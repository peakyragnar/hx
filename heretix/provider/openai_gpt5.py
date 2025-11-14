from __future__ import annotations

import time
import hashlib
from typing import Any, Dict, Optional

import os
from heretix.ratelimit import RateLimiter
try:
    # Optional provider-config support; falls back to env/defaults if absent
    from .config import get_rate_limits  # type: ignore
except Exception:  # pragma: no cover - defensive import guard
    get_rate_limits = None  # type: ignore

from openai import OpenAI

from .json_utils import parse_schema_from_text
from .schema_text import RPL_SAMPLE_JSON_SCHEMA
from .telemetry import LLMTelemetry
from heretix.schemas import RPLSampleV1


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
    return None


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

    t0 = time.time()
    _OPENAI_RATE_LIMITER.acquire()
    # Create a fresh client per call for thread-safety under concurrency
    client = OpenAI()
    try:
        resp = client.responses.create(
            model=model,
            instructions=full_instructions,
            input=[{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
            max_output_tokens=max_output_tokens,
            reasoning={"effort": "minimal"},
        )
    except Exception as e:
        if "reasoning" in str(e):
            resp = client.responses.create(
                model=model,
                instructions=full_instructions,
                input=[{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
                max_output_tokens=max_output_tokens,
            )
        else:
            raise
    latency_ms = int((time.time() - t0) * 1000)

    # Parse JSON from response object
    raw_text = _extract_output_text(resp)
    raw_obj, sample_payload, warnings = parse_schema_from_text(raw_text, RPLSampleV1)

    provider_model_id = getattr(resp, "model", model)
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

from .registry import register_score_fn

register_score_fn(
    aliases=("gpt-5", "openai-gpt5", "openai:gpt-5", "openai", "gpt5-default"),
    fn=score_claim,
)
