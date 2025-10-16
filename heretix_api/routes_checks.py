from __future__ import annotations

from typing import Dict, Tuple

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
) -> Tuple[Dict[str, object], Dict[str, float], Dict[str, float], Dict[str, object]]:
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
    web_block = {
        "p": float(wel["p"]),
        "ci95": [float(wel["ci95"][0]), float(wel["ci95"][1])],
        "evidence": {k: float(v) for k, v in wel["metrics"].items()},
    }
    combined, weights = fuse_prior_web(claim, prior, web_block)
    return web_block, combined, weights, wel["provenance"]
