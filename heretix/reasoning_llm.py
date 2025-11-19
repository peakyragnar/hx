from __future__ import annotations

from typing import Any, Dict, Optional

from heretix.prompts.prompt_builder import build_reasoning_prompt
from heretix.provider.registry import get_expl_adapter


def _ensure_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def generate_reasoning_paragraph(
    *,
    claim: str,
    verdict: str,
    probability_text: str,
    context: str,
    model: str = "gpt-5",
    provider: Optional[str] = None,
    max_output_tokens: int = 320,
) -> Dict[str, Any]:
    """Produce a short reasoning paragraph for the verdict."""

    prompt = build_reasoning_prompt(
        provider or "narrator",
        claim=claim,
        verdict=verdict,
        probability_text=probability_text,
        context=context,
    )
    adapter = get_expl_adapter(model)
    result = adapter(
        instructions=prompt.system,
        user_text=prompt.user,
        model=model,
        max_output_tokens=max_output_tokens,
    )
    if not isinstance(result, dict):
        raise TypeError("Reasoning adapter must return a dict payload")

    text = _ensure_text(result.get("text"))
    if not text:
        raise ValueError("Reasoning adapter returned an empty response")

    telemetry_obj = result.get("telemetry")
    if hasattr(telemetry_obj, "model_dump"):
        telemetry_payload = telemetry_obj.model_dump()
    elif isinstance(telemetry_obj, dict):
        telemetry_payload = dict(telemetry_obj)
    else:
        telemetry_payload = None

    return {
        "reasoning": text,
        "telemetry": telemetry_payload,
        "warnings": result.get("warnings") or [],
    }


__all__ = ["generate_reasoning_paragraph"]
