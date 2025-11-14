from __future__ import annotations

import time
from typing import Dict

from heretix.ratelimit import RateLimiter

from .registry import register_wel_score_fn
from . import grok_xai as _grok


_XAI_RPS, _XAI_BURST = _grok._resolve_rate_limits()
_XAI_WEL_RATE_LIMITER = RateLimiter(rate_per_sec=_XAI_RPS, burst=_XAI_BURST)


def score_wel_bundle(
    *,
    instructions: str,
    bundle_text: str,
    model: str = "grok-4",
    max_output_tokens: int = 768,
) -> Dict[str, object]:
    """Call the Grok adapter for a WEL snippet bundle."""

    client = _grok._build_client()
    warnings: list[str] = []

    payload = {
        "model": model,
        "instructions": instructions,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": bundle_text},
                ],
            }
        ],
        "max_output_tokens": max_output_tokens or 768,
        "temperature": 0.0,
    }

    _XAI_WEL_RATE_LIMITER.acquire()
    t0 = time.time()
    try:
        resp = client.responses.create(**payload)
    except Exception:
        warnings.append("grok_chat_completion_fallback")
        resp = _grok._call_chat_completion(
            client,
            instructions=instructions,
            user_text=bundle_text,
            model=model,
            max_output_tokens=max_output_tokens or 768,
        )
    latency_ms = int((time.time() - t0) * 1000)

    text = _grok._collect_text_from_output(resp)
    if not text:
        raise RuntimeError("Grok WEL adapter returned no text payload")

    provider_model_id = getattr(resp, "model", None) or model
    response_id = getattr(resp, "id", None) or getattr(resp, "response_id", None)
    created_ts = float(getattr(resp, "created", time.time()))

    return {
        "text": text,
        "warnings": warnings,
        "meta": {
            "provider_model_id": provider_model_id,
            "response_id": response_id,
            "created": created_ts,
        },
        "timing": {"latency_ms": latency_ms},
    }


register_wel_score_fn(
    aliases=("grok-4", "grok-5", "xai:grok-4", "xai:grok-5", "grok"),
    fn=score_wel_bundle,
)
