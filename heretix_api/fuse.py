from __future__ import annotations

from typing import Dict, Tuple

from heretix_wel.timeliness import heuristic_is_timely
from heretix_wel.weights import (
    fuse_probabilities,
    recency_score,
    strength_score,
    web_weight,
)


def fuse_prior_web(claim: str, prior: Dict[str, float], web: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
    recency = recency_score(
        claim_is_timely=heuristic_is_timely(claim),
        median_age_days=float(web["evidence"].get("median_age_days", 365.0)),
    )
    strength = strength_score(
        n_docs=int(web["evidence"].get("n_docs", 0)),
        n_domains=int(web["evidence"].get("n_domains", 0)),
        dispersion=float(web["evidence"].get("dispersion", 0.0)),
        json_valid_rate=float(web["evidence"].get("json_valid_rate", 1.0)),
    )
    weight = web_weight(recency, strength)
    p_combined, ci_combined = fuse_probabilities(
        prior["p"],
        tuple(prior["ci95"]),
        web["p"],
        tuple(web["ci95"]),
        weight,
    )
    return (
        {"p": p_combined, "ci95": list(ci_combined)},
        {"w_web": weight, "recency": recency, "strength": strength},
    )
