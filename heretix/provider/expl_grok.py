from __future__ import annotations

import os
import time
from typing import Any, Dict

from openai import OpenAI

from heretix.ratelimit import RateLimiter

from .config import get_rate_limits
from .registry import register_expl_adapter
from .telemetry import LLMTelemetry

_DEFAULT_API_BASE = "https://api.x.ai/v1"


def _resolve_rate_limits() -> tuple[float, int]:
    try:
        rps, burst = get_rate_limits("xai", "grok-4")
    except Exception:
        rps, burst = 1.0, 2
    try:
        env_rps = float(os.getenv("HERETIX_XAI_RPS", "").strip() or rps)
        rps = env_rps if env_rps > 0 else rps
    except ValueError:
        pass
    try:
        env_burst = int(os.getenv("HERETIX_XAI_BURST", "").strip() or burst)
        burst = env_burst if env_burst > 0 else burst
    except ValueError:
        pass
    return float(rps), int(burst)


_GROK_RPS, _GROK_BURST = _resolve_rate_limits()
_GROK_RATE_LIMITER = RateLimiter(rate_per_sec=_GROK_RPS, burst=_GROK_BURST)


def _build_client() -> OpenAI:
    api_key = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
    if not api_key:
        raise RuntimeError("Set XAI_API_KEY or GROK_API_KEY for Grok narration.")
    base_url = os.getenv("XAI_API_BASE") or os.getenv("GROK_API_BASE") or _DEFAULT_API_BASE
    return OpenAI(api_key=api_key, base_url=base_url)


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


def write_simple_expl_grok(
    *,
    instructions: str,
    user_text: str,
    model: str = "grok-4",
    max_output_tokens: int = 640,
) -> Dict[str, object]:
    """Call the Grok API to produce a SimpleExplV1 payload."""

    _GROK_RATE_LIMITER.acquire()
    client = _build_client()
    t0 = time.time()
    resp = client.responses.create(
        model=model,
        instructions=instructions,
        input=[{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
        max_output_tokens=max_output_tokens,
        temperature=0.0,
    )
    latency_ms = int((time.time() - t0) * 1000)

    payload = _extract_output_text(resp)
    if payload is None:
        raise RuntimeError("No Grok explanation payload received")

    provider_model_id = getattr(resp, "model", model)
    response_id = getattr(resp, "id", None) or getattr(resp, "response_id", None)
    tokens_in, tokens_out = _extract_usage(resp)
    telemetry = LLMTelemetry(
        provider="xai",
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
        },
        "timing": {"latency_ms": latency_ms},
        "telemetry": telemetry,
    }


register_expl_adapter(
    aliases=("grok-4", "grok-4-latest", "grok-5", "grok-5-latest", "grok", "xai"),
    fn=write_simple_expl_grok,
)
