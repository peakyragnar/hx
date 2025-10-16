from __future__ import annotations

import hashlib
import json
from typing import Dict, Tuple

from openai import OpenAI

WEL_SYSTEM = """You are the Web Evidence Lens (WEL).
Estimate P(true) for the claim using only the provided snippets.
- Ignore external knowledge.
- Point out conflicts or missing evidence in notes.
- Return strict JSON only."""

WEL_SCHEMA = """Return ONLY a JSON object with:
{
  "p_true": number between 0 and 1,
  "support_bullets": array of 1-4 short strings,
  "oppose_bullets": array of 1-4 short strings,
  "notes": array of 0-3 short strings
}"""


def call_wel_once(bundle_text: str, model: str = "gpt-5") -> Tuple[Dict[str, object], str]:
    """
    Evaluate a bundle of snippets with GPT-5 and return the parsed JSON plus prompt hash.
    """
    client = OpenAI()
    instructions = f"{WEL_SYSTEM}\n\n{WEL_SCHEMA}"
    prompt_hash = hashlib.sha256((instructions + bundle_text).encode("utf-8")).hexdigest()

    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=[{"role": "user", "content": [{"type": "input_text", "text": bundle_text}]}],
        max_output_tokens=768,
        reasoning={"effort": "minimal"},
    )

    payload = None
    if getattr(response, "output_text", None):
        payload = response.output_text
    else:
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    text = getattr(content, "text", None)
                    if text:
                        payload = text
                        break
            if payload:
                break

    if payload is None:
        raise RuntimeError("No response payload received from GPT-5")

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON from WEL model: {exc}") from exc
    return parsed, prompt_hash
