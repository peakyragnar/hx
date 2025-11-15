from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, List, Optional
import json
import os
import hashlib
import gzip

import typer
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import load_run_config, RunConfig
from .sampler import rotation_offset, balanced_indices_with_rotation, planned_counts
from .seed import make_bootstrap_seed
import yaml
from heretix.pipeline import PipelineOptions, perform_run
from heretix.db.models import Check
from heretix.provider.utils import infer_provider_from_model
from heretix.provider.schema_text import RPL_SAMPLE_JSON_SCHEMA
from heretix.constants import SCHEMA_VERSION


app = typer.Typer(help="Heretix (new) RPL harness")


@app.callback()
def _root_callback():
    """Heretix CLI root."""
    # No root options; subcommands handle actions.
    pass


def _plan_summary(cfg_local: RunConfig, prompt_path: Path) -> dict:
    doc = yaml.safe_load(prompt_path.read_text())
    paraphrases = [str(x) for x in doc.get("paraphrases", [])]
    T_bank = len(paraphrases)
    T_stage = int(cfg_local.T) if cfg_local.T is not None else T_bank
    T_stage = max(1, min(T_stage, T_bank))
    logical_model = cfg_local.logical_model or cfg_local.model
    off = rotation_offset(cfg_local.claim, logical_model, str(doc.get("version")), T_bank)
    order = list(range(T_bank))
    if T_bank > 1 and off % T_bank != 0:
        rot = off % T_bank
        order = order[rot:] + order[:rot]
    tpl_indices = order[:T_stage]
    seq = balanced_indices_with_rotation(T_stage, cfg_local.K, offset=0)
    counts, ratio = planned_counts(seq, T_stage)
    return {
        "claim": cfg_local.claim,
        "model": cfg_local.model,
        "prompt_version": cfg_local.prompt_version,
        "prompt_version_full": str(doc.get("version")),
        "K": cfg_local.K,
        "R": cfg_local.R,
        "T": T_stage,
        "B": cfg_local.B,
        "max_output_tokens": cfg_local.max_output_tokens,
        "T_bank": T_bank,
        "rotation_offset": off,
        "tpl_indices": tpl_indices,
        "seq": seq,
        "planned_counts": counts,
        "planned_imbalance_ratio": ratio,
    }


@app.command("run")
def cmd_run(
    config: Path = typer.Option(..., exists=True, dir_okay=False, help="Path to run config YAML/JSON"),
    prompt_version: List[str] = typer.Option(None, help="Override prompt versions to run (one or many)"),
    model_name: List[str] = typer.Option(None, "--model", "-m", help="Override models to run (repeatable)"),
    out: Path = typer.Option(Path("runs/rpl_run.json"), help="Output JSON file (A/B summary)"),
    mock: bool = typer.Option(False, help="Use deterministic mock provider (no network) for smoke tests"),
    dry_run: bool = typer.Option(False, help="Preview effective plan without running or writing to DB"),
    mode: str = typer.Option("baseline", help="Evaluation mode: baseline or web_informed"),
    database_url: Optional[str] = typer.Option(None, help="Database URL override (defaults to sqlite:///runs/heretix.sqlite)"),
):
    """Run single or multiple prompt versions and print compact A/B results."""
    load_dotenv()
    mode_normalized = (mode or "baseline").lower()
    if mode_normalized not in {"baseline", "web_informed"}:
        typer.echo("ERROR: mode must be 'baseline' or 'web_informed'", err=True)
        raise typer.Exit(1)

    if not mock and not os.getenv("HERETIX_MOCK") and not os.getenv("OPENAI_API_KEY"):
        typer.echo("ERROR: OPENAI_API_KEY not set (required for live runs)", err=True)
        raise typer.Exit(1)

    cfg = load_run_config(str(config))
    override_models = _normalize_model_list(model_name)
    models_to_run = override_models or (cfg.models or [cfg.model])
    models_to_run = _normalize_model_list(models_to_run)
    if not models_to_run:
        typer.echo("ERROR: No models specified", err=True)
        raise typer.Exit(1)
    cfg.models = models_to_run
    cfg.model = models_to_run[0]
    cfg.logical_model = cfg.model
    versions = prompt_version if prompt_version else [cfg.prompt_version]

    if dry_run:
        plans: List[dict[str, Any]] = []
        for model in models_to_run:
            for v in versions:
                local_cfg = RunConfig(**{**cfg.__dict__})
                local_cfg.model = model
                local_cfg.logical_model = model
                if not local_cfg.provider_locked:
                    local_cfg.provider = infer_provider_from_model(model)
                local_cfg.prompt_version = v
                prompt_file = (
                    Path(local_cfg.prompt_file_path)
                    if local_cfg.prompts_file
                    else Path(__file__).parent / "prompts" / f"{v}.yaml"
                )
                plans.append(_plan_summary(local_cfg, prompt_file))
        if len(plans) == 1:
            typer.echo(json.dumps({"mode": "single", "plan": plans[0]}, indent=2))
        else:
            typer.echo(json.dumps({"mode": "multi", "plans": plans}, indent=2))
        return

    effective_db_url = database_url or os.getenv("DATABASE_URL", "sqlite:///runs/heretix.sqlite")
    os.environ["DATABASE_URL"] = effective_db_url

    from heretix.db.migrate import ensure_schema

    ensure_schema(effective_db_url)

    engine = create_engine(effective_db_url, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    prompt_root_env = os.getenv("RPL_PROMPTS_DIR")
    prompt_root = Path(prompt_root_env) if prompt_root_env else None
    recency_env = os.getenv("WEL_RECENCY_DAYS")
    if recency_env and recency_env.lower() == "none":
        wel_recency = None
    elif recency_env:
        try:
            wel_recency = int(recency_env)
        except ValueError:
            # On invalid override, fall back to adaptive (auto)
            wel_recency = None
    else:
        # Default to adaptive (auto): let WEL choose based on claim timeliness
        wel_recency = None

    pipeline_options = PipelineOptions(
        app_env=os.getenv("APP_ENV", "local"),
        wel_provider=os.getenv("WEL_PROVIDER", "tavily"),
        wel_model=os.getenv("WEL_MODEL", cfg.model),
        wel_docs=int(os.getenv("WEL_DOCS", "16")),
        wel_replicates=int(os.getenv("WEL_REPLICATES", "2")),
        wel_per_domain_cap=int(os.getenv("WEL_PER_DOMAIN_CAP", "3")),
        wel_recency_days=wel_recency,
        prompt_root=prompt_root,
    )

    runs_output: list[dict] = []
    for model in models_to_run:
        for v in versions:
            local_cfg = RunConfig(**{**cfg.__dict__})
            local_cfg.model = model
            local_cfg.logical_model = model
            if not local_cfg.provider_locked:
                local_cfg.provider = infer_provider_from_model(model)
            local_cfg.prompt_version = v
            typer.echo(f"Running {model}  K={local_cfg.K} R={local_cfg.R}  mode={mode_normalized}  version={v}")

            run_options = replace(pipeline_options, wel_model=model)
            with SessionLocal() as session:
                artifacts = perform_run(
                    session=session,
                    cfg=local_cfg,
                    mode=mode_normalized,
                    options=run_options,
                    use_mock=mock,
                    user_id=None,
                    anon_token=None,
                )
                session.commit()

            run_entry = _build_run_entry(local_cfg, mode_normalized, mock, artifacts)
            runs_output.append(run_entry)

            combined_block = run_entry.get("combined") or run_entry.get("prior")
            ci = combined_block.get("ci95", [None, None]) or [None, None]
            p_val = combined_block.get("p")
            if p_val is not None:
                ci_lo = f"{ci[0]:.3f}" if ci[0] is not None else "nan"
                ci_hi = f"{ci[1]:.3f}" if ci[1] is not None else "nan"
                typer.echo(f"  combined_p={p_val:.3f}  CI95=[{ci_lo},{ci_hi}]")
            weight_block = run_entry.get("weights") or {}
            w_web = weight_block.get("w_web")
            if w_web is not None:
                try:
                    w_web_value = float(w_web)
                except (TypeError, ValueError):
                    w_web_value = 0.0
                w_web_value = max(0.0, min(1.0, w_web_value))
                typer.echo(f"  weights: web={w_web_value:.2f}  prior={(1.0 - w_web_value):.2f}")

    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"mode": mode_normalized, "requested_models": models_to_run, "runs": runs_output}
    out.write_text(json.dumps(payload, indent=2))
    typer.echo(f"Wrote {out}")


def _build_run_entry(cfg: RunConfig, mode: str, mock: bool, artifacts) -> dict:
    result = artifacts.result
    run_data: dict[str, Any] = {
        "execution_id": result.get("execution_id"),
        "run_id": result.get("run_id"),
        "claim": result.get("claim"),
        "model": result.get("model", cfg.model),
        "prompt_version": result.get("prompt_version", cfg.prompt_version),
        "mode": mode,
        "schema_version": result.get("schema_version", SCHEMA_VERSION),
        "sampling": result.get("sampling", {}),
        "aggregation": result.get("aggregation", {}),
        "aggregates": result.get("aggregates", {}),
        "prior": artifacts.prior_block,
        "web": artifacts.web_block,
        "combined": artifacts.combined_block,
        "weights": artifacts.weights,
        "mock": mock,
        "prompt_file": str(artifacts.prompt_file),
        "simple_expl": artifacts.simple_expl,
        "provenance": {
            "rpl": {
                "prompt_version": result.get("prompt_version", cfg.prompt_version),
                "model": result.get("model", cfg.model),
            }
        },
    }
    if artifacts.wel_provenance:
        run_data["provenance"]["wel"] = artifacts.wel_provenance
    if artifacts.wel_replicates:
        run_data["wel_replicates"] = artifacts.wel_replicates
    if artifacts.wel_debug_votes:
        run_data["wel_debug_votes"] = artifacts.wel_debug_votes
    if artifacts.artifact_manifest_uri:
        run_data["web_artifact"] = {
            "manifest": artifacts.artifact_manifest_uri,
            "replicates_uri": artifacts.artifact_replicates_uri,
            "docs_uri": artifacts.artifact_docs_uri,
        }
    return run_data


def _load_local_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Artifact file not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _load_local_gzip_json(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Artifact file not found: {path}")
    return json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))


def _normalize_model_list(values: Any) -> List[str]:
    if not values:
        return []
    if isinstance(values, (list, tuple, set)):
        candidates = list(values)
    else:
        candidates = [values]

    normalized: List[str] = []
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if not text or text in normalized:
            continue
        normalized.append(text)
    return normalized


@app.command("artifact")
def cmd_artifact(
    run_id: Optional[str] = typer.Option(None, help="Run ID to inspect"),
    claim: Optional[str] = typer.Option(None, help="Claim text; shows most recent run"),
    database_url: Optional[str] = typer.Option(
        None, help="Database URL (defaults to sqlite:///runs/heretix.sqlite)"
    ),
    max_docs: int = typer.Option(5, help="Number of documents to show"),
    max_support: int = typer.Option(3, help="Support bullets per replicate to show"),
):
    """Pretty-print stored web artifacts (docs & replicate summaries)."""
    if not run_id and not claim:
        typer.echo("Provide --run-id or --claim", err=True)
        raise typer.Exit(1)

    effective_db_url = database_url or "sqlite:///runs/heretix.sqlite"
    os.environ["DATABASE_URL"] = effective_db_url

    from heretix.db.migrate import ensure_schema

    ensure_schema(effective_db_url)

    engine = create_engine(effective_db_url, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    with SessionLocal() as session:
        query = session.query(Check)
        if run_id:
            query = query.filter(Check.run_id == run_id)
        if claim:
            query = query.filter(Check.claim == claim)
        row = query.order_by(Check.created_at.desc()).first()
        if row is None:
            text = run_id or claim or "criteria"
            typer.echo(f"No run found for {text}", err=True)
            raise typer.Exit(1)
        manifest_path = row.artifact_json_path
        if not manifest_path:
            typer.echo("Run has no stored artifact; enable HERETIX_ARTIFACT_BACKEND", err=True)
            raise typer.Exit(1)

    if manifest_path.startswith("gs://"):
        typer.echo(
            f"Artifact stored remotely ({manifest_path}); download it first or run export script.",
            err=True,
        )
        raise typer.Exit(1)

    manifest = _load_local_json(manifest_path)
    typer.echo(f"Run ID: {manifest.get('run_id')}")
    typer.echo(f"Claim : {manifest.get('claim')}")
    typer.echo(f"Mode  : {manifest.get('mode')}")
    web = manifest.get("web") or {}
    typer.echo(f"Web p : {web.get('p'):.3f}  CI95={web.get('ci95')}")
    evidence = web.get("evidence") or {}
    typer.echo(
        f"Docs={int(evidence.get('n_docs', 0))} Domains={int(evidence.get('n_domains', 0))} "
        f"Median age≈{evidence.get('median_age_days')}"
    )

    docs_uri = manifest.get("docs_uri")
    if docs_uri and docs_uri.startswith("runs/"):
        docs = _load_local_gzip_json(docs_uri)
        typer.echo("\nTop documents:")
        for doc in docs[:max_docs]:
            typer.echo(f"- {doc.get('domain')} :: {doc.get('title')}")
            typer.echo(f"  {doc.get('url')}")
            snippet = (doc.get("snippet") or "").strip()
            if snippet:
                typer.echo(f"  Snippet: {snippet[:240]}{'…' if len(snippet) > 240 else ''}")
            published = doc.get("published_at")
            if published:
                typer.echo(f"  Published: {published} (confidence {doc.get('published_confidence')})")
    else:
        typer.echo("\nDocuments bundle not available locally.")

    reps_uri = manifest.get("replicates_uri")
    if reps_uri and reps_uri.startswith("runs/"):
        replicates = _load_local_gzip_json(reps_uri)
        typer.echo("\nReplicates:")
        for rep in replicates:
            typer.echo(f"- replicate {rep.get('replicate_idx')}   p_web={rep.get('p_web'):.3f}")
            support = list(rep.get("support_bullets") or [])[:max_support]
            oppose = list(rep.get("oppose_bullets") or [])[:max_support]
            if support:
                typer.echo("  support:")
                for bullet in support:
                    typer.echo(f"    • {bullet}")
            if oppose:
                typer.echo("  oppose:")
                for bullet in oppose:
                    typer.echo(f"    • {bullet}")
    else:
        typer.echo("\nReplicate bundle not available locally.")

    typer.echo("\nDone.")


@app.command("describe")
def cmd_describe(
    config: Path = typer.Option(..., exists=True, dir_okay=False, help="Path to run config YAML/JSON"),
):
    """Describe the effective configuration and sampling plan (no network)."""
    cfg = load_run_config(str(config))
    prompt_file = (
        Path(cfg.prompt_file_path)
        if cfg.prompts_file
        else (Path(__file__).parent / "prompts" / f"{cfg.prompt_version}.yaml")
    )
    # Compose a temporary cfg
    tmp = RunConfig(**{**cfg.__dict__})
    tmp.claim = cfg.claim
    # Build the same plan as dry-run
    doc = yaml.safe_load(prompt_file.read_text())
    paraphrases = [str(x) for x in doc.get("paraphrases", [])]
    T_bank = len(paraphrases)
    T_stage = int(cfg.T) if cfg.T is not None else T_bank
    T_stage = max(1, min(T_stage, T_bank))
    off = rotation_offset(tmp.claim, tmp.model, str(doc.get("version")), T_bank)
    order = list(range(T_bank))
    if T_bank > 1 and off % T_bank != 0:
        rot = off % T_bank
        order = order[rot:] + order[:rot]
    tpl_indices = order[:T_stage]
    seq = balanced_indices_with_rotation(T_stage, tmp.K, offset=0)
    counts, ratio = planned_counts(seq, T_stage)
    # Compute planned bootstrap seed with precedence (config > env > derived)
    # Build template hashes for selected templates
    system_text = str(doc.get("system"))
    user_template = str(doc.get("user_template"))
    schema_instructions = RPL_SAMPLE_JSON_SCHEMA
    full_instructions = system_text + "\n\n" + schema_instructions
    tpl_hashes = []
    prompt_len_list = []
    for idx in tpl_indices:
        ptxt = paraphrases[idx].replace("{CLAIM}", tmp.claim)
        utext = f"{ptxt}\n\n" + user_template.replace("{CLAIM}", tmp.claim)
        h = hashlib.sha256((full_instructions + "\n\n" + utext).encode("utf-8")).hexdigest()
        tpl_hashes.append(h)
        prompt_len_list.append(len(full_instructions + "\n\n" + utext))

    if cfg.seed is not None:
        seed_eff = int(cfg.seed)
    elif os.getenv("HERETIX_RPL_SEED") is not None:
        seed_eff = int(os.getenv("HERETIX_RPL_SEED"))
    else:
        seed_eff = make_bootstrap_seed(
            claim=tmp.claim,
            model=tmp.model,
            prompt_version=str(doc.get("version")),
            k=tmp.K,
            r=tmp.R,
            template_hashes=sorted(set(tpl_hashes)),
            center="trimmed",
            trim=0.2,
            B=tmp.B,
        )

    summary = {
        "config": {
            "claim": cfg.claim,
            "model": cfg.model,
            "models": cfg.models,
            "prompt_version": cfg.prompt_version,
            "prompt_version_full": str(doc.get("version")),
            "K": cfg.K,
            "R": cfg.R,
            "T": T_stage,
            "B": cfg.B,
            "seed": cfg.seed,
            "max_prompt_chars": cfg.max_prompt_chars,
            "max_output_tokens": cfg.max_output_tokens,
        },
        "plan": {
            "T_bank": T_bank,
            "rotation_offset": off,
            "tpl_indices": tpl_indices,
            "seq": seq,
            "planned_counts": counts,
            "planned_imbalance_ratio": ratio,
            "bootstrap_seed_effective": seed_eff,
            "prompt_char_len_max": (max(prompt_len_list) if prompt_len_list else 0),
            "prompt_char_len_over_cap": (max(prompt_len_list) > int(cfg.max_prompt_chars) if (prompt_len_list and cfg.max_prompt_chars) else False),
        },
    }
    typer.echo(json.dumps(summary, indent=2))


if __name__ == "__main__":
    # Allow module execution via: python -m heretix.cli
    app()
