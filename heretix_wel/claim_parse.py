from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

YEAR_REGEX = re.compile(r"\b(19|20)\d{2}\b")


@dataclass
class ClaimInfo:
    text: str
    relation_family: str
    years: List[int] = field(default_factory=list)
    contains_future_reference: bool = False
    contains_past_reference: bool = False
    is_time_sensitive: bool = False


def _detect_relation_family(text: str) -> str:
    lower = text.lower()
    if any(kw in lower for kw in ("won", "defeated", "champion", "trophy", "victory")):
        return "event_outcome"
    if any(kw in lower for kw in ("ceo", "president", "headquartered", "capital", "located in", "is the leader")):
        return "identity_role"
    if any(kw in lower for kw in ("population", "price", "worth", "revenue", "salary", "net worth", "percent", "%")):
        return "numeric_value"
    if any(kw in lower for kw in ("happened", "occurred", "took place", "released", "launched", "died", "born")):
        return "existence_date"
    if any(kw in lower for kw in ("member of", "listed on", "part of", "belongs to", "is in")):
        return "membership"
    return "unknown"


def parse_claim(text: str, today: Optional[datetime] = None) -> ClaimInfo:
    today = today or datetime.utcnow()
    years = [int(y) for y in YEAR_REGEX.findall(text)]
    year_values = []
    for match in YEAR_REGEX.finditer(text):
        try:
            year_values.append(int(match.group()))
        except ValueError:
            continue

    relation_family = _detect_relation_family(text)

    contains_future = False
    contains_past = False
    for year in year_values:
        if year > today.year:
            contains_future = True
        elif year < today.year:
            contains_past = True

    lower = text.lower()
    future_signals = any(kw in lower for kw in ("will ", "will be", "going to", "next year", "upcoming"))
    present_signals = any(kw in lower for kw in ("is the", "are the", "currently", "as of"))

    time_sensitive = future_signals or relation_family in ("event_outcome", "numeric_value")

    return ClaimInfo(
        text=text,
        relation_family=relation_family,
        years=year_values,
        contains_future_reference=contains_future or future_signals,
        contains_past_reference=contains_past,
        is_time_sensitive=time_sensitive or present_signals,
    )
