from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


@dataclass
class DocVerdict:
    stance: str  # support | contradict | unclear
    quote: Optional[str]
    field: Optional[str]
    value: Optional[str]


_DOC_PROMPT = """You are a meticulous fact checker.

You MUST base your answer ONLY on the provided document excerpt. Do not use outside knowledge.

Claim: "{claim}"

Document excerpt:
"""

_DOC_INSTRUCTIONS = """Determine if this excerpt SUPPORTS, CONTRADICTS, or is UNCLEAR about the claim.

Return STRICT JSON with:
{{
  "stance": "support" | "contradict" | "unclear",
  "quote": "<verbatim quote proving your stance>",
  "field": "<one of: winner|date|number|role|membership|fact>",
  "value": "<the value extracted from the quote (e.g., actual winner, date, number)>"
}}

If you cannot provide a verbatim quote, return stance "unclear".
"""


def evaluate_doc(claim: str, context: str, model: str = "gpt-5") -> DocVerdict:
    content = context.strip()
    if not content:
        return DocVerdict("unclear", None, None, None)

    client = OpenAI()
    instructions = _DOC_PROMPT.format(claim=claim) + content

    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": _DOC_INSTRUCTIONS},
                ],
            }
        ],
        max_output_tokens=400,
        reasoning={"effort": "minimal"},
    )

    text_output = getattr(response, "output_text", None)
    if not text_output:
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "message":
                continue
            for part in getattr(item, "content", []) or []:
                if getattr(part, "type", None) == "output_text":
                    text_output = getattr(part, "text", None)
                    if text_output:
                        break
            if text_output:
                break

    if not text_output:
        return DocVerdict("unclear", None, None, None)

    try:
        payload = json.loads(text_output)
    except json.JSONDecodeError:
        return DocVerdict("unclear", None, None, None)

    stance = str(payload.get("stance") or "").lower()
    if stance not in {"support", "contradict", "unclear"}:
        stance = "unclear"

    quote = payload.get("quote")
    if not quote or not isinstance(quote, str):
        quote = None
        stance = "unclear"

    field = payload.get("field")
    if field and isinstance(field, str):
        field = field.lower()
    else:
        field = None
    if field not in {"winner", "date", "number", "role", "membership", "fact"}:
        field = None

    value = payload.get("value")
    if value and isinstance(value, str):
        value = value.strip()
    else:
        value = None

    return DocVerdict(stance, quote, field, value)
