from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_REASONING_TAG_RE = re.compile(
    r"<(?P<tag>think|thinking|thought|reasoning|reflection|scratchpad)>(.*?)</\s*(?P=tag)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_WRAPPER_KEYS = ("response", "answer", "result", "output", "data", "payload", "content")
_REASONING_KEYS = {"reasoning_content", "reasoning_trace", "deliberation", "thoughts", "scratchpad"}


def _find_matching_brace(text: str, start_idx: int) -> int:
    depth = 0
    in_string = False
    escape = False
    for idx in range(start_idx, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return idx
    return -1

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
    data = _unwrap_reasoning_payload(data)

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
    """Drop provider reasoning wrappers before attempting JSON parsing."""

    cleaned = _strip_reasoning_content_prefix(text)
    while True:
        updated = _REASONING_TAG_RE.sub("", cleaned)
        if updated == cleaned:
            break
        cleaned = updated
    return cleaned


def _strip_reasoning_content_prefix(text: str) -> str:
    if not text:
        return text
    remainder = text.lstrip()
    while remainder:
        array_idx = remainder.find("[")
        obj_idx = remainder.find("{")
        if array_idx != -1 and (obj_idx == -1 or array_idx < obj_idx):
            return remainder[array_idx:]
        if obj_idx == -1:
            return remainder
        end = _find_matching_brace(remainder, obj_idx)
        if end == -1:
            return remainder[obj_idx:]
        chunk = remainder[obj_idx : end + 1]
        lowered = chunk.lower()
        has_reason = "reasoning_content" in lowered
        has_signal = any(token in lowered for token in ("belief", "prob_true", "stance_prob_true", "support_bullets"))
        if has_reason and not has_signal:
            remainder = remainder[end + 1 :].lstrip()
            continue
        return remainder[obj_idx:]
    return remainder


def _maybe_parse_json_string(value: Any) -> Any:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith("{") or candidate.startswith("["):
            try:
                return json.loads(candidate)
            except Exception:
                return value
    return value


def _looks_like_schema_dict(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    keys = set(obj.keys())
    if "belief" in keys or "prob_true" in keys:
        return True
    if {"stance_prob_true", "stance_label"}.issubset(keys):
        return True
    if {"support_bullets", "oppose_bullets"}.issubset(keys):
        return True
    if {"prob_true_rpl", "ci95"}.issubset(keys):
        return True
    return False


def _unwrap_reasoning_payload(data: Any) -> Any:
    current = data
    for _ in range(8):
        if isinstance(current, str):
            parsed = _maybe_parse_json_string(current)
            if parsed is current:
                break
            current = parsed
            continue
        if isinstance(current, list):
            if len(current) == 1:
                current = current[0]
                continue
            break
        if not isinstance(current, dict):
            break
        for key in list(_REASONING_KEYS):
            if key in current:
                current.pop(key, None)
        if _looks_like_schema_dict(current):
            break
        next_data: Any = None
        for key in _WRAPPER_KEYS:
            if key not in current:
                continue
            candidate = _maybe_parse_json_string(current[key])
            if isinstance(candidate, (dict, list)):
                next_data = candidate
                break
        if next_data is None:
            break
        current = next_data
    return current


def _safe_json_dict(text: Optional[str]) -> Dict[str, Any]:
    """Best-effort parse of provider payloads into a dict, allowing fenced JSON."""

    if not text:
        return {}
    attempts = [text]
    try:
        cleaned = strip_markdown_json(text)
    except ValueError:
        cleaned = None
    if cleaned and cleaned not in attempts:
        attempts.append(cleaned)
    for candidate in attempts:
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        if isinstance(obj, dict):
            cleaned = _unwrap_reasoning_payload(obj)
            if isinstance(cleaned, dict):
                return cleaned
    return {}


def parse_schema_from_text(
    raw_text: Optional[str],
    schema_model: Type[BaseModel],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], List[str]]:
    """Return (best-effort raw dict, canonical dict | None, warnings)."""

    fallback = _safe_json_dict(raw_text)
    if not raw_text:
        return fallback, None, []
    try:
        parsed, warnings = extract_and_validate(raw_text, schema_model)
    except Exception:
        return fallback, None, ["schema_validation_failed"]
    canonical = parsed.model_dump()
    if not fallback:
        fallback = canonical
    return fallback, canonical, warnings


__all__ = ["strip_markdown_json", "extract_and_validate", "parse_schema_from_text"]
