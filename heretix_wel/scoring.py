from __future__ import annotations

import hashlib
from typing import Dict, List, Tuple

from heretix.provider.json_utils import parse_schema_from_text
from heretix.provider.registry import get_wel_score_fn
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
    Evaluate a bundle of snippets using the registered WEL adapter.
    """
    instructions = f"{WEL_SYSTEM}\n\n{WEL_SCHEMA}"
    prompt_hash = hashlib.sha256((instructions + bundle_text).encode("utf-8")).hexdigest()

    adapter = get_wel_score_fn(model)
    result = adapter(
        instructions=instructions,
        bundle_text=bundle_text,
        model=model,
        max_output_tokens=768,
    )
    if not isinstance(result, dict):
        raise TypeError("WEL adapter must return a dict payload with 'text'")
    payload = result.get("text")
    adapter_warnings = list(result.get("warnings") or [])
    if not payload:
        raise RuntimeError("WEL adapter returned an empty payload")

    _, canonical, schema_warnings = parse_schema_from_text(payload, WELDocV1)
    warnings = adapter_warnings + schema_warnings
    if canonical is None:
        raise WELSchemaError(warnings)
    return canonical, warnings, prompt_hash
