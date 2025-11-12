from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict

from heretix.ratelimit import RateLimiter
from openai import OpenAI


_DEFAULT_GROK_MODEL = os.getenv("HERETIX_GROK_MODEL", "grok-4-fast-non-reasoning")


def score_claim(
    *,
    claim: str,
    system_text: str,
    user_template: str,
    paraphrase_text: str,
    model: str | None = None,
    max_output_tokens: int = 1024,
) -> Dict[str, Any]:
    """Call xAI Grok (OpenAI-compatible) to score a claim under a paraphrase.

    Returns a dict with keys: raw (parsed JSON), meta (provider_model_id,
    prompt_sha256, response_id, created), and timing fields (latency_ms).
    """

    target_model = (model or _DEFAULT_GROK_MODEL).strip() or _DEFAULT_GROK_MODEL

    paraphrased = paraphrase_text.replace("{CLAIM}", claim)
    user_text = f"{paraphrased}\n\n" + user_template.replace("{CLAIM}", claim)
    schema_instructions = (
        "Return ONLY JSON matching this schema: "
        "{ \"prob_true\": 0..1, \"confidence_self\": 0..1, "
        "\"assumptions\": [string], \"reasoning_bullets\": [3-6 strings], "
        "\"contrary_considerations\": [2-4 strings], \"ambiguity_flags\": [string] } "
        "Output the JSON object only."
    )
    full_instructions = system_text + "\n\n" + schema_instructions
    prompt_sha256 = hashlib.sha256((full_instructions + "\n\n" + user_text).encode("utf-8")).hexdigest()

    # Prepare client (OpenAI SDK pointed to xAI)
    api_key = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
    client = OpenAI(api_key=api_key, base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1"))

    t0 = time.time()
    _XAI_RATE_LIMITER.acquire()

    # Try Responses API first; if unsupported, fall back to Chat Completions
    # Note: Grok supports temperature; enforce temperature=0 for determinism when available.
    raw_obj: Dict[str, Any] = {}
    provider_model_id = target_model
    response_id: str | None = None
    created_ts: float = float(int(time.time()))

    def _parse_json_text(text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except Exception:
            return {}

    try:
        # Responses API path (OpenAI-compatible)
        resp = client.responses.create(
            model=target_model,
            instructions=full_instructions,
            input=[{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
            max_output_tokens=max_output_tokens,
            temperature=0,
        )
        text = getattr(resp, "output_text", None)
        if not text:
            # Walk structured output, if present
            try:
                for o in getattr(resp, "output", []) or []:
                    if getattr(o, "type", None) == "message":
                        for part in getattr(o, "content", []) or []:
                            if getattr(part, "type", None) == "output_text":
                                text = getattr(part, "text", None)
                                if text:
                                    break
                        if text:
                            break
            except Exception:
                text = None
        if text:
            raw_obj = _parse_json_text(text)
        provider_model_id = getattr(resp, "model", target_model)
        response_id = getattr(resp, "id", None) or getattr(resp, "response_id", None)
        created_ts = float(getattr(resp, "created", int(time.time())))
    except Exception:
        # Fallback: Chat Completions API
        chat = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": full_instructions},
                {"role": "user", "content": user_text},
            ],
            temperature=0,
            max_tokens=max_output_tokens,
        )
        try:
            msg = chat.choices[0].message  # type: ignore[attr-defined]
            text = getattr(msg, "content", None)
        except Exception:
            text = None
        if text:
            raw_obj = _parse_json_text(text)
        provider_model_id = getattr(chat, "model", target_model)
        response_id = getattr(chat, "id", None)
        created_ts = float(getattr(chat, "created", int(time.time())))

    latency_ms = int((time.time() - t0) * 1000)

    # If invalid JSON, leave raw={} so upstream RPL policy excludes it.
    return {
        "raw": raw_obj if isinstance(raw_obj, dict) else {},
        "meta": {
            "provider_model_id": provider_model_id or target_model,
            "prompt_sha256": prompt_sha256,
            "response_id": response_id,
            "created": created_ts,
        },
        "timing": {"latency_ms": latency_ms},
    }


_XAI_RATE_LIMITER = RateLimiter(
    rate_per_sec=float(os.getenv("HERETIX_XAI_RPS", "1")),
    burst=int(os.getenv("HERETIX_XAI_BURST", "2")),
)
