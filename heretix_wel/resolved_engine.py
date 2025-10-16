from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from .claim_parse import ClaimInfo, parse_claim
from .doc_verdict import DocVerdict, evaluate_doc
from .types import Doc

DOMAIN_WEIGHTS = {
    "us.gov": 2.0,
    "whitehouse.gov": 2.0,
    "house.gov": 1.8,
    "senate.gov": 1.8,
    "federalreserve.gov": 1.8,
    "mlb.com": 1.6,
    "nfl.com": 1.6,
    "nba.com": 1.6,
    "fifa.com": 1.6,
    "apnews.com": 1.5,
    "reuters.com": 1.5,
    "bbc.com": 1.4,
    "nytimes.com": 1.3,
    "washingtonpost.com": 1.3,
    "cnn.com": 1.2,
    "espn.com": 1.2,
    "yahoo.com": 1.1,
}

THRESH_SUPPORT = 2.0
THRESH_OPPOSE = 0.5
MIN_DISTINCT_DOMAINS = 2
RECENCY_TAU_DAYS = 14.0


class ResolvedResult(Dict[str, object]):
    pass


def _domain_weight(domain: str) -> float:
    domain = (domain or "").lower()
    for key, weight in DOMAIN_WEIGHTS.items():
        if domain.endswith(key):
            return weight
    if domain:
        return 1.0
    return 0.8


def _recency_weight(doc: Doc) -> float:
    if not doc.published_at:
        return 1.0
    age_days = max((datetime.utcnow() - doc.published_at.replace(tzinfo=None)).total_seconds() / 86400.0, 0.0)
    return math.exp(-age_days / RECENCY_TAU_DAYS)


def _score_doc(doc: Doc, verdict: DocVerdict) -> float:
    base = _domain_weight(doc.domain)
    recency = _recency_weight(doc)
    quote_bonus = 1.1 if verdict.quote else 1.0
    return base * recency * quote_bonus


def _should_attempt_resolution(info: ClaimInfo) -> bool:
    if info.relation_family in {"event_outcome", "identity_role", "existence_date", "numeric_value", "membership"}:
        if info.contains_future_reference:
            return False
        return True
    return False


def try_resolve_fact(
    claim_text: str,
    docs: Iterable[Doc],
    info: Optional[ClaimInfo] = None,
    model: str = "gpt-5",
) -> ResolvedResult:
    info = info or parse_claim(claim_text)
    if not _should_attempt_resolution(info):
        return ResolvedResult({"resolved": False})

    support = 0.0
    contradict = 0.0
    domain_votes = defaultdict(float)
    citations: List[Dict[str, object]] = []

    for doc in docs:
        excerpt = (doc.page_text or doc.snippet or doc.title or "").strip()
        verdict = evaluate_doc(claim_text, excerpt, model=model)
        if verdict.stance == "unclear":
            continue
        weight = _score_doc(doc, verdict)
        if verdict.stance == "support":
            support += weight
        elif verdict.stance == "contradict":
            contradict += weight
        domain_votes[doc.domain] += weight
        citations.append(
            {
                "url": doc.url,
                "domain": doc.domain,
                "quote": verdict.quote,
                "stance": verdict.stance,
                "field": verdict.field,
                "value": verdict.value,
                "weight": weight,
                "published_at": doc.published_at.isoformat() if doc.published_at else None,
            }
        )

    distinct_domains = sum(1 for d, w in domain_votes.items() if w > 0.0)

    if support >= THRESH_SUPPORT and contradict <= THRESH_OPPOSE and distinct_domains >= MIN_DISTINCT_DOMAINS:
        return ResolvedResult(
            {
                "resolved": True,
                "truth": True,
                "reason": "consensus",
                "support": support,
                "contradict": contradict,
                "domains": distinct_domains,
                "citations": citations,
            }
        )
    if contradict >= THRESH_SUPPORT and support <= THRESH_OPPOSE and distinct_domains >= MIN_DISTINCT_DOMAINS:
        return ResolvedResult(
            {
                "resolved": True,
                "truth": False,
                "reason": "consensus",
                "support": support,
                "contradict": contradict,
                "domains": distinct_domains,
                "citations": citations,
            }
        )

    return ResolvedResult(
        {
            "resolved": False,
            "support": support,
            "contradict": contradict,
            "domains": distinct_domains,
            "citations": citations,
        }
    )
