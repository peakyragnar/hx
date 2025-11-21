from __future__ import annotations

import time
import hashlib
import logging
from typing import Any, Dict, Optional

import os
import atexit
import threading
from heretix.ratelimit import RateLimiter
try:
    # Optional provider-config support; falls back to env/defaults if absent
    from .config import get_rate_limits, load_provider_capabilities  # type: ignore
except Exception:  # pragma: no cover - defensive import guard
    get_rate_limits = None  # type: ignore
    load_provider_capabilities = None  # type: ignore

from openai import OpenAI

from .json_utils import parse_schema_from_text
from .schema_text import RPL_SAMPLE_JSON_SCHEMA
from .telemetry import LLMTelemetry
from heretix.schemas import RPLSampleV1

logger = logging.getLogger(__name__)

# JSON schema for chat.completions enforcement
_RPL_JSON_SCHEMA = {
    "name": "rpl_sample",
    "schema": {
        "type": "object",
        "properties": {
            "belief": {
                "type": "object",
                "properties": {
                    "prob_true": {"type": "number"},
                    "ci95": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "rationale": {"type": "string"},
                },
                "required": ["prob_true"],
            },
            "meta": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "prompt_sha256": {"type": "string"},
                },
                "required": ["prompt_sha256"],
            },
        },
        "required": ["belief", "meta"],
        "additionalProperties": True,
    },
}


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


def _extract_output_text(resp: Any) -> Optional[str]:
    # Responses API shape
    if hasattr(resp, "output_text") and resp.output_text:
        return str(resp.output_text)
    try:
        for o in getattr(resp, "output", []) or []:
            if getattr(o, "type", None) != "message":
                continue
            parts = getattr(o, "content", []) or []
            for part in parts:
                if getattr(part, "type", None) == "output_text" and getattr(part, "text", None):
                    return str(part.text)
    except Exception:
        pass
    # Chat Completions shape
    try:
        choices = getattr(resp, "choices", None) or []
        if choices:
            content = getattr(choices[0], "message", None) or getattr(choices[0], "delta", None)
            if content:
                text = getattr(content, "content", None)
                if isinstance(text, list):
                    # Newer SDK returns content parts
                    for part in text:
                        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                            return str(part["text"])
                        if hasattr(part, "type") and getattr(part, "type") == "text" and getattr(part, "text", None):
                            return str(getattr(part, "text"))
                if text:
                    return str(text)
    except Exception:
        pass
    return None


def _resolve_api_model(logical_model: str) -> str:
    if not load_provider_capabilities:
        return logical_model
    try:
        caps = load_provider_capabilities()
    except Exception:
        return logical_model
    record = caps.get("openai") if isinstance(caps, dict) else None
    if record and logical_model in record.api_model_map:
        return record.api_model_map[logical_model]
    return logical_model


def score_claim(
    *,
    claim: str,
    system_text: str,
    user_template: str,
    paraphrase_text: str,
    model: str = "gpt-5",
    max_output_tokens: int = 1024,
) -> Dict[str, Any]:
    """Call GPT-5 Responses API to score a claim under a paraphrase.

    Returns a dict with keys: raw (parsed JSON), meta (provider_model_id, prompt_sha256, response_id, created),
    and timing fields (tokens_out unknown unless provider returns it; we capture latency_ms).
    """
    paraphrased = paraphrase_text.replace("{CLAIM}", claim)
    user_text = f"{paraphrased}\n\n" + user_template.replace("{CLAIM}", claim)
    schema_instructions = RPL_SAMPLE_JSON_SCHEMA
    full_instructions = system_text + "\n\n" + schema_instructions
    prompt_sha256 = hashlib.sha256((full_instructions + "\n\n" + user_text).encode("utf-8")).hexdigest()

    api_model = _resolve_api_model(model)
    t0 = time.time()
    _OPENAI_RATE_LIMITER.acquire()
    # Create a fresh client per call for thread-safety under concurrency
    client = _get_openai_client()
def _responses_call(with_format: bool):
    kwargs: dict[str, object] = {
        "model": api_model,
        "instructions": full_instructions,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
        "max_output_tokens": max_output_tokens,
        "temperature": 0,
        "top_p": 1,
        "parallel_tool_calls": False,
    }
    if with_format:
        kwargs["response_format"] = {"type": "json_schema", "json_schema": _RPL_JSON_SCHEMA}
    return client.responses.create(**kwargs)

def _chat_call():
    kwargs: dict[str, object] = {
        "model": api_model,
        "messages": [
            {"role": "system", "content": full_instructions},
            {"role": "user", "content": user_text},
        ],
        "max_output_tokens": max_output_tokens,
        "response_format": {"type": "json_schema", "json_schema": _RPL_JSON_SCHEMA},
        "temperature": 0,
        "top_p": 1,
        "parallel_tool_calls": False,
    }
    return client.chat.completions.create(**kwargs)

    # Prefer chat with JSON schema; fall back to Responses
    try:
        resp = _chat_call()
    except Exception:
        try:
            resp = _responses_call(with_format=True)
        except TypeError:
            resp = _responses_call(with_format=False)
    latency_ms = int((time.time() - t0) * 1000)

    # Parse JSON from response object
    raw_text = _extract_output_text(resp)
    raw_obj, sample_payload, warnings = parse_schema_from_text(raw_text, RPLSampleV1)
    if not sample_payload:
        resp_id = getattr(resp, "id", None) or getattr(resp, "response_id", None)
        _raw_debug = (raw_text or "")[:4000]
        logger.warning("openai_gpt5: responses parse failed (resp_id=%s) raw=%s", resp_id, _raw_debug)
        try:
            resp = _chat_call()
            raw_text = _extract_output_text(resp)
            raw_obj, sample_payload, warnings = parse_schema_from_text(raw_text, RPLSampleV1)
        except Exception:
            pass
    if not sample_payload:
        resp_id = getattr(resp, "id", None) or getattr(resp, "response_id", None)
        _raw_debug = (raw_text or "")[:4000]
        logger.warning("openai_gpt5: chat parse failed (resp_id=%s) raw=%s", resp_id, _raw_debug)

    provider_model_id = getattr(resp, "model", api_model)
    response_id = getattr(resp, "id", None) or getattr(resp, "response_id", None)
    created_ts = int(getattr(resp, "created", int(time.time())))
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
        "raw": raw_obj,
        "sample": sample_payload,
        "warnings": warnings,
        "meta": {
            "provider_model_id": provider_model_id,
            "prompt_sha256": prompt_sha256,
            "response_id": response_id,
            "created": float(created_ts),
        },
        "timing": {
            "latency_ms": latency_ms,
        },
        "telemetry": telemetry,
    }
_rps: float
_burst: int
if get_rate_limits is not None:
    try:
        _rps, _burst = get_rate_limits("openai", "gpt-5")  # defaults for this adapter
    except Exception:  # pragma: no cover - config failures fall back to env/defaults
        _rps = float(os.getenv("HERETIX_OPENAI_RPS", "2"))
        _burst = int(os.getenv("HERETIX_OPENAI_BURST", "2"))
else:
    _rps = float(os.getenv("HERETIX_OPENAI_RPS", "2"))
    _burst = int(os.getenv("HERETIX_OPENAI_BURST", "2"))

_OPENAI_RATE_LIMITER = RateLimiter(rate_per_sec=float(_rps), burst=int(_burst))
_CLIENT_LOCK = threading.Lock()
_OPENAI_CLIENT: Optional[OpenAI] = None


def _get_openai_client() -> OpenAI:
    global _OPENAI_CLIENT
    with _CLIENT_LOCK:
        if _OPENAI_CLIENT is None:
            _OPENAI_CLIENT = OpenAI()
        return _OPENAI_CLIENT


def _close_openai_client() -> None:
    client = _OPENAI_CLIENT
    if client and hasattr(client, "close"):
        try:
            client.close()
        except Exception:
            pass


atexit.register(_close_openai_client)

from .registry import register_score_fn

register_score_fn(
    aliases=("gpt-5", "openai-gpt5", "openai:gpt-5", "openai", "gpt5-default"),
    fn=score_claim,
)
score_claim.__logical_model__ = "gpt5-default"
