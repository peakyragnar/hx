from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Iterable
import json
import os
import sys

import typer
from dotenv import load_dotenv

from .config import load_run_config, RunConfig
from .rpl import run_single_version
from .sampler import rotation_offset, balanced_indices_with_rotation, planned_counts
from .seed import make_bootstrap_seed
import yaml


app = typer.Typer(help="Heretix (new) RPL harness")


@app.callback()
def _root_callback():
    """Heretix CLI root."""
    # No root options; subcommands handle actions.
    pass


@app.command("run")
def cmd_run(
    config: Path = typer.Option(..., exists=True, dir_okay=False, help="Path to run config YAML/JSON"),
    prompt_version: List[str] = typer.Option(None, help="Override prompt versions to run (one or many)"),
    out: Path = typer.Option(Path("runs/rpl_run.json"), help="Output JSON file (A/B summary)"),
    mock: bool = typer.Option(False, help="Use deterministic mock provider (no network) for smoke tests"),
    dry_run: bool = typer.Option(False, help="Preview effective plan without running or writing to DB"),
):
    """Run single or multiple prompt versions and print compact A/B results."""
    load_dotenv()
    # Only require API key for live runs; allow --mock runs without it
    if not mock and not os.getenv("HERETIX_MOCK") and not os.getenv("OPENAI_API_KEY"):
        typer.echo("ERROR: OPENAI_API_KEY not set (required for live runs)", err=True)
        raise typer.Exit(1)

    cfg = load_run_config(str(config))
    versions = prompt_version if prompt_version else [cfg.prompt_version]

    # Helper: load prompt YAML for planning
    def _load_prompt(path: Path) -> dict:
        return yaml.safe_load(path.read_text())

    # Helper: plan summary (no network)
    def _plan_summary(cfg_local: RunConfig, prompt_path: Path) -> dict:
        doc = _load_prompt(prompt_path)
        paraphrases = [str(x) for x in doc.get("paraphrases", [])]
        T_bank = len(paraphrases)
        T_stage = int(cfg_local.T) if cfg_local.T is not None else T_bank
        T_stage = max(1, min(T_stage, T_bank))
        off = rotation_offset(cfg_local.claim, cfg_local.model, str(doc.get("version")), T_bank)
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

    # Helper: read claims from a file (JSONL or plain text)
    def _read_claims(path: Path) -> List[str]:
        claims: List[str] = []
        for line in path.read_text().splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            try:
                obj = json.loads(s)
                if isinstance(obj, dict) and "claim" in obj:
                    claims.append(str(obj["claim"]))
                elif isinstance(obj, str):
                    claims.append(obj)
                else:
                    # Fallback: treat raw line as the claim text
                    claims.append(s)
            except Exception:
                claims.append(s)
        return claims

    # Batch mode detection: claims_file present
    is_batch = bool(cfg.claims_file)

    if is_batch:
        # Read all claims
        claims_path = Path(cfg.claims_file)
        if not claims_path.exists():
            typer.echo(f"ERROR: claims_file not found: {claims_path}", err=True)
            raise typer.Exit(1)
        claim_list = _read_claims(claims_path)
        if dry_run:
            # For dry-run in batch, preview high-level plan only
            # Use the first version only for preview; batch always runs one prompt_version set unless overridden
            v = versions[0]
            local_cfg = RunConfig(**{**cfg.__dict__})
            local_cfg.claim = claim_list[0] if claim_list else cfg.claim
            local_cfg.prompt_version = v
            prompt_file = Path(local_cfg.prompt_file_path or (Path(__file__).parent / "prompts" / f"{v}.yaml"))
            plan = _plan_summary(local_cfg, prompt_file)
            preview = {
                "mode": "batch",
                "n_claims": len(claim_list),
                "versions": versions,
                "plan": plan,
            }
            typer.echo(json.dumps(preview, indent=2))
            return

        # Streaming JSONL if out endswith .jsonl; else write a big JSON array
        out.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl = out.suffix.lower() == ".jsonl"
        if write_jsonl:
            with out.open("w") as f:
                for idx, claim in enumerate(claim_list):
                    for v in versions:
                        local_cfg = RunConfig(**{**cfg.__dict__})
                        local_cfg.claim = claim
                        local_cfg.prompt_version = v
                        prompt_file = local_cfg.prompt_file_path or (Path(__file__).parent / "prompts" / f"{v}.yaml")
                        typer.echo(f"[{idx+1}/{len(claim_list)}] Running {local_cfg.model}  K={local_cfg.K} R={local_cfg.R}  version={v}")
                        res = run_single_version(local_cfg, prompt_file=str(prompt_file), mock=mock)
                        f.write(json.dumps(res) + "\n")
            typer.echo(f"Wrote {out}")
        else:
            results = []
            for idx, claim in enumerate(claim_list):
                for v in versions:
                    local_cfg = RunConfig(**{**cfg.__dict__})
                    local_cfg.claim = claim
                    local_cfg.prompt_version = v
                    prompt_file = local_cfg.prompt_file_path or (Path(__file__).parent / "prompts" / f"{v}.yaml")
                    typer.echo(f"[{idx+1}/{len(claim_list)}] Running {local_cfg.model}  K={local_cfg.K} R={local_cfg.R}  version={v}")
                    res = run_single_version(local_cfg, prompt_file=str(prompt_file), mock=mock)
                    results.append(res)
            # Print A/B summary lines
            for r in results:
                a = r["aggregates"]
                typer.echo(
                    f"v={r['prompt_version']}  p={a['prob_true_rpl']:.3f}  CI95=[{a['ci95'][0]:.3f},{a['ci95'][1]:.3f}]  width={a['ci_width']:.3f}  stab={a['stability_score']:.3f}  compl={a['rpl_compliance_rate']:.2f}  cache={a['cache_hit_rate']:.2f}"
                )
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"runs": results}, indent=2))
            typer.echo(f"Wrote {out}")
        return

    # Single-claim path (default)
    if dry_run:
        v = versions[0]
        local_cfg = RunConfig(**{**cfg.__dict__})
        local_cfg.prompt_version = v
        prompt_file = Path(local_cfg.prompt_file_path or (Path(__file__).parent / "prompts" / f"{v}.yaml"))
        plan = _plan_summary(local_cfg, prompt_file)
        typer.echo(json.dumps({"mode": "single", "plan": plan}, indent=2))
        return

    results = []
    for v in versions:
        local_cfg = RunConfig(**{**cfg.__dict__})
        local_cfg.prompt_version = v
        prompt_file = local_cfg.prompt_file_path or (Path(__file__).parent / "prompts" / f"{v}.yaml")
        typer.echo(f"Running {local_cfg.model}  K={local_cfg.K} R={local_cfg.R}  version={v}")
        res = run_single_version(local_cfg, prompt_file=str(prompt_file), mock=mock)
        results.append(res)

    # A/B table summary to stdout
    for r in results:
        a = r["aggregates"]
        typer.echo(
            f"v={r['prompt_version']}  p={a['prob_true_rpl']:.3f}  CI95=[{a['ci95'][0]:.3f},{a['ci95'][1]:.3f}]  width={a['ci_width']:.3f}  stab={a['stability_score']:.3f}  compl={a['rpl_compliance_rate']:.2f}  cache={a['cache_hit_rate']:.2f}"
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"runs": results}, indent=2))
    typer.echo(f"Wrote {out}")


@app.command("describe")
def cmd_describe(
    config: Path = typer.Option(..., exists=True, dir_okay=False, help="Path to run config YAML/JSON"),
):
    """Describe the effective configuration and sampling plan (no network)."""
    cfg = load_run_config(str(config))
    prompt_file = Path(cfg.prompt_file_path or (Path(__file__).parent / "prompts" / f"{cfg.prompt_version}.yaml"))
    # For batch, claim placeholder to compute rotation; we don’t need to be exact here
    claim_preview = cfg.claim
    if cfg.claims_file and not cfg.claim:
        try:
            # Peek first non-empty line
            with open(cfg.claims_file, "r") as fh:
                for line in fh:
                    s = line.strip()
                    if s:
                        try:
                            obj = json.loads(s)
                            claim_preview = obj.get("claim", s) if isinstance(obj, dict) else (obj if isinstance(obj, str) else s)
                        except Exception:
                            claim_preview = s
                        break
        except Exception:
            pass
    # Compose a temporary cfg
    tmp = RunConfig(**{**cfg.__dict__})
    tmp.claim = claim_preview
    plan = {
        "batch": bool(cfg.claims_file),
        "claims_file": cfg.claims_file,
    }
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
    schema_instructions = (
        "Return ONLY valid JSON with exactly these fields:\n"
        "{\n  \"prob_true\": number between 0 and 1,\n  \"confidence_self\": number between 0 and 1,\n  \"assumptions\": array of strings,\n  \"reasoning_bullets\": array of 3-6 strings,\n  \"contrary_considerations\": array of 2-4 strings,\n  \"ambiguity_flags\": array of strings\n}\n"
        "Output ONLY the JSON object, no other text."
    )
    full_instructions = system_text + "\n\n" + schema_instructions
    tpl_hashes = []
    for idx in tpl_indices:
        ptxt = paraphrases[idx].replace("{CLAIM}", tmp.claim)
        utext = f"{ptxt}\n\n" + user_template.replace("{CLAIM}", tmp.claim)
        h = hashlib.sha256((full_instructions + "\n\n" + utext).encode("utf-8")).hexdigest()
        tpl_hashes.append(h)

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
            "claims_file": cfg.claims_file,
            "model": cfg.model,
            "prompt_version": cfg.prompt_version,
            "prompt_version_full": str(doc.get("version")),
            "K": cfg.K,
            "R": cfg.R,
            "T": T_stage,
            "B": cfg.B,
            "seed": cfg.seed,
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
        },
    }
    typer.echo(json.dumps(summary, indent=2))


if __name__ == "__main__":
    # Allow module execution via: python -m heretix.cli
    app()
