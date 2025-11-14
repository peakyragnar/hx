from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Iterable, Optional

import requests

from heretix.ratelimit import RateLimiter

from .config import get_rate_limits, load_provider_capabilities
from .registry import register_score_fn
from .schema_text import RPL_SAMPLE_JSON_SCHEMA


_LOGGER = logging.getLogger(__name__)
_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _resolve_rate_limits() -> tuple[float, int]:
    try:
        rps, burst = get_rate_limits("google", "gemini25-default")
    except Exception:
        rps, burst = 1.0, 2
    rps_env = os.getenv("HERETIX_GEMINI_RPS")
    burst_env = os.getenv("HERETIX_GEMINI_BURST")
    try:
        if rps_env:
            rps = float(rps_env)
    except ValueError:
        pass
    try:
        if burst_env:
            burst = int(burst_env)
    except ValueError:
        pass
    if rps <= 0:
        rps = 1.0
    if burst <= 0:
        burst = 1
    return float(rps), int(burst)


_GEMINI_RPS, _GEMINI_BURST = _resolve_rate_limits()
_GEMINI_RATE_LIMITER = RateLimiter(rate_per_sec=_GEMINI_RPS, burst=_GEMINI_BURST)


def _schema_instructions() -> str:
    return RPL_SAMPLE_JSON_SCHEMA


def _resolve_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY (or GOOGLE_API_KEY) to call Gemini.")
    return api_key


def _resolve_api_model(logical_model: str) -> str:
    try:
        caps = load_provider_capabilities()
    except Exception as exc:
        _LOGGER.debug("Unable to load provider capabilities: %s", exc)
        caps = {}
    record = caps.get("google") if isinstance(caps, dict) else None
    if record and logical_model in record.api_model_map:
        return record.api_model_map[logical_model]
    return logical_model


def _extract_text(payload: Dict[str, Any]) -> Optional[str]:
    candidates = payload.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content")
        parts: Iterable[Any]
        if isinstance(content, dict):
            parts = content.get("parts", []) or []
        elif isinstance(content, list):
            parts = content
        else:
            parts = []
        for part in parts:
            if isinstance(part, dict):
                text_val = part.get("text") or part.get("data")
                if isinstance(text_val, str) and text_val.strip():
                    return text_val
        # Some variants return `candidate["text"]`
        text_val = candidate.get("text")
        if isinstance(text_val, str) and text_val.strip():
            return text_val
    return None


def _parse_json_text(text: Optional[str]) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        obj = json.loads(text)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def score_claim(
    *,
    claim: str,
    system_text: str,
    user_template: str,
    paraphrase_text: str,
    model: str = "gemini25-default",
    max_output_tokens: int = 1024,
) -> Dict[str, Any]:
    """Call Google Gemini to score a claim under a paraphrase."""

    paraphrased = paraphrase_text.replace("{CLAIM}", claim)
    user_text = f"{paraphrased}\n\n" + user_template.replace("{CLAIM}", claim)
    instructions = system_text + "\n\n" + _schema_instructions()
    prompt_sha256 = hashlib.sha256((instructions + "\n\n" + user_text).encode("utf-8")).hexdigest()

    api_model = _resolve_api_model(model)
    api_key = _resolve_api_key()
    payload = {
        "system_instruction": {"role": "system", "parts": [{"text": instructions}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_text}],
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0,
            "max_output_tokens": max_output_tokens or 1024,
        },
    }

    url = f"{_API_BASE}/models/{api_model}:generateContent"
    params = {"key": api_key}

    _GEMINI_RATE_LIMITER.acquire()
    t0 = time.time()
    response = requests.post(url, params=params, json=payload, timeout=60)
    try:
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"Gemini request failed: {exc}") from exc

    latency_ms = int((time.time() - t0) * 1000)

    raw_text = _extract_text(data)
    raw_obj = _parse_json_text(raw_text)

    provider_model_id = data.get("model") or api_model
    response_id = data.get("responseId")
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
        "gemini",
        "gemini-2.5",
        "gemini25-default",
        "google:gemini-2.5",
        "google",
    ),
    fn=score_claim,
)
