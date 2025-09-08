from __future__ import annotations

import json
import time
import hashlib
from typing import Dict, Any

from openai import OpenAI


_client = None


def _client_once() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


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
    schema_instructions = (
        "Return ONLY JSON matching this schema: "
        "{ \"prob_true\": 0..1, \"confidence_self\": 0..1, "
        "\"assumptions\": [string], \"reasoning_bullets\": [3-6 strings], "
        "\"contrary_considerations\": [2-4 strings], \"ambiguity_flags\": [string] } "
        "Output the JSON object only."
    )
    full_instructions = system_text + "\n\n" + schema_instructions
    prompt_sha256 = hashlib.sha256((full_instructions + "\n\n" + user_text).encode("utf-8")).hexdigest()

    t0 = time.time()
    client = _client_once()
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
    if hasattr(resp, "output_text") and resp.output_text:
        obj = json.loads(resp.output_text)
    else:
        # Fallback: walk items to find text
        text = None
        try:
            for o in getattr(resp, "output", []) or []:
                if getattr(o, "type", None) == "message":
                    parts = getattr(o, "content", []) or []
                    for part in parts:
                        if getattr(part, "type", None) == "output_text":
                            text = getattr(part, "text", None)
                            break
                if text:
                    break
        except Exception:
            pass
        if not text:
            raise ValueError("Failed to extract text from response")
        obj = json.loads(text)

    provider_model_id = getattr(resp, "model", model)
    response_id = getattr(resp, "id", None) or getattr(resp, "response_id", None)
    created_ts = int(getattr(resp, "created", int(time.time())))

    return {
        "raw": obj,
        "meta": {
            "provider_model_id": provider_model_id,
            "prompt_sha256": prompt_sha256,
            "response_id": response_id,
            "created": float(created_ts),
        },
        "timing": {
            "latency_ms": latency_ms,
        },
    }
