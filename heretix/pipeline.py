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
from heretix.verdicts import finalize_combined_block


@dataclass
class PipelineOptions:
    """Configuration knobs shared between CLI and API execution paths."""

    app_env: str = "local"
    wel_provider: str = "tavily"
    wel_model: str = "gpt-5"
    wel_docs: int = 16
    wel_replicates: int = 2
    wel_per_domain_cap: int = 3
    wel_recency_days: Optional[int] = None
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
    simple_expl: Optional[Dict[str, Any]] = None


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
    combined_block_payload: Dict[str, Any] = finalize_combined_block(
        {"p": prior_p, "ci95": list(prior_ci), "resolved": False},
        weight_web=0.0,
    )
    weights_payload: Optional[Dict[str, Any]] = None
    if mode != "web_informed":
        weights_payload = {"w_web": 0.0, "recency": 0.0, "strength": 0.0}
    wel_provenance: Optional[Dict[str, Any]] = None
    raw_replicates: list[Any] = []
    debug_votes: Optional[list[Dict[str, Any]]] = None
    artifact_record: Optional[ArtifactRecord] = None
    sanitized_web_block: Optional[Dict[str, Any]] = None

    if mode == "web_informed":
        if use_mock:
            web_block_payload = {
                "p": prior_p,
                "ci95": list(prior_ci),
                "evidence": {
                    "n_docs": 0.0,
                    "n_domains": 0.0,
                    "median_age_days": 0.0,
                    "n_confident_dates": 0.0,
                    "date_confident_rate": 0.0,
                    "dispersion": 0.0,
                    "json_valid_rate": 1.0,
                },
                "resolved": False,
                "resolved_truth": None,
                "resolved_reason": None,
                "resolved_citations": [],
                "support": None,
                "contradict": None,
                "domains": None,
            }
            weights_payload = {"w_web": 0.0, "recency": 0.0, "strength": 0.0}
            combined_block_payload = finalize_combined_block(
                {"p": prior_p, "ci95": list(prior_ci), "resolved": False},
                weight_web=weights_payload["w_web"],
            )
            wel_provenance = {
                "provider": options.wel_provider,
                "model": options.wel_model,
                "mock": True,
                "k_docs": options.wel_docs,
                "replicates": 0,
                "recency_days": options.wel_recency_days,
                "seed": cfg.seed,
            }
            sanitized_web_block = dict(web_block_payload)
            sanitized_web_block.pop("replicates", None)
        else:
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
                sanitized_web_block = dict(web_block_payload)
                sanitized_web_block.pop("replicates", None)
                sanitized_web_block.pop("resolved_debug_votes", None)
                if debug_votes is not None:
                    sanitized_web_block["resolved_debug_votes"] = debug_votes

    combined_block_payload = finalize_combined_block(
        combined_block_payload,
        weight_web=(weights_payload or {}).get("w_web"),
    )

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

    check = _get_or_create_check(session, run_id, options.app_env)
    check_updates: Dict[str, Any] = {}

    _assign(check, check_updates, "env", options.app_env)
    _assign(check, check_updates, "user_id", user_id)
    _assign(check, check_updates, "claim", cfg.claim)
    _assign(
        check,
        check_updates,
        "claim_hash",
        hashlib.sha256((cfg.claim or "").encode("utf-8")).hexdigest() if cfg.claim else None,
    )
    _assign(check, check_updates, "model", result.get("model", cfg.model))
    _assign(check, check_updates, "prompt_version", result.get("prompt_version", cfg.prompt_version))
    _assign(check, check_updates, "k", int(cfg.K))
    _assign(check, check_updates, "r", int(cfg.R))
    _assign(check, check_updates, "t", sampling.get("T"))
    _assign(check, check_updates, "b", cfg.B)
    _assign(check, check_updates, "seed", cfg.seed)
    bootstrap_seed_val = aggregation.get("bootstrap_seed")
    _assign(
        check,
        check_updates,
        "bootstrap_seed",
        int(bootstrap_seed_val) if bootstrap_seed_val is not None else None,
    )
    _assign(check, check_updates, "max_output_tokens", cfg.max_output_tokens)
    _assign(check, check_updates, "prob_true_rpl", float(aggregates.get("prob_true_rpl")))
    _assign(check, check_updates, "ci_lo", float(ci95[0]) if ci95 and ci95[0] is not None else None)
    _assign(check, check_updates, "ci_hi", float(ci95[1]) if ci95 and ci95[1] is not None else None)
    _assign(check, check_updates, "ci_width", ci_width)
    _assign(check, check_updates, "template_iqr_logit", aggregation.get("template_iqr_logit"))
    _assign(check, check_updates, "stability_score", stability_score)
    _assign(check, check_updates, "imbalance_ratio", aggregation.get("imbalance_ratio"))
    _assign(check, check_updates, "rpl_compliance_rate", rpl_compliance_rate)
    _assign(check, check_updates, "cache_hit_rate", cache_hit_rate)
    _assign(check, check_updates, "config_json", config_json)
    _assign(check, check_updates, "sampler_json", json.dumps({"K": cfg.K, "R": cfg.R, "T": sampling.get("T")}))
    _assign(check, check_updates, "counts_by_template_json", json.dumps(aggregation_counts))
    _assign(check, check_updates, "artifact_json_path", None)
    _assign(check, check_updates, "prompt_char_len_max", aggregation.get("prompt_char_len_max"))
    _assign(check, check_updates, "pqs", None)
    _assign(check, check_updates, "gate_compliance_ok", rpl_compliance_rate >= 0.98)
    _assign(check, check_updates, "gate_stability_ok", stability_score >= 0.25)
    _assign(check, check_updates, "gate_precision_ok", ci_width <= 0.30)
    _assign(check, check_updates, "pqs_version", None)
    _assign(check, check_updates, "mode", mode)
    _assign(check, check_updates, "p_prior", prior_p)
    _assign(check, check_updates, "ci_prior_lo", prior_ci[0])
    _assign(check, check_updates, "ci_prior_hi", prior_ci[1])
    _assign(check, check_updates, "stability_prior", stability_score)

    if web_block_payload:
        evidence = web_block_payload.get("evidence", {})
        _assign(check, check_updates, "p_web", float(web_block_payload["p"]))
        _assign(check, check_updates, "ci_web_lo", float(web_block_payload["ci95"][0]))
        _assign(check, check_updates, "ci_web_hi", float(web_block_payload["ci95"][1]))
        _assign(check, check_updates, "n_docs", int(evidence.get("n_docs", 0)))
        _assign(check, check_updates, "n_domains", int(evidence.get("n_domains", 0)))
        _assign(check, check_updates, "median_age_days", float(evidence.get("median_age_days", 0.0)))
        _assign(check, check_updates, "web_dispersion", float(evidence.get("dispersion", 0.0)))
        _assign(check, check_updates, "json_valid_rate", float(evidence.get("json_valid_rate", 0.0)))
        date_confident = evidence.get("date_confident_rate")
        confident_count = evidence.get("n_confident_dates")
        if date_confident is not None:
            _assign(check, check_updates, "date_confident_rate", float(date_confident))
        if confident_count is not None:
            _assign(check, check_updates, "n_confident_dates", float(confident_count))
    else:
        _assign(check, check_updates, "p_web", None)
        _assign(check, check_updates, "ci_web_lo", None)
        _assign(check, check_updates, "ci_web_hi", None)
        _assign(check, check_updates, "n_docs", None)
        _assign(check, check_updates, "n_domains", None)
        _assign(check, check_updates, "median_age_days", None)
        _assign(check, check_updates, "web_dispersion", None)
        _assign(check, check_updates, "json_valid_rate", None)
        _assign(check, check_updates, "date_confident_rate", None)
        _assign(check, check_updates, "n_confident_dates", None)

    if combined_block_payload:
        _assign(check, check_updates, "p_combined", float(combined_block_payload["p"]))
        _assign(check, check_updates, "ci_combined_lo", float(combined_block_payload["ci95"][0]))
        _assign(check, check_updates, "ci_combined_hi", float(combined_block_payload["ci95"][1]))
    else:
        _assign(check, check_updates, "p_combined", None)
        _assign(check, check_updates, "ci_combined_lo", None)
        _assign(check, check_updates, "ci_combined_hi", None)

    if weights_payload:
        _assign(check, check_updates, "w_web", float(weights_payload.get("w_web", 0.0)))
        _assign(check, check_updates, "recency_score", float(weights_payload.get("recency", 0.0)))
        _assign(check, check_updates, "strength_score", float(weights_payload.get("strength", 0.0)))
    else:
        _assign(check, check_updates, "w_web", None)
        _assign(check, check_updates, "recency_score", None)
        _assign(check, check_updates, "strength_score", None)

    if combined_block_payload and combined_block_payload.get("resolved"):
        _assign(check, check_updates, "resolved_flag", True)
        resolved_truth = combined_block_payload.get("resolved_truth")
        _assign(
            check,
            check_updates,
            "resolved_truth",
            bool(resolved_truth) if resolved_truth is not None else None,
        )
        _assign(check, check_updates, "resolved_reason", combined_block_payload.get("resolved_reason"))
        _assign(check, check_updates, "resolved_support", combined_block_payload.get("support"))
        _assign(check, check_updates, "resolved_contradict", combined_block_payload.get("contradict"))
        domains_val = combined_block_payload.get("domains")
        _assign(
            check,
            check_updates,
            "resolved_domains",
            int(domains_val) if domains_val is not None else None,
        )
        citations_val = combined_block_payload.get("resolved_citations")
        _assign(check, check_updates, "resolved_citations", json.dumps(citations_val) if citations_val is not None else None)
    else:
        _assign(check, check_updates, "resolved_flag", False if mode == "web_informed" else None)
        _assign(check, check_updates, "resolved_truth", None)
        _assign(check, check_updates, "resolved_reason", None)
        _assign(check, check_updates, "resolved_support", None)
        _assign(check, check_updates, "resolved_contradict", None)
        _assign(check, check_updates, "resolved_domains", None)
        _assign(check, check_updates, "resolved_citations", None)

    _assign(check, check_updates, "was_cached", cache_hit_rate >= 0.999)
    provider_model_value = result.get("provider_model_id") or result.get("model", cfg.model)
    _assign(check, check_updates, "provider_model_id", provider_model_value)
    _assign(check, check_updates, "anon_token", anon_token if user_id is None else None)
    _assign(check, check_updates, "created_at", now)
    _assign(check, check_updates, "finished_at", now)

    if mode == "web_informed" and web_block_payload:
        try:
            store = get_artifact_store()
            artifact_record = write_web_artifact(
                run_id=run_id,
                claim=cfg.claim,
                mode=mode,
                store=store,
                prior_block=prior_block_payload,
                web_block=sanitized_web_block or web_block_payload,
                combined_block=combined_block_payload,
                wel_provenance=wel_provenance,
                replicates=raw_replicates,
                debug_votes=debug_votes,
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("Failed to write web artifact for run %s: %s", run_id, exc)
            artifact_record = None

    if artifact_record:
        _assign(check, check_updates, "artifact_json_path", artifact_record.manifest_uri)

    normalized_reps = [_normalize_replica(rep) for rep in raw_replicates]

    # Backend-owned Simple View explanation
    simple_expl: Optional[Dict[str, Any]] = None
    if mode == "web_informed" and combined_block_payload is not None and (
        sanitized_web_block is not None or normalized_reps
    ):
        try:
            from heretix.simple_expl import compose_simple_expl

            simple_expl = compose_simple_expl(
                claim=cfg.claim or "",
                combined_p=float(combined_block_payload.get("p", prior_p)),
                web_block=sanitized_web_block,
                replicates=normalized_reps,
            )
        except Exception:  # pragma: no cover
            logger.exception("Failed to compose Simple View for run %s", run_id)
            simple_expl = None
    elif mode == "baseline":
        try:
            from heretix.simple_expl import compose_baseline_simple_expl

            simple_expl = compose_baseline_simple_expl(
                claim=cfg.claim or "",
                prior_p=prior_p,
                prior_ci=(prior_ci[0], prior_ci[1]),
                stability_score=stability_score,
                template_count=sampling.get("T") or aggregation.get("n_templates"),
                imbalance_ratio=aggregation.get("imbalance_ratio"),
            )
        except Exception:  # pragma: no cover
            logger.exception("Failed to compose baseline Simple View for run %s", run_id)
            simple_expl = None

    return PipelineArtifacts(
        result=result,
        prior_block=prior_block_payload,
        web_block=sanitized_web_block,
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
        simple_expl=simple_expl,
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
def _get_or_create_check(session: Session, run_id: str, env: str) -> Check:
    check = session.scalar(select(Check).where(Check.run_id == run_id))
    if check is None:
        check = Check(run_id=run_id, env=env)
        session.add(check)
    return check


def _assign(check: Check, updates: Dict[str, Any], field: str, value: Any) -> None:
    updates[field] = value
    setattr(check, field, value)
