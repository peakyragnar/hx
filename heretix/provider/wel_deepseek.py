from __future__ import annotations

import time
from typing import Dict

import requests

from heretix.ratelimit import RateLimiter

from .registry import register_wel_score_fn
from . import deepseek_r1 as _deepseek


_DEEPSEEK_RPS, _DEEPSEEK_BURST = _deepseek._resolve_rate_limits()
_DEEPSEEK_WEL_RATE_LIMITER = RateLimiter(rate_per_sec=_DEEPSEEK_RPS, burst=_DEEPSEEK_BURST)


def score_wel_bundle(
    *,
    instructions: str,
    bundle_text: str,
    model: str = "deepseek-r1",
    max_output_tokens: int = 1024,
) -> Dict[str, object]:
    """Call DeepSeek's API for a WEL snippet bundle."""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": bundle_text},
        ],
        "temperature": 0.0,
        "max_tokens": max_output_tokens or 1024,
    }

    headers = {
        "Authorization": f"Bearer {_deepseek._resolve_api_key()}",
        "Content-Type": "application/json",
    }

    _DEEPSEEK_WEL_RATE_LIMITER.acquire()
    t0 = time.time()
    response = requests.post(_deepseek._API_URL, json=payload, headers=headers, timeout=60)
    try:
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"DeepSeek WEL request failed: {exc}") from exc
    latency_ms = int((time.time() - t0) * 1000)

    choices = data.get("choices") or []
    text: str | None = None
    for choice in choices:
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            text = content
            break
    if not text:
        raise RuntimeError("DeepSeek WEL adapter returned no text")

    provider_model_id = data.get("model") or model
    response_id = data.get("id")
    created_ts = float(time.time())

    return {
        "text": text,
        "warnings": [],
        "meta": {
            "provider_model_id": provider_model_id,
            "response_id": response_id,
            "created": created_ts,
        },
        "timing": {"latency_ms": latency_ms},
    }


register_wel_score_fn(
    aliases=("deepseek", "deepseek-r1", "deepseek:r1", "deepseek-r1-default"),
    fn=score_wel_bundle,
)
