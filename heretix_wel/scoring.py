from __future__ import annotations

import hashlib
from typing import Dict, List, Tuple

from openai import OpenAI

from heretix.provider.json_utils import parse_schema_from_text
from heretix.schemas import WELDocV1


class WELSchemaError(ValueError):
    def __init__(self, warnings: List[str]):
        super().__init__("WEL response failed schema validation")
        self.warnings = warnings

WEL_SYSTEM = """You are the Web Evidence Lens (WEL).
Estimate P(true) for the claim using only the provided snippets.
- Ignore external knowledge.
- Point out conflicts or missing evidence in notes.
- Return strict JSON only."""

WEL_SCHEMA = """Return ONLY a JSON object with:
{
  "stance_prob_true": number between 0 and 1,
  "stance_label": "supports" | "contradicts" | "mixed" | "irrelevant",
  "support_bullets": array of 1-4 short strings,
  "oppose_bullets": array of 1-4 short strings,
  "notes": array of 0-3 short strings
}"""


def call_wel_once(bundle_text: str, model: str = "gpt-5") -> Tuple[Dict[str, object], List[str], str]:
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

    raw_obj, canonical, warnings = parse_schema_from_text(payload, WELDocV1)
    if canonical is None:
        raise WELSchemaError(warnings)
    return canonical, warnings, prompt_hash
