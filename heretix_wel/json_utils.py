from __future__ import annotations

import json
import re
from typing import Any, Dict

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def load_json_obj(text: str) -> Dict[str, Any]:
    """
    Parse a JSON object, tolerating common LLM wrappers like triple backticks.
    Raises ValueError if no valid JSON object can be recovered.
    """
    if not text:
        raise ValueError("empty JSON payload")

    cleaned = text.strip()
    fence_match = _CODE_FENCE_RE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise ValueError("no JSON object found")
        candidate = cleaned[start : end + 1]
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON payload: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload

