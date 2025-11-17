from __future__ import annotations

import os
import time
from typing import Any, Dict

from openai import OpenAI

from heretix.ratelimit import RateLimiter

try:
    from .config import get_rate_limits  # type: ignore
except Exception:  # pragma: no cover - optional dependency guard
    get_rate_limits = None  # type: ignore

from .registry import register_expl_adapter
from .telemetry import LLMTelemetry


def _extract_output_text(resp: Any) -> str | None:
    if hasattr(resp, "output_text") and resp.output_text:
        return str(resp.output_text)
    try:
        for item in getattr(resp, "output", []) or []:
            if getattr(item, "type", None) != "message":
                continue
            for part in getattr(item, "content", []) or []:
                if getattr(part, "type", None) == "output_text" and getattr(part, "text", None):
                    return str(part.text)
    except Exception:
        pass
    return None


def _extract_usage(resp: Any) -> tuple[int, int]:
    tokens_in = 0
    tokens_out = 0
    usage = getattr(resp, "usage", None)
    if usage:
        tokens_in = int(
            getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0)) or 0
        )
        tokens_out = int(
            getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0)) or 0
        )
    return tokens_in, tokens_out


def write_simple_expl(
    *,
    instructions: str,
    user_text: str,
    model: str = "gpt-5",
    max_output_tokens: int = 640,
) -> Dict[str, object]:
    """Call GPT-5 to produce a SimpleExplV1 payload."""

    _OPENAI_EXPL_RATE_LIMITER.acquire()
    client = OpenAI()
    t0 = time.time()
    try:
        resp = client.responses.create(
            model=model,
            instructions=instructions,
            input=[{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
            max_output_tokens=max_output_tokens,
            reasoning={"effort": "minimal"},
        )
    except Exception as exc:
        if "reasoning" in str(exc).lower():
            resp = client.responses.create(
                model=model,
                instructions=instructions,
                input=[{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
                max_output_tokens=max_output_tokens,
            )
        else:
            raise
    latency_ms = int((time.time() - t0) * 1000)

    payload = _extract_output_text(resp)
    if payload is None:
        raise RuntimeError("No response payload received from GPT-5 explanation adapter")

    provider_model_id = getattr(resp, "model", model)
    response_id = getattr(resp, "id", None) or getattr(resp, "response_id", None)
    created_ts = float(getattr(resp, "created", time.time()))
    tokens_in, tokens_out = _extract_usage(resp)
    telemetry = LLMTelemetry(
        provider="openai",
        logical_model=str(model),
        api_model=str(provider_model_id) if provider_model_id else None,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
    )

    return {
        "text": payload,
        "warnings": [],
        "meta": {
            "provider_model_id": provider_model_id,
            "response_id": response_id,
            "created": created_ts,
        },
        "timing": {"latency_ms": latency_ms},
        "telemetry": telemetry,
    }


if get_rate_limits is not None:
    try:
        _rps, _burst = get_rate_limits("openai", "gpt-5")
    except Exception:  # pragma: no cover - fall back to env/defaults
        _rps = float(os.getenv("HERETIX_OPENAI_RPS", "2"))
        _burst = int(os.getenv("HERETIX_OPENAI_BURST", "2"))
else:
    _rps = float(os.getenv("HERETIX_OPENAI_RPS", "2"))
    _burst = int(os.getenv("HERETIX_OPENAI_BURST", "2"))

_OPENAI_EXPL_RATE_LIMITER = RateLimiter(rate_per_sec=float(_rps), burst=int(_burst))

register_expl_adapter(
    aliases=(
        "gpt-5",
        "gpt5-default",
        "openai-gpt5",
        "openai:gpt-5",
        "openai",
        "narrator",
        "simple-expl",
        "simple-expl-gpt5",
    ),
    fn=write_simple_expl,
)
