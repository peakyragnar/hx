from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from .types import Doc


def normalize_snippet_text(text: str) -> str:
    return " ".join((text or "").split())


def dedupe_by_url(docs: List[Doc]) -> List[Doc]:
    seen = set()
    unique: List[Doc] = []
    for doc in docs:
        key = doc.url or doc.title
        if key and key not in seen:
            seen.add(key)
            unique.append(doc)
    return unique


def cap_per_domain(docs: List[Doc], max_per_domain: int = 3) -> List[Doc]:
    counts: Dict[str, int] = defaultdict(int)
    result: List[Doc] = []
    for doc in docs:
        domain = doc.domain or ""
        if counts[domain] < max_per_domain:
            counts[domain] += 1
            result.append(doc)
    return result


def median_age_days(docs: List[Doc], min_confidence: float = 0.0) -> float:
    now = datetime.now(timezone.utc)
    ages = []
    for doc in docs:
        if doc.published_at and doc.published_confidence >= min_confidence:
            delta = (now - doc.published_at).total_seconds() / 86400.0
            ages.append(max(delta, 0.0))
    if not ages:
        return math.nan
    ages.sort()
    mid = len(ages) // 2
    if len(ages) % 2 == 1:
        return float(ages[mid])
    return float((ages[mid - 1] + ages[mid]) / 2.0)


def pack_snippets_for_llm(claim: str, docs: List[Doc], max_chars: int = 6000) -> str:
    lines = [f"CLAIM: {claim}", "", "SNIPPETS (use ONLY these):"]
    for doc in docs:
        date_str = doc.published_at.date().isoformat() if doc.published_at else "unknown-date"
        lines.append(f"- [{doc.domain}] {doc.title.strip()[:300]} ({date_str})")
        lines.append(f"  {doc.snippet}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def evidence_metrics(docs: List[Doc]) -> Dict[str, float]:
    domains = {doc.domain for doc in docs if doc.domain}
    return {
        "n_docs": float(len(docs)),
        "n_domains": float(len(domains)),
        "median_age_days": float(median_age_days(docs)),
    }
