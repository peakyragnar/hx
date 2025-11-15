from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Optional

import requests

from heretix.ratelimit import RateLimiter

from .config import get_rate_limits, load_provider_capabilities
from .json_utils import parse_schema_from_text
from .registry import register_score_fn
from .schema_text import RPL_SAMPLE_JSON_SCHEMA
from .telemetry import LLMTelemetry
from heretix.schemas import RPLSampleV1


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


def _resolve_api_model(logical_model: str) -> str:
    try:
        caps = load_provider_capabilities()
    except Exception as exc:
        _LOGGER.debug("Unable to load provider capabilities: %s", exc)
        caps = {}
    record = caps.get("deepseek") if isinstance(caps, dict) else None
    if record and logical_model in record.api_model_map:
        return record.api_model_map[logical_model]
    return logical_model


def _usage_counts(data: Dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage") or {}
    tokens_in = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    tokens_out = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    return tokens_in, tokens_out


def _format_http_error(response: Optional[requests.Response]) -> str:
    if response is None:
        return "no response payload"
    detail: Optional[str] = None
    try:
        data = response.json()
        if isinstance(data, dict):
            error_obj = data.get("error")
            if isinstance(error_obj, dict):
                message = error_obj.get("message")
                error_type = error_obj.get("type")
                detail = str(message or error_type)
            if not detail:
                detail = json.dumps(data)[:500]
    except ValueError:
        pass
    if not detail:
        text = (response.text or "").strip()
        detail = text[:500] if text else "no body"
    return detail


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

    api_model = _resolve_api_model(model)

    payload = {
        "model": api_model,
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
    try:
        response = requests.post(_API_URL, json=payload, headers=headers, timeout=60)
    except requests.RequestException as exc:
        raise RuntimeError(f"DeepSeek HTTP request failed: {exc}") from exc
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else response.status_code
        detail = _format_http_error(exc.response or response)
        raise RuntimeError(f"DeepSeek request failed (HTTP {status}): {detail}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        snippet = (response.text or "").strip()[:500]
        raise RuntimeError(f"DeepSeek request returned non-JSON payload: {snippet}") from exc

    latency_ms = int((time.time() - t0) * 1000)

    text = None
    choices = data.get("choices") or []
    for choice in choices:
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            text = content
            break
    raw_obj, sample_payload, warnings = parse_schema_from_text(text, RPLSampleV1)

    provider_model_id = data.get("model") or api_model
    response_id = data.get("id")
    meta = {
        "provider_model_id": provider_model_id,
        "prompt_sha256": prompt_sha256,
        "response_id": response_id,
        "created": float(time.time()),
    }
    tokens_in, tokens_out = _usage_counts(data)
    telemetry = LLMTelemetry(
        provider="deepseek",
        logical_model=str(model),
        api_model=str(provider_model_id) if provider_model_id else None,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
    )

    return {
        "raw": raw_obj,
        "sample": sample_payload,
        "warnings": warnings,
        "meta": meta,
        "timing": {"latency_ms": latency_ms},
        "telemetry": telemetry,
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
