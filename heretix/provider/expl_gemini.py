from __future__ import annotations

import json
import os
import time
from typing import Any, Dict

import requests

from heretix.ratelimit import RateLimiter

from .config import get_rate_limits, load_provider_capabilities
from .registry import register_expl_adapter
from .telemetry import LLMTelemetry
from .json_utils import strip_markdown_json

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_OUTPUT = 640
_MAX_OUTPUT = 2048


def _resolve_rate_limits() -> tuple[float, int]:
    try:
        rps, burst = get_rate_limits("google", "gemini25-default")
    except Exception:
        rps, burst = 1.0, 2
    try:
        env_rps = float(os.getenv("HERETIX_GEMINI_RPS", "").strip() or rps)
        rps = env_rps if env_rps > 0 else rps
    except ValueError:
        pass
    try:
        env_burst = int(os.getenv("HERETIX_GEMINI_BURST", "").strip() or burst)
        burst = env_burst if env_burst > 0 else burst
    except ValueError:
        pass
    return float(rps), int(burst)


_GEMINI_RPS, _GEMINI_BURST = _resolve_rate_limits()
_GEMINI_RATE_LIMITER = RateLimiter(rate_per_sec=_GEMINI_RPS, burst=_GEMINI_BURST)


def _resolve_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Gemini API key is not configured.")
    return api_key


def _resolve_api_model(logical_model: str) -> str:
    try:
        caps = load_provider_capabilities()
    except Exception:
        caps = {}
    record = caps.get("google") if isinstance(caps, dict) else None
    if record and logical_model in record.api_model_map:
        return record.api_model_map[logical_model]
    return logical_model


def _extract_text(data: Dict[str, Any]) -> str | None:
    candidates = data.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") if isinstance(content, dict) else None
        if isinstance(parts, list):
            for part in parts:
                text_val = part.get("text") if isinstance(part, dict) else None
                if isinstance(text_val, str) and text_val.strip():
                    return text_val
        text_val = candidate.get("text")
        if isinstance(text_val, str) and text_val.strip():
            return text_val
    return None


def _usage_counts(data: Dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usageMetadata") or {}
    tokens_in = int(usage.get("promptTokenCount") or 0)
    tokens_out = int(usage.get("candidatesTokenCount") or usage.get("totalTokenCount") or 0)
    return tokens_in, tokens_out


def _effective_output_limit(requested: int | None) -> int:
    try:
        value = int(requested) if requested is not None else _DEFAULT_OUTPUT
    except (TypeError, ValueError):
        value = _DEFAULT_OUTPUT
    if value <= 0:
        value = _DEFAULT_OUTPUT
    if value < 1024:
        value = 1024
    return min(value, _MAX_OUTPUT)


def _format_http_error(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if isinstance(payload, dict):
        error_obj = payload.get("error")
        if isinstance(error_obj, dict):
            message = error_obj.get("message") or error_obj.get("status")
            if message:
                return str(message)
        if payload:
            return json.dumps(payload)[:400]
    text = (response.text or "").strip()
    return text[:400] if text else f"HTTP {response.status_code}"


_DEFAULT_EXPL_MODEL = os.getenv("HERETIX_GEMINI_EXPL_MODEL_DEFAULT", "gemini-2.0-flash")


def _resolve_expl_model(logical_model: str) -> str:
    override = os.getenv("HERETIX_GEMINI_EXPL_MODEL")
    if override:
        return override
    api_model = _resolve_api_model(logical_model)
    if "flash" in api_model.lower():
        return api_model
    return _DEFAULT_EXPL_MODEL


def write_simple_expl_gemini(
    *,
    instructions: str,
    user_text: str,
    model: str = "gemini25-default",
    max_output_tokens: int = 640,
) -> Dict[str, object]:
    """Call Google Gemini to produce a SimpleExplV1 payload."""

    api_model = _resolve_expl_model(model)
    api_key = _resolve_api_key()
    output_limit = _effective_output_limit(max_output_tokens)
    payload = {
        "system_instruction": {"role": "system", "parts": [{"text": instructions}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0,
            "max_output_tokens": output_limit,
        },
    }

    url = f"{_API_BASE}/models/{api_model}:generateContent"
    params = {"key": api_key}

    _GEMINI_RATE_LIMITER.acquire()
    t0 = time.time()
    response = requests.post(url, params=params, json=payload, timeout=60)
    latency_ms = int((time.time() - t0) * 1000)

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(_format_http_error(response)) from exc

    try:
        data = response.json()
    except ValueError as exc:
        snippet = (response.text or "").strip()[:400]
        raise RuntimeError(f"Gemini explanation returned non-JSON payload: {snippet}") from exc

    text = _extract_text(data)
    if not text:
        snippet = json.dumps(data)[:400] if isinstance(data, dict) else str(data)[:400]
        raise RuntimeError(f"Gemini explanation returned no text payload: {snippet}")

    # Attempt to normalize the JSON payload before returning
    try:
        # robustly extract the JSON substring (handles fences and preamble)
        clean_text = strip_markdown_json(text)

        # Partial parse to fix common schema hallucinations
        parsed = json.loads(clean_text)
        if isinstance(parsed, dict):
            # Fix 1: Map 'reason' or 'explanation' to 'body_paragraphs' if missing
            # (Gemini sometimes returns { "reason": "..." } instead of the schema)
            content_source = parsed.pop("reason", None) or parsed.pop("explanation", None)
            if content_source and "body_paragraphs" not in parsed:
                parsed["body_paragraphs"] = [str(content_source)]

            # Fix 2: Ensure lists and extract strings from nested structures
            if "body_paragraphs" in parsed:
                if isinstance(parsed["body_paragraphs"], str):
                    parsed["body_paragraphs"] = [parsed["body_paragraphs"]]
                elif isinstance(parsed["body_paragraphs"], list):
                    # Flatten any nested JSON or ensure all elements are strings
                    cleaned_paras = []
                    for item in parsed["body_paragraphs"]:
                        if isinstance(item, str):
                            trimmed = item.strip()
                            # Check if this string is actually JSON
                            if trimmed.startswith('{') or trimmed.startswith('['):
                                try:
                                    nested_json = json.loads(trimmed)
                                    # If it's a dict with body_paragraphs, extract those
                                    if isinstance(nested_json, dict):
                                        nested_paras = nested_json.get("body_paragraphs")
                                        if isinstance(nested_paras, list):
                                            # Recursively extract from nested body_paragraphs
                                            for nested_item in nested_paras:
                                                if isinstance(nested_item, str):
                                                    cleaned_paras.append(nested_item.strip())
                                                else:
                                                    cleaned_paras.append(str(nested_item).strip())
                                        elif isinstance(nested_paras, str):
                                            cleaned_paras.append(nested_paras.strip())
                                        else:
                                            # No body_paragraphs, try other common keys
                                            text_val = nested_json.get("text") or nested_json.get("content") or nested_json.get("reason")
                                            if text_val:
                                                cleaned_paras.append(str(text_val).strip())
                                            else:
                                                # Just use the original string if we can't extract anything useful
                                                cleaned_paras.append(trimmed)
                                    else:
                                        # It's a JSON array or primitive, just stringify it
                                        cleaned_paras.append(str(nested_json).strip())
                                except (json.JSONDecodeError, ValueError):
                                    # Not valid JSON, use as-is
                                    cleaned_paras.append(trimmed)
                            else:
                                # Not JSON, use as-is
                                cleaned_paras.append(trimmed)
                        elif isinstance(item, dict):
                            # Extract text from nested dict
                            text_val = item.get("text") or item.get("content") or str(item)
                            cleaned_paras.append(str(text_val).strip())
                        else:
                            cleaned_paras.append(str(item).strip())
                    parsed["body_paragraphs"] = [p for p in cleaned_paras if p]

            if "bullets" in parsed:
                if isinstance(parsed["bullets"], str):
                    parsed["bullets"] = [parsed["bullets"]]
                elif isinstance(parsed["bullets"], list):
                    # Ensure all bullets are strings
                    cleaned_bullets = []
                    for item in parsed["bullets"]:
                        if isinstance(item, str):
                            cleaned_bullets.append(item.strip())
                        else:
                            cleaned_bullets.append(str(item).strip())
                    parsed["bullets"] = [b for b in cleaned_bullets if b]

            # Fix 3: Ensure title exists if we have content (prevents validation failure)
            if "title" not in parsed and "body_paragraphs" in parsed:
                # Use a generic title so we don't lose the valid content
                parsed["title"] = "Analysis of the verdict"

            # Re-serialize to ensure downstream validators see clean JSON
            text = json.dumps(parsed, ensure_ascii=False)
    except Exception:
        # If parsing fails here, we ignore it and let the downstream validator
        # raise the standard error (preserving the original text for debugging).
        pass

    tokens_in, tokens_out = _usage_counts(data)
    telemetry = LLMTelemetry(
        provider="google",
        logical_model=str(model),
        api_model=api_model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
    )

    return {
        "text": text,
        "warnings": [],
        "meta": {"provider_model_id": api_model},
        "timing": {"latency_ms": latency_ms},
        "telemetry": telemetry,
    }


register_expl_adapter(
    aliases=("gemini25-default", "gemini-2.5", "gemini", "google"),
    fn=write_simple_expl_gemini,
)
