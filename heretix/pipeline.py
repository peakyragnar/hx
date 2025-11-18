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
from heretix.provider.utils import infer_provider_from_model
from heretix.constants import SCHEMA_VERSION


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
    reasoning_text: Optional[str] = None


logger = logging.getLogger(__name__)

_CACHE_HIT_THRESHOLD = 0.999


def _should_generate_llm_narration(
    use_mock: bool,
    combined_block: Optional[Dict[str, Any]],
    cache_hit_rate: float,
) -> bool:
    """Return True if we should call live narration helpers."""

    if use_mock:
        return False
    if combined_block is None:
        return False
    return cache_hit_rate < _CACHE_HIT_THRESHOLD


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

    provider_id = result.get("provider") or cfg.provider or infer_provider_from_model(cfg.model)
    logical_model_value = result.get("logical_model", result.get("model", cfg.model))
    schema_version = result.get("schema_version", SCHEMA_VERSION)
    tokens_in = result.get("tokens_in")
    tokens_out = result.get("tokens_out")
    cost_usd = result.get("cost_usd")

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
    _assign(check, check_updates, "provider", provider_id)
    _assign(check, check_updates, "logical_model", cfg.logical_model or logical_model_value)
    _assign(check, check_updates, "prompt_version", result.get("prompt_version", cfg.prompt_version))
    _assign(check, check_updates, "schema_version", schema_version)
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

    _assign(check, check_updates, "was_cached", cache_hit_rate >= _CACHE_HIT_THRESHOLD)
    provider_model_value = result.get("provider_model_id") or result.get("model", cfg.model)
    _assign(check, check_updates, "provider_model_id", provider_model_value)
    _assign(check, check_updates, "tokens_in", int(tokens_in) if tokens_in is not None else None)
    _assign(check, check_updates, "tokens_out", int(tokens_out) if tokens_out is not None else None)
    _assign(check, check_updates, "cost_usd", float(cost_usd) if cost_usd is not None else None)
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
    reasoning_text: Optional[str] = None
    reasoning_evidence = _collect_reasoning_evidence(normalized_reps)

    # Backend-owned Simple View explanation
    simple_expl: Optional[Dict[str, Any]] = None
    narration_allowed = _should_generate_llm_narration(
        use_mock,
        combined_block_payload,
        cache_hit_rate,
    )
    resolved_model_value = result.get("resolved_logical_model", logical_model_value)
    run_warning_counts = result.get("warning_counts")
    if narration_allowed:
        try:
            from heretix.explanations_llm import generate_simple_expl_llm

            llm_result = generate_simple_expl_llm(
                claim=cfg.claim or "",
                mode=mode,
                prior_block=prior_block_payload,
                combined_block=combined_block_payload,
                web_block=sanitized_web_block if mode == "web_informed" else None,
                warning_counts=run_warning_counts or (
                    (sanitized_web_block or {}).get("warning_counts") if sanitized_web_block else None
                ),
                sampling=sampling,
                weights=weights_payload,
                model=resolved_model_value or cfg.model,
                provider=provider_id,
            )
            simple_expl = llm_result["simple_expl"]
        except Exception:  # pragma: no cover
            logger.exception("Failed to generate LLM narration for run %s", run_id)
            simple_expl = None

    if narration_allowed:
        try:
            from heretix.reasoning_llm import generate_reasoning_paragraph

            verdict_label = str(combined_block_payload.get("label") or "Uncertain")
            combined_prob_value = float(combined_block_payload.get("p", prior_p))
            probability_text = f"{int(round(max(0.0, min(1.0, combined_prob_value)) * 100))}%"
            context_text = _build_reasoning_context(
                mode=mode,
                stability_score=stability_score,
                ci_width=ci_width,
                evidence_lines=reasoning_evidence,
            )
            reasoning_result = generate_reasoning_paragraph(
                claim=cfg.claim or "",
                verdict=verdict_label,
                probability_text=probability_text,
                context=context_text,
                model=resolved_model_value or cfg.model,
                provider=provider_id,
            )
            reasoning_text = reasoning_result.get("reasoning")
        except Exception:  # pragma: no cover
            logger.exception("Failed to generate reasoning paragraph for run %s", run_id)
            reasoning_text = None

    if simple_expl is None:
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

    simple_expl = _normalize_simple_expl_payload(simple_expl)
    if reasoning_text and simple_expl:
        paragraphs = list(simple_expl.get("body_paragraphs", []))
        if reasoning_text not in paragraphs:
            paragraphs = [reasoning_text] + paragraphs
        else:
            paragraphs = [reasoning_text] + [p for p in paragraphs if p != reasoning_text]
        simple_expl["body_paragraphs"] = paragraphs[:3]
        simple_expl["reasoning"] = reasoning_text

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
        reasoning_text=reasoning_text,
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


def _normalize_simple_expl_payload(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not payload:
        return None

    def _clean_list(values: Any) -> list[str]:
        cleaned: list[str] = []
        if not isinstance(values, (list, tuple)):
            return cleaned
        for value in values:
            if not isinstance(value, str):
                value = str(value)
            text = value.strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned

    title = str(payload.get("title") or "Why this verdict looks this way").strip()
    summary = str(payload.get("summary") or "").strip()
    paragraphs = []
    bullets = []

    if "body_paragraphs" in payload or "bullets" in payload:
        paragraphs = _clean_list(payload.get("body_paragraphs"))
        bullets = _clean_list(payload.get("bullets"))
    else:
        legacy_lines = _clean_list(payload.get("lines"))
        bullets = legacy_lines[:3]
        if summary:
            paragraphs = [summary]
        elif legacy_lines:
            paragraphs = [legacy_lines[0]]

    if not paragraphs:
        paragraphs = ["This verdict relies on the model's prior knowledge."]
    normalized = {
        "title": title or "Why this verdict looks this way",
        "body_paragraphs": paragraphs[:3],
        "bullets": bullets[:4],
    }
    normalized["summary"] = summary or paragraphs[0]
    normalized["lines"] = bullets[:4] if bullets else paragraphs[:3]
    return normalized


def _collect_reasoning_evidence(reps: list[Dict[str, Any]], limit: int = 4) -> list[str]:
    lines: list[str] = []

    def _append(text: Any) -> None:
        if not text:
            return
        cleaned = " ".join(str(text).split()).strip()
        if not cleaned:
            return
        if cleaned not in lines:
            lines.append(cleaned)

    for rep in reps or []:
        for field in ("support_bullets", "oppose_bullets", "notes"):
            for item in rep.get(field, []) or []:
                _append(item)
                if len(lines) >= limit:
                    return lines
    return lines


def _bucket_stability_label(score: float) -> str:
    try:
        val = float(score)
    except (TypeError, ValueError):
        val = 0.0
    if val >= 0.65:
        return "high"
    if val >= 0.35:
        return "medium"
    return "low"


def _bucket_precision_label(ci_width: float) -> str:
    try:
        width = float(ci_width)
    except (TypeError, ValueError):
        width = 0.0
    if width <= 0.2:
        return "narrow"
    if width <= 0.35:
        return "moderate"
    return "wide"


def _build_reasoning_context(*, mode: str, stability_score: float, ci_width: float, evidence_lines: list[str]) -> str:
    lines = [
        f"Stability level: {_bucket_stability_label(stability_score)}",
        f"Precision band: {_bucket_precision_label(ci_width)}",
    ]
    if evidence_lines:
        lines.append("Evidence snippets:")
        for item in evidence_lines:
            lines.append(f"- {item}")
    else:
        lines.append("Evidence snippets: (not available)")
    return "\n".join(lines)
def _get_or_create_check(session: Session, run_id: str, env: str) -> Check:
    check = session.scalar(select(Check).where(Check.run_id == run_id))
    if check is None:
        check = Check(run_id=run_id, env=env)
        session.add(check)
    return check


def _assign(check: Check, updates: Dict[str, Any], field: str, value: Any) -> None:
    updates[field] = value
    setattr(check, field, value)
