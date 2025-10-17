from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import logging
from sqlalchemy import select
from sqlalchemy.orm import Session

from heretix.config import RunConfig
from heretix.rpl import run_single_version
from heretix.db.models import Check
from heretix_api.routes_checks import evaluate_web_informed
import hashlib
from heretix.artifacts import ArtifactRecord, get_artifact_store, write_web_artifact


@dataclass
class PipelineOptions:
    """Configuration knobs shared between CLI and API execution paths."""

    app_env: str = "local"
    wel_provider: str = "tavily"
    wel_model: str = "gpt-5"
    wel_docs: int = 16
    wel_replicates: int = 2
    wel_per_domain_cap: int = 3
    wel_recency_days: Optional[int] = 14
    prompt_root: Optional[Path] = None


@dataclass
class PipelineArtifacts:
    """Return payload for downstream serialization."""

    result: Dict[str, Any]
    prior_block: Dict[str, Any]
    web_block: Optional[Dict[str, Any]]
    combined_block: Dict[str, Any]
    weights: Optional[Dict[str, Any]]
    wel_provenance: Optional[Dict[str, Any]]
    prompt_file: Path
    check: Check
    wel_replicates: list[Dict[str, Any]]
    wel_debug_votes: Optional[list[Dict[str, Any]]]
    artifact_manifest_uri: Optional[str] = None
    artifact_replicates_uri: Optional[str] = None
    artifact_docs_uri: Optional[str] = None


logger = logging.getLogger(__name__)


def resolve_prompt_file(cfg: RunConfig, options: PipelineOptions) -> Path:
    if cfg.prompts_file:
        return Path(cfg.prompts_file)
    if options.prompt_root:
        base = options.prompt_root
    else:
        from heretix import __file__ as heretix_file

        base = Path(heretix_file).resolve().parent / "prompts"
    path = base / f"{cfg.prompt_version}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path


def perform_run(
    *,
    session: Session,
    cfg: RunConfig,
    mode: str,
    options: PipelineOptions,
    use_mock: bool,
    user_id: Optional[str],
    anon_token: Optional[str],
) -> PipelineArtifacts:
    """
    Execute a single run (RPL baseline plus optional WEL) and persist results into `checks`.
    """
    prompt_file = resolve_prompt_file(cfg, options)
    result = run_single_version(cfg, prompt_file=str(prompt_file), mock=use_mock)

    aggregation = result.get("aggregation", {})
    aggregates = dict(result.get("aggregates", {}))
    sampling = dict(result.get("sampling", {}))

    ci95 = aggregates.get("ci95", [None, None])
    rpl_compliance_rate = float(aggregates.get("rpl_compliance_rate", 0.0))
    cache_hit_rate = float(aggregates.get("cache_hit_rate", 0.0))
    ci_width = float(aggregates.get("ci_width", (ci95[1] or 0.0) - (ci95[0] or 0.0)))
    stability_score = float(aggregates.get("stability_score", 0.0))

    now = datetime.now(timezone.utc)

    prior_p = float(aggregates.get("prob_true_rpl") or 0.0)
    prior_ci = [
        float(ci95[0]) if ci95 and ci95[0] is not None else 0.0,
        float(ci95[1]) if ci95 and ci95[1] is not None else 0.0,
    ]
    prior_block_payload = {
        "p": prior_p,
        "ci95": prior_ci,
        "stability": stability_score,
    }

    web_block_payload: Optional[Dict[str, Any]] = None
    combined_block_payload: Dict[str, Any] = {"p": prior_p, "ci95": list(prior_ci), "resolved": False}
    weights_payload: Optional[Dict[str, Any]] = None
    wel_provenance: Optional[Dict[str, Any]] = None
    raw_replicates: list[Any] = []
    debug_votes: Optional[list[Dict[str, Any]]] = None
    artifact_record: Optional[ArtifactRecord] = None

    if mode == "web_informed":
        web_block_payload, combined_block_payload, weights_payload, wel_provenance = evaluate_web_informed(
            claim=cfg.claim or "",
            prior={"p": prior_p, "ci95": prior_ci},
            provider=options.wel_provider,
            model=options.wel_model,
            k_docs=options.wel_docs,
            replicates=options.wel_replicates,
            per_domain_cap=options.wel_per_domain_cap,
            recency_days=options.wel_recency_days,
            seed=cfg.seed,
        )
        if web_block_payload:
            raw_replicates = web_block_payload.get("replicates", []) or []
            debug_votes = web_block_payload.get("resolved_debug_votes")

    aggregation_counts = aggregation.get("counts_by_template", {})
    config_json = json.dumps(
        {
            "claim": cfg.claim,
            "model": cfg.model,
            "prompt_version": cfg.prompt_version,
            "K": cfg.K,
            "R": cfg.R,
            "T": sampling.get("T"),
            "B": cfg.B,
            "seed": cfg.seed,
            "max_output_tokens": cfg.max_output_tokens,
            "no_cache": cfg.no_cache,
            "prompt_file": str(prompt_file),
            "mode": mode,
        }
    )

    run_id = result.get("run_id")
    if not run_id:
        raise RuntimeError("run_id missing from RPL result")

    check = session.scalar(select(Check).where(Check.run_id == run_id))
    if check is None:
        check = Check(run_id=run_id, env=options.app_env)
        session.add(check)

    check.env = options.app_env
    check.user_id = user_id
    check.claim = cfg.claim
    check.claim_hash = hashlib.sha256((cfg.claim or "").encode("utf-8")).hexdigest() if cfg.claim else None
    check.model = result.get("model", cfg.model)
    check.prompt_version = result.get("prompt_version", cfg.prompt_version)
    check.k = int(cfg.K)
    check.r = int(cfg.R)
    check.t = sampling.get("T")
    check.b = cfg.B
    check.seed = cfg.seed
    bootstrap_seed_val = aggregation.get("bootstrap_seed")
    check.bootstrap_seed = int(bootstrap_seed_val) if bootstrap_seed_val is not None else None
    check.max_output_tokens = cfg.max_output_tokens
    check.prob_true_rpl = float(aggregates.get("prob_true_rpl"))
    check.ci_lo = float(ci95[0]) if ci95 and ci95[0] is not None else None
    check.ci_hi = float(ci95[1]) if ci95 and ci95[1] is not None else None
    check.ci_width = ci_width
    check.template_iqr_logit = aggregation.get("template_iqr_logit")
    check.stability_score = stability_score
    check.imbalance_ratio = aggregation.get("imbalance_ratio")
    check.rpl_compliance_rate = rpl_compliance_rate
    check.cache_hit_rate = cache_hit_rate
    check.config_json = config_json
    check.sampler_json = json.dumps({"K": cfg.K, "R": cfg.R, "T": sampling.get("T")})
    check.counts_by_template_json = json.dumps(aggregation_counts)
    check.artifact_json_path = None
    check.prompt_char_len_max = aggregation.get("prompt_char_len_max")
    check.pqs = None
    check.gate_compliance_ok = rpl_compliance_rate >= 0.98
    check.gate_stability_ok = stability_score >= 0.25
    check.gate_precision_ok = ci_width <= 0.30
    check.pqs_version = None
    check.mode = mode
    check.p_prior = prior_p
    check.ci_prior_lo = prior_ci[0]
    check.ci_prior_hi = prior_ci[1]
    check.stability_prior = stability_score

    if web_block_payload:
        evidence = web_block_payload.get("evidence", {})
        check.p_web = float(web_block_payload["p"])
        check.ci_web_lo = float(web_block_payload["ci95"][0])
        check.ci_web_hi = float(web_block_payload["ci95"][1])
        check.n_docs = int(evidence.get("n_docs", 0))
        check.n_domains = int(evidence.get("n_domains", 0))
        check.median_age_days = float(evidence.get("median_age_days", 0.0))
        check.web_dispersion = float(evidence.get("dispersion", 0.0))
        check.json_valid_rate = float(evidence.get("json_valid_rate", 0.0))
        date_confident = evidence.get("date_confident_rate")
        confident_count = evidence.get("n_confident_dates")
        if date_confident is not None:
            check.date_confident_rate = float(date_confident)
        if confident_count is not None:
            check.n_confident_dates = float(confident_count)
    else:
        check.p_web = None
        check.ci_web_lo = None
        check.ci_web_hi = None
        check.n_docs = None
        check.n_domains = None
        check.median_age_days = None
        check.web_dispersion = None
        check.json_valid_rate = None
        check.date_confident_rate = None
        check.n_confident_dates = None

    if combined_block_payload:
        check.p_combined = float(combined_block_payload["p"])
        check.ci_combined_lo = float(combined_block_payload["ci95"][0])
        check.ci_combined_hi = float(combined_block_payload["ci95"][1])
    else:
        check.p_combined = None
        check.ci_combined_lo = None
        check.ci_combined_hi = None

    if weights_payload:
        check.w_web = float(weights_payload.get("w_web", 0.0))
        check.recency_score = float(weights_payload.get("recency", 0.0))
        check.strength_score = float(weights_payload.get("strength", 0.0))
    else:
        check.w_web = None
        check.recency_score = None
        check.strength_score = None

    if combined_block_payload and combined_block_payload.get("resolved"):
        check.resolved_flag = True
        resolved_truth = combined_block_payload.get("resolved_truth")
        check.resolved_truth = bool(resolved_truth) if resolved_truth is not None else None
        check.resolved_reason = combined_block_payload.get("resolved_reason")
        check.resolved_support = combined_block_payload.get("support")
        check.resolved_contradict = combined_block_payload.get("contradict")
        domains_val = combined_block_payload.get("domains")
        check.resolved_domains = int(domains_val) if domains_val is not None else None
        citations_val = combined_block_payload.get("resolved_citations")
        check.resolved_citations = json.dumps(citations_val) if citations_val is not None else None
    else:
        check.resolved_flag = False if mode == "web_informed" else None
        check.resolved_truth = None
        check.resolved_reason = None
        check.resolved_support = None
        check.resolved_contradict = None
        check.resolved_domains = None
        check.resolved_citations = None

    check.was_cached = cache_hit_rate >= 0.999
    check.provider_model_id = result.get("model", cfg.model)
    check.anon_token = anon_token if user_id is None else None
    check.created_at = now
    check.finished_at = now

    if mode == "web_informed" and web_block_payload:
        try:
            store = get_artifact_store()
            artifact_record = write_web_artifact(
                run_id=run_id,
                claim=cfg.claim,
                mode=mode,
                store=store,
                prior_block=prior_block_payload,
                web_block=web_block_payload,
                combined_block=combined_block_payload,
                wel_provenance=wel_provenance,
                replicates=raw_replicates,
                debug_votes=debug_votes,
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("Failed to write web artifact for run %s: %s", run_id, exc)
            artifact_record = None

    if artifact_record:
        check.artifact_json_path = artifact_record.manifest_uri

    normalized_reps = [_normalize_replica(rep) for rep in raw_replicates]
    if web_block_payload is not None:
        web_block_payload["replicates"] = normalized_reps
        if debug_votes is not None:
            web_block_payload["resolved_debug_votes"] = debug_votes

    return PipelineArtifacts(
        result=result,
        prior_block=prior_block_payload,
        web_block=web_block_payload,
        combined_block=combined_block_payload,
        weights=weights_payload,
        wel_provenance=wel_provenance,
        prompt_file=prompt_file,
        check=check,
        wel_replicates=normalized_reps,
        wel_debug_votes=debug_votes,
        artifact_manifest_uri=artifact_record.manifest_uri if artifact_record else None,
        artifact_replicates_uri=artifact_record.verdicts_uri if artifact_record else None,
        artifact_docs_uri=artifact_record.docs_uri if artifact_record else None,
    )


def _normalize_replica(rep: Any) -> Dict[str, Any]:
    support = []
    oppose = []
    notes = []
    json_valid = None
    replicate_idx = getattr(rep, "replicate_idx", None)
    p_web = getattr(rep, "p_web", None)
    if isinstance(rep, dict):
        replicate_idx = rep.get("replicate_idx")
        p_web = rep.get("p_web")
        support = list(rep.get("support_bullets", []))
        oppose = list(rep.get("oppose_bullets", []))
        notes = list(rep.get("notes", []))
        json_valid = rep.get("json_valid")
    else:
        support = list(getattr(rep, "support_bullets", []) or [])
        oppose = list(getattr(rep, "oppose_bullets", []) or [])
        notes = list(getattr(rep, "notes", []) or [])
        json_valid = getattr(rep, "json_valid", None)
    return {
        "replicate_idx": replicate_idx,
        "p_web": p_web,
        "support_bullets": [str(x) for x in support],
        "oppose_bullets": [str(x) for x in oppose],
        "notes": [str(x) for x in notes],
        "json_valid": bool(json_valid) if json_valid is not None else None,
    }
