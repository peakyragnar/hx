# heretix_rpl/aggregation.py
from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np

def aggregate_simple(all_logits: List[float], B: int = 1000) -> Tuple[float, Tuple[float, float], dict]:
    """Legacy: mean over all logits + bootstrap CI (unclustered)."""
    arr = np.asarray(all_logits, dtype=float)
    ell_hat = float(np.mean(arr))
    idx = np.random.randint(0, arr.size, size=(B, arr.size))
    means = np.mean(arr[idx], axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return ell_hat, (float(lo), float(hi)), {
        "n_samples": int(arr.size),
        "method": "simple_mean"
    }

def aggregate_clustered(by_template_logits: Dict[str, List[float]], B: int = 2000) -> Tuple[float, Tuple[float, float], dict]:
    """
    Equal-by-template aggregation (cluster bootstrap).
    1) For each template key, average replicates in logit space.
    2) Average template means equally for global estimate.
    3) Cluster bootstrap: resample templates, then replicates, to get CI95.
    """
    keys = list(by_template_logits.keys())
    T = len(keys)
    if T == 0:
        raise ValueError("No templates to aggregate")
    tpl_means = [float(np.mean(by_template_logits[k])) for k in keys]
    ell_hat = float(np.mean(tpl_means))

    dist = []
    for _ in range(B):
        chosen_tpls = np.random.choice(keys, size=T, replace=True)
        means = []
        for k in chosen_tpls:
            grp = np.asarray(by_template_logits[k], dtype=float)
            grp_resamp = grp[np.random.randint(0, grp.size, size=grp.size)]
            means.append(float(np.mean(grp_resamp)))
        dist.append(float(np.mean(means)))
    lo, hi = np.percentile(dist, [2.5, 97.5])

    counts = {k: len(v) for k, v in by_template_logits.items()}
    imbalance = max(counts.values()) / min(counts.values())
    tpl_iqr = float(np.percentile(tpl_means, 75) - np.percentile(tpl_means, 25))

    return ell_hat, (float(lo), float(hi)), {
        "n_templates": T,
        "counts_by_template": counts,
        "imbalance_ratio": imbalance,
        "template_iqr_logit": tpl_iqr,
        "method": "equal_by_template_cluster_bootstrap"
    }

# Optional: simple registry if we add more estimators later
AGGREGATORS = {
    "simple": aggregate_simple,
    "clustered": aggregate_clustered
}