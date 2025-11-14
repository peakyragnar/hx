from __future__ import annotations

import time
from typing import Dict

import requests

from heretix.ratelimit import RateLimiter

from .telemetry import LLMTelemetry
from .registry import register_wel_score_fn
from . import gemini_google as _gemini


_GEMINI_RPS, _GEMINI_BURST = _gemini._resolve_rate_limits()
_GEMINI_WEL_RATE_LIMITER = RateLimiter(rate_per_sec=_GEMINI_RPS, burst=_GEMINI_BURST)


def score_wel_bundle(
    *,
    instructions: str,
    bundle_text: str,
    model: str = "gemini25-default",
    max_output_tokens: int = 768,
) -> Dict[str, object]:
    """Call Google Gemini to score a WEL snippet bundle."""

    api_model = _gemini._resolve_api_model(model)
    api_key = _gemini._resolve_api_key()
    payload = {
        "system_instruction": {"role": "system", "parts": [{"text": instructions}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": bundle_text}],
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0,
            "max_output_tokens": max_output_tokens or 768,
        },
    }

    url = f"{_gemini._API_BASE}/models/{api_model}:generateContent"

    _GEMINI_WEL_RATE_LIMITER.acquire()
    t0 = time.time()
    response = requests.post(url, params={"key": api_key}, json=payload, timeout=60)
    try:
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"Gemini WEL request failed: {exc}") from exc
    latency_ms = int((time.time() - t0) * 1000)

    text = _gemini._extract_text(data)
    if not text:
        raise RuntimeError("Gemini WEL adapter returned no candidate text")

    provider_model_id = data.get("model") or api_model
    response_id = data.get("responseId")
    created_ts = float(time.time())
    tokens_in, tokens_out = _gemini._usage_counts(data)
    telemetry = LLMTelemetry(
        provider="google",
        logical_model=str(model),
        api_model=str(provider_model_id) if provider_model_id else None,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
    )

    return {
        "text": text,
        "warnings": [],
        "meta": {
            "provider_model_id": provider_model_id,
            "response_id": response_id,
            "created": created_ts,
        },
        "timing": {"latency_ms": latency_ms},
        "telemetry": telemetry,
    }


register_wel_score_fn(
    aliases=("gemini", "gemini-2.5", "gemini25-default", "google:gemini-2.5", "google"),
    fn=score_wel_bundle,
)
