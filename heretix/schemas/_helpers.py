from __future__ import annotations

from collections.abc import Iterable
from typing import List


def coerce_string_list(value: object, *, allow_empty: bool = True) -> List[str]:
    """Convert arbitrary user/model-provided content into a clean list of strings."""

    if value is None:
        return []
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate and not allow_empty:
            return []
        return [candidate] if candidate else []
    if isinstance(value, Iterable):
        cleaned: List[str] = []
        for item in value:
            if item is None:
                continue
            candidate = str(item).strip()
            if not candidate:
                if allow_empty:
                    continue
                raise ValueError("Blank strings are not allowed in this list")
            cleaned.append(candidate)
        return cleaned
    raise TypeError("Expected a string or iterable of strings")
