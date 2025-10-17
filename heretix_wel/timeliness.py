from __future__ import annotations

import re

_TIMELY_PATTERNS = re.compile(
    r"\b("
    r"today|tonight|tomorrow|yesterday|this (?:week|month|quarter|year)|"
    r"live|breaking|earnings|poll|primary|debate|game|match|vs\.?|odds|line|"
    r"forecast|update|recent|latest|current|reigning|defending"
    r")\b",
    flags=re.IGNORECASE,
)

_DATE_PATTERN = re.compile(
    r"\b("
    r"(?:20\d{2})-\d{2}-\d{2}|"
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
    r")\b",
    flags=re.IGNORECASE,
)


def heuristic_is_timely(claim: str) -> bool:
    """
    Lightweight heuristic to detect claims likely to require fresh evidence.
    """
    if not claim:
        return False
    if _TIMELY_PATTERNS.search(claim):
        return True
    if _DATE_PATTERN.search(claim):
        return True
    return False
