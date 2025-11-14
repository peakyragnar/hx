from __future__ import annotations

import json
from typing import Any, Dict, Optional

from heretix.prompts.prompt_builder import build_simple_expl_prompt
from heretix.provider.json_utils import parse_schema_from_text
from heretix.provider.registry import get_expl_adapter
from heretix.schemas import SimpleExplV1


def _clean_value(value: Any) -> Any:
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return value
    if isinstance(value, dict):
        return {str(k): _clean_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_value(v) for v in value]
    return value


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
    context: Dict[str, Any] = {
        "claim": claim,
        "mode": mode,
        "prior": _clean_value(prior_block),
        "combined": _clean_value(combined_block),
        "warning_counts": _clean_value(warning_counts or {}),
        "sampling_plan": _clean_value(sampling or {}),
        "weights": _clean_value(weights or {}),
    }
    if web_block:
        context["web"] = {
            "enabled": True,
            **_clean_value(web_block),
        }
    else:
        context["web"] = {"enabled": False}
    return json.dumps(context, indent=2, ensure_ascii=False)


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
    prompt = build_simple_expl_prompt(style, claim=claim, context=context)
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
        raise ValueError("Explanation adapter output failed SimpleExplV1 validation")
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
