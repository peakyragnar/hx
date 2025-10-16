from __future__ import annotations

import math
from typing import Dict, Tuple, Any

from heretix_wel.evaluate_wel import evaluate_wel

from .fuse import fuse_prior_web


def evaluate_web_informed(
    claim: str,
    prior: Dict[str, float],
    provider: str,
    model: str,
    k_docs: int,
    replicates: int,
    per_domain_cap: int,
    recency_days: int | None,
    seed: int | None = None,
) -> Tuple[Dict[str, Any], Dict[str, float], Dict[str, float], Dict[str, object]]:
    wel = evaluate_wel(
        claim=claim,
        provider=provider,
        model=model,
        k_docs=k_docs,
        per_domain_cap=per_domain_cap,
        replicates=replicates,
        recency_days=recency_days,
        seed=seed,
    )
    metrics = dict(wel["metrics"])
    evidence: Dict[str, float] = {}
    for key, value in metrics.items():
        if isinstance(value, (int, float)) and not math.isnan(float(value)):
            evidence[key] = float(value)
    web_block: Dict[str, Any] = {
        "p": float(wel["p"]),
        "ci95": [float(wel["ci95"][0]), float(wel["ci95"][1])],
        "evidence": evidence,
        "resolved": bool(metrics.get("resolved")),
        "resolved_truth": metrics.get("resolved_truth"),
        "resolved_reason": metrics.get("resolved_reason"),
        "resolved_citations": metrics.get("resolved_citations", []),
        "support": metrics.get("resolved_support"),
        "contradict": metrics.get("resolved_contradict"),
        "domains": metrics.get("resolved_domains"),
    }
    combined, weights = fuse_prior_web(claim, prior, web_block)
    if web_block["resolved"]:
        combined.update(
            {
                "resolved": True,
                "resolved_truth": web_block.get("resolved_truth"),
                "resolved_reason": web_block.get("resolved_reason"),
                "resolved_citations": web_block.get("resolved_citations", []),
                "support": web_block.get("support"),
                "contradict": web_block.get("contradict"),
                "domains": web_block.get("domains"),
            }
        )
        weights = {"w_web": 1.0, "recency": 1.0, "strength": 1.0}
    return web_block, combined, weights, wel["provenance"]
