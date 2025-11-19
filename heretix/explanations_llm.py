from __future__ import annotations

from typing import Any, Dict, Optional

from heretix.prompts.prompt_builder import build_simple_expl_prompt
from heretix.provider.json_utils import parse_schema_from_text
from heretix.provider.registry import get_expl_adapter
from heretix.schemas import SimpleExplV1


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if num != num:  # NaN guard
        return default
    return num


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bucket_stability(stability: Any) -> str:
    score = _safe_float(stability, default=0.0)
    if score >= 0.65:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def _bucket_precision(ci_width: float) -> str:
    if ci_width <= 0.2:
        return "narrow"
    if ci_width <= 0.35:
        return "medium"
    return "wide"


def _bucket_docs(count: float) -> str:
    if count <= 0:
        return "none"
    if count <= 3:
        return "few"
    return "several"


def _describe_paraphrases(k_val: Optional[int]) -> str:
    if not k_val or k_val <= 1:
        return "one wording"
    if k_val <= 3:
        return "a couple of wordings"
    if k_val <= 6:
        return "several wordings"
    return "many wordings"


def _describe_replicates(r_val: Optional[int]) -> str:
    if not r_val or r_val <= 1:
        return "one sample per wording"
    if r_val == 2:
        return "two samples per wording"
    if r_val <= 4:
        return "multiple samples per wording"
    return "many samples per wording"


def _ci_bounds(block: Optional[Dict[str, Any]]) -> tuple[float, float]:
    if block is None:
        return 0.0, 0.0
    ci_vals = block.get("ci95")
    if isinstance(ci_vals, (list, tuple)) and len(ci_vals) >= 2:
        return _safe_float(ci_vals[0], default=0.0), _safe_float(ci_vals[1], default=0.0)
    return _safe_float(block.get("ci_lo"), default=0.0), _safe_float(block.get("ci_hi"), default=0.0)


def _summarize_sampling(sampling: Optional[Dict[str, Any]]) -> Dict[str, str]:
    sampling = sampling or {}
    k_val = _to_int(sampling.get("K") or sampling.get("k"))
    r_val = _to_int(sampling.get("R") or sampling.get("r"))
    summary = {
        "paraphrases": _describe_paraphrases(k_val),
        "replicates": _describe_replicates(r_val),
    }
    t_val = _to_int(sampling.get("T") or sampling.get("t"))
    if t_val:
        summary["templates"] = "many templates" if t_val >= 8 else ("several templates" if t_val >= 4 else "few templates")
    return summary


def _summarize_web(
    *,
    mode: str,
    prior_prob: float,
    combined_block: Dict[str, Any],
    web_block: Optional[Dict[str, Any]],
    weights: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    attempted = mode == "web_informed"
    combined_prob = _safe_float(combined_block.get("p"), default=prior_prob)
    enabled = bool(web_block) and attempted
    summary: Dict[str, Any] = {
        "attempted": attempted,
        "enabled": bool(enabled),
        "shift": "no_change",
        "shift_phrase": "prior-only run",
        "docs_bucket": "none",
        "docs_summary": "no usable articles",
    }

    if not attempted:
        return summary

    if not enabled:
        summary["shift_phrase"] = "web lens found no usable articles"
        summary["docs_bucket"] = "none"
        summary["docs_summary"] = "no usable articles"
        return summary

    evidence = web_block.get("evidence") if isinstance(web_block, dict) else None
    doc_count = 0.0
    if isinstance(evidence, dict):
        doc_count = _safe_float(evidence.get("n_docs"), default=0.0)
    summary["docs_bucket"] = _bucket_docs(doc_count)
    if summary["docs_bucket"] == "few":
        summary["docs_summary"] = "a few usable articles"
    elif summary["docs_bucket"] == "several":
        summary["docs_summary"] = "several usable articles"

    delta = combined_prob - prior_prob
    if abs(delta) < 0.01:
        shift = "no_change"
        phrase = "no real change from prior"
    elif delta > 0:
        shift = "up"
        phrase = "nudged upward slightly" if delta < 0.05 else "nudged upward noticeably"
    else:
        shift = "down"
        phrase = "nudged downward slightly" if delta > -0.05 else "nudged downward noticeably"

    summary["shift"] = shift
    summary["shift_phrase"] = phrase

    weight_web = combined_block.get("weight_web")
    if weight_web is None and weights:
        weight_web = weights.get("w_web")
    summary["weight_web"] = _safe_float(weight_web, default=0.0)
    return summary


def _summarize_warnings(warning_counts: Optional[Dict[str, int]]) -> Optional[Dict[str, Any]]:
    if not warning_counts:
        return None
    normalized: Dict[str, int] = {}
    total = 0
    for key, value in warning_counts.items():
        try:
            val = int(value)
        except (TypeError, ValueError):
            continue
        normalized[str(key)] = val
        total += val
    return {"has_warnings": total > 0, "counts": normalized} if normalized else None


def _has_positive_warning(warning_counts: Optional[Dict[str, int]]) -> bool:
    if not warning_counts:
        return False
    for value in warning_counts.values():
        try:
            if int(value) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _build_context_payload(
    *,
    claim: str,
    mode: str,
    prior_block: Dict[str, Any],
    combined_block: Dict[str, Any],
    web_block: Optional[Dict[str, Any]],
    warning_counts: Optional[Dict[str, int]],
    sampling: Optional[Dict[str, Any]],
    weights: Optional[Dict[str, Any]],
) -> str:
    prior_prob = _safe_float(prior_block.get("p"), default=0.5)
    combined_prob = _safe_float(combined_block.get("p"), default=prior_prob)
    label = str(combined_block.get("label") or "Uncertain")
    ci_lo, ci_hi = _ci_bounds(combined_block or prior_block)
    ci_width = max(ci_hi - ci_lo, 0.0)

    web_summary = _summarize_web(
        mode=mode,
        prior_prob=prior_prob,
        combined_block=combined_block,
        web_block=web_block,
        weights=weights,
    )
    confidence = {
        "stability_level": _bucket_stability(prior_block.get("stability")),
        "precision_level": _bucket_precision(ci_width),
        "compliance_ok": not _has_positive_warning(warning_counts),
    }
    sampling_summary = _summarize_sampling(sampling)
    warning_summary = _summarize_warnings(warning_counts)

    prob_pct = int(round(combined_prob * 100))
    prob_phrase = f"~{prob_pct}%"
    lines = [
        f"Mode: {mode}",
        f"Verdict: {label} (probability {prob_phrase})",
        f"Stability: {confidence['stability_level']} · Precision: {confidence['precision_level']} · Compliance clean: {confidence['compliance_ok']}",
        f"Sampling: {sampling_summary.get('paraphrases')} with {sampling_summary.get('replicates')}",
    ]

    if mode == "baseline":
        lines.append("Web lens: skipped (prior-only run).")
    else:
        if web_summary["enabled"]:
            lines.append(
                f"Web lens: {web_summary['docs_summary']} and {web_summary['shift_phrase']}."
            )
        else:
            lines.append("Web lens: attempted but no usable articles, so it mirrored the prior.")

    if warning_summary and warning_summary.get("has_warnings"):
        lines.append(f"Warnings: {warning_summary['counts']}.")

    return "\n".join(lines)


def generate_simple_expl_llm(
    *,
    claim: str,
    mode: str,
    prior_block: Dict[str, Any],
    combined_block: Dict[str, Any],
    web_block: Optional[Dict[str, Any]],
    warning_counts: Optional[Dict[str, int]],
    sampling: Optional[Dict[str, Any]],
    weights: Optional[Dict[str, Any]],
    model: str = "gpt-5",
    provider: Optional[str] = None,
    style: str = "narrator",
    max_output_tokens: int = 640,
) -> Dict[str, Any]:
    """Generate SimpleExplV1 via the explanation adapter."""

    context = _build_context_payload(
        claim=claim,
        mode=mode,
        prior_block=prior_block,
        combined_block=combined_block,
        web_block=web_block,
        warning_counts=warning_counts,
        sampling=sampling,
        weights=weights,
    )
    prompt = build_simple_expl_prompt(provider or style, claim=claim, context=context, style=style)
    adapter = get_expl_adapter(model)
    result = adapter(
        instructions=prompt.system,
        user_text=prompt.user,
        model=model,
        max_output_tokens=max_output_tokens,
    )
    if not isinstance(result, dict):
        raise TypeError("Explanation adapter must return a dict payload")
    payload = result.get("text")
    _, canonical, warnings = parse_schema_from_text(payload, SimpleExplV1)
    if canonical is None:
        snippet = (payload or "")[:400] if isinstance(payload, str) else str(payload)[:400]
        raise ValueError(f"Explanation adapter output failed SimpleExplV1 validation: {snippet}")
    telemetry_obj = result.get("telemetry")
    if hasattr(telemetry_obj, "model_dump"):
        telemetry_payload = telemetry_obj.model_dump()
    elif isinstance(telemetry_obj, dict):
        telemetry_payload = dict(telemetry_obj)
    else:
        telemetry_payload = None
    return {
        "simple_expl": canonical,
        "warnings": warnings,
        "telemetry": telemetry_payload,
    }


__all__ = ["generate_simple_expl_llm"]
