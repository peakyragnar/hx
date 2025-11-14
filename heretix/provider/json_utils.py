from __future__ import annotations

import json
import re
from typing import List, Tuple, Type

from pydantic import BaseModel, ValidationError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_REASONING_TAG_RE = re.compile(
    r"<(?P<tag>think|thinking|thought|reasoning|reflection|scratchpad)>(.*?)</\s*(?P=tag)\s*>",
    re.IGNORECASE | re.DOTALL,
)


def strip_markdown_json(text: str) -> str:
    """Remove Markdown fences and discard text outside the first JSON block."""

    if text is None:
        raise ValueError("Input text must not be None")
    trimmed = text.strip()
    if not trimmed:
        raise ValueError("Input text must not be empty")

    trimmed = _strip_reasoning_sections(trimmed)

    match = _FENCE_RE.search(trimmed)
    if match:
        trimmed = match.group(1).strip()

    start_char = "{" if "{" in trimmed else ("[" if "[" in trimmed else None)
    if start_char is None:
        raise ValueError("No JSON object/array found in text")
    end_char = "}" if start_char == "{" else "]"
    start_idx = trimmed.find(start_char)
    end_idx = trimmed.rfind(end_char)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise ValueError("Malformed JSON payload")
    return trimmed[start_idx : end_idx + 1]


def extract_and_validate(
    raw_text: str,
    schema_model: Type[BaseModel],
) -> Tuple[BaseModel, List[str]]:
    """Parse raw provider output, returning the schema object and warnings."""

    if not raw_text:
        raise ValueError("raw_text must be non-empty")
    warnings: List[str] = []

    sanitized = _strip_reasoning_sections(raw_text)

    try:
        data = json.loads(sanitized)
    except json.JSONDecodeError:
        cleaned = strip_markdown_json(sanitized)
        data = json.loads(cleaned)
        warnings.append("json_repaired_simple")

    try:
        obj = schema_model.model_validate(data, strict=True)
        return obj, warnings
    except ValidationError as strict_exc:
        try:
            obj = schema_model.model_validate(data, strict=False)
        except ValidationError as exc:
            raise exc from strict_exc
        warnings.append("validation_coerced")
        return obj, warnings


def _strip_reasoning_sections(text: str) -> str:
    """Remove <think>...</think> style reasoning tags that some models emit."""

    cleaned = text
    while True:
        updated = _REASONING_TAG_RE.sub("", cleaned)
        if updated == cleaned:
            break
        cleaned = updated
    return cleaned


__all__ = ["strip_markdown_json", "extract_and_validate"]
