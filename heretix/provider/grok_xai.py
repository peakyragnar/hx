from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any, Dict, Iterable, Optional

from heretix.ratelimit import RateLimiter

from .config import get_rate_limits
from .json_utils import parse_schema_from_text
from .registry import register_score_fn
from .schema_text import RPL_SAMPLE_JSON_SCHEMA
from .telemetry import LLMTelemetry
from heretix.schemas import RPLSampleV1

try:  # pragma: no cover - import guard mirrors openai adapter
    from openai import OpenAI
except Exception as exc:  # pragma: no cover - defer failure until use
    raise RuntimeError("openai SDK is required for the Grok adapter") from exc


_LOGGER = logging.getLogger(__name__)
_DEFAULT_API_BASE = "https://api.x.ai/v1"
_MODEL_ALLOWLIST = {
    "grok-4",
    "grok-4-latest",
    "grok-5",
    "grok-5-latest",
}
_MODEL_PREFIX_ALLOWLIST = ("grok-4", "grok-5")


def _resolve_rate_limits() -> tuple[float, int]:
    try:
        rps, burst = get_rate_limits("xai", "grok-4")
    except Exception:
        rps, burst = 1.0, 2
    rps_env = os.getenv("HERETIX_XAI_RPS")
    burst_env = os.getenv("HERETIX_XAI_BURST")
    if rps_env:
        try:
            rps = float(rps_env)
        except ValueError:
            pass
    if burst_env:
        try:
            burst = int(burst_env)
        except ValueError:
            pass
    if rps <= 0:
        rps = 1.0
    if burst <= 0:
        burst = 1
    return float(rps), int(burst)


_XAI_RPS, _XAI_BURST = _resolve_rate_limits()
_XAI_RATE_LIMITER = RateLimiter(rate_per_sec=_XAI_RPS, burst=_XAI_BURST)


def _build_client() -> Any:
    api_key = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
    if not api_key:
        raise RuntimeError("Set XAI_API_KEY or GROK_API_KEY for Grok runs.")
    base_url = os.getenv("XAI_API_BASE") or os.getenv("GROK_API_BASE") or _DEFAULT_API_BASE
    return OpenAI(api_key=api_key, base_url=base_url)


def _schema_instructions() -> str:
    return RPL_SAMPLE_JSON_SCHEMA


def _collect_text_from_output(resp: Any) -> Optional[str]:
    if hasattr(resp, "output_text") and resp.output_text:
        return str(resp.output_text)
    try:
        output = getattr(resp, "output", None) or []
        for chunk in output:
            if getattr(chunk, "type", None) != "message":
                continue
            for part in getattr(chunk, "content", []) or []:
                if getattr(part, "type", None) == "output_text" and getattr(part, "text", None):
                    return str(part.text)
    except Exception:
        pass
    choices = getattr(resp, "choices", None) or []
    for choice in choices:
        message = getattr(choice, "message", None)
        if not message:
            continue
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, Iterable):
            collected: list[str] = []
            for item in content:
                if isinstance(item, str):
                    collected.append(item)
                elif isinstance(item, dict):
                    text_val = item.get("text") or item.get("content")
                    if isinstance(text_val, str):
                        collected.append(text_val)
            if collected:
                return "\n".join(collected)
    return None


def _call_chat_completion(
    client: Any,
    *,
    instructions: str,
    user_text: str,
    model: str,
    max_output_tokens: int,
) -> Any:
    chat = getattr(client, "chat", None)
    completions = getattr(chat, "completions", None)
    if completions is None or not hasattr(completions, "create"):
        raise
    return completions.create(
        model=model,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_text},
        ],
        max_output_tokens=max_output_tokens,
        temperature=0.0,
    )


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


def _append_model_warning(meta: Dict[str, Any]) -> None:
    provider_model_id = meta.get("provider_model_id")
    if not provider_model_id:
        return
    normalized = str(provider_model_id).lower()
    if normalized in _MODEL_ALLOWLIST:
        return
    if any(normalized.startswith(prefix) for prefix in _MODEL_PREFIX_ALLOWLIST):
        return
    warning = f"Unexpected provider model id '{provider_model_id}' for Grok adapter"
    meta["model_warning"] = warning
    _LOGGER.warning("%s", warning)


def score_claim(
    *,
    claim: str,
    system_text: str,
    user_template: str,
    paraphrase_text: str,
    model: str = "grok-4",
    max_output_tokens: int = 1024,
) -> Dict[str, Any]:
    """Call the Grok (xAI) Responses API to score a claim."""

    paraphrased = paraphrase_text.replace("{CLAIM}", claim)
    user_text = f"{paraphrased}\n\n" + user_template.replace("{CLAIM}", claim)
    instructions = system_text + "\n\n" + _schema_instructions()
    prompt_sha256 = hashlib.sha256((instructions + "\n\n" + user_text).encode("utf-8")).hexdigest()

    max_tokens = max_output_tokens or 1024
    client = _build_client()

    payload = {
        "model": model,
        "instructions": instructions,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": user_text,
                    }
                ],
            }
        ],
        "max_output_tokens": max_tokens,
        "temperature": 0.0,
    }

    _XAI_RATE_LIMITER.acquire()
    t0 = time.time()
    try:
        resp = client.responses.create(**payload)
    except Exception as exc:
        resp = _call_chat_completion(
            client,
            instructions=instructions,
            user_text=user_text,
            model=model,
            max_output_tokens=max_tokens,
        )
        _LOGGER.debug("Grok responses.create failed (%s); used chat.completions fallback", exc)

    latency_ms = int((time.time() - t0) * 1000)

    raw_text = _collect_text_from_output(resp)
    raw_obj, sample_payload, warnings = parse_schema_from_text(raw_text, RPLSampleV1)

    provider_model_id = getattr(resp, "model", None) or model
    response_id = getattr(resp, "id", None) or getattr(resp, "response_id", None)
    created_ts = int(getattr(resp, "created", int(time.time())))

    meta = {
        "provider_model_id": provider_model_id,
        "prompt_sha256": prompt_sha256,
        "response_id": response_id,
        "created": float(created_ts),
    }
    _append_model_warning(meta)
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
        "raw": raw_obj,
        "sample": sample_payload,
        "warnings": warnings,
        "meta": meta,
        "timing": {"latency_ms": latency_ms},
        "telemetry": telemetry,
    }


register_score_fn(
    aliases=(
        "grok",
        "grok-4",
        "grok4",
        "grok4-default",
        "xai:grok-4",
        "grok-5",
        "xai:grok-5",
        "xai",
    ),
    fn=score_claim,
)
