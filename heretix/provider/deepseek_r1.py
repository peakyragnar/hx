from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict

import requests

from heretix.ratelimit import RateLimiter

from .config import get_rate_limits
from .registry import register_score_fn
from .schema_text import RPL_SAMPLE_JSON_SCHEMA


_LOGGER = logging.getLogger(__name__)
_API_URL = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/chat/completions")


def _resolve_rate_limits() -> tuple[float, int]:
    try:
        rps, burst = get_rate_limits("deepseek", "deepseek-r1")
    except Exception:
        rps, burst = 0.5, 1
    try:
        env_rps = os.getenv("HERETIX_DEEPSEEK_RPS")
        if env_rps:
            rps = float(env_rps)
    except ValueError:
        pass
    try:
        env_burst = os.getenv("HERETIX_DEEPSEEK_BURST")
        if env_burst:
            burst = int(env_burst)
    except ValueError:
        pass
    if rps <= 0:
        rps = 0.5
    if burst <= 0:
        burst = 1
    return float(rps), int(burst)


_DEEPSEEK_RPS, _DEEPSEEK_BURST = _resolve_rate_limits()
_DEEPSEEK_RATE_LIMITER = RateLimiter(rate_per_sec=_DEEPSEEK_RPS, burst=_DEEPSEEK_BURST)


def _schema_instructions() -> str:
    return RPL_SAMPLE_JSON_SCHEMA


def _resolve_api_key() -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("Set DEEPSEEK_API_KEY to call DeepSeek.")
    return api_key


def score_claim(
    *,
    claim: str,
    system_text: str,
    user_template: str,
    paraphrase_text: str,
    model: str = "deepseek-r1",
    max_output_tokens: int = 2048,
) -> Dict[str, Any]:
    """Call DeepSeek's OpenAI-compatible API for RPL sampling."""

    paraphrased = paraphrase_text.replace("{CLAIM}", claim)
    user_text = f"{paraphrased}\n\n" + user_template.replace("{CLAIM}", claim)
    instructions = system_text + "\n\n" + _schema_instructions()
    prompt_sha256 = hashlib.sha256((instructions + "\n\n" + user_text).encode("utf-8")).hexdigest()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.0,
        "max_tokens": max_output_tokens or 2048,
    }

    headers = {
        "Authorization": f"Bearer {_resolve_api_key()}",
        "Content-Type": "application/json",
    }

    _DEEPSEEK_RATE_LIMITER.acquire()
    t0 = time.time()
    response = requests.post(_API_URL, json=payload, headers=headers, timeout=60)
    try:
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"DeepSeek request failed: {exc}") from exc

    latency_ms = int((time.time() - t0) * 1000)

    text = None
    choices = data.get("choices") or []
    for choice in choices:
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            text = content
            break
    try:
        raw_obj = json.loads(text) if text else {}
        if not isinstance(raw_obj, dict):
            raw_obj = {}
    except Exception:
        raw_obj = {}

    provider_model_id = data.get("model") or model
    response_id = data.get("id")
    meta = {
        "provider_model_id": provider_model_id,
        "prompt_sha256": prompt_sha256,
        "response_id": response_id,
        "created": float(time.time()),
    }

    return {
        "raw": raw_obj,
        "meta": meta,
        "timing": {"latency_ms": latency_ms},
    }


register_score_fn(
    aliases=(
        "deepseek",
        "deepseek-r1",
        "deepseek-r1-default",
        "deepseek:r1",
    ),
    fn=score_claim,
)
