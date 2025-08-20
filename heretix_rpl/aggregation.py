# heretix_rpl/aggregation.py
from __future__ import annotations
from typing import Dict, List, Tuple, Optional
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

def _trimmed_mean(x: np.ndarray, trim: float = 0.2) -> float:
    """Symmetric trimmed mean; drop trim*len(x) from each tail (in logit space)."""
    x = np.sort(np.asarray(x, dtype=float))
    n = x.size
    k = int(n * trim)
    if 2*k >= n:  # too few to trim; fall back to mean
        return float(np.mean(x))
    return float(np.mean(x[k:n-k]))

def aggregate_clustered(
    by_template_logits: Dict[str, List[float]],
    B: int = 5000,
    rng: Optional[np.random.Generator] = None,
    center: str = "trimmed",   # "trimmed" | "mean"
    trim: float = 0.2,         # 20% -> drop min & max when T=5
    fixed_m: Optional[int] = None  # set to an int to standardize inner resample size
) -> Tuple[float, Tuple[float, float], dict]:
    """
    Equal-by-template aggregation (cluster bootstrap, deterministic if rng provided).
    1) Average replicates per template in logit space.
    2) Combine templates with equal weight using a robust center (default: 20% trimmed mean).
    3) Cluster bootstrap: resample templates, then replicates, to get CI95.
    """
    keys = list(by_template_logits.keys())
    T = len(keys)
    if T == 0:
        raise ValueError("No templates to aggregate")

    # Choose center function
    if center == "trimmed":
        center_fn = lambda arr: _trimmed_mean(np.asarray(arr, dtype=float), trim=trim)
    elif center == "mean":
        center_fn = lambda arr: float(np.mean(np.asarray(arr, dtype=float)))
    else:
        raise ValueError(f"Unknown center '{center}'")

    # Deterministic generator if provided
    rng = rng or np.random.default_rng()

    # Per-template means (logit space)
    tpl_means = np.array([np.mean(by_template_logits[k]) for k in keys], dtype=float)
    ell_hat = center_fn(tpl_means)

    # Cluster bootstrap
    # Optionally standardize within-template resample size to fixed_m to equalize inner variance
    if fixed_m is None:
        sizes = {k: len(by_template_logits[k]) for k in keys}
    else:
        sizes = {k: fixed_m for k in keys}

    dist = []
    for _ in range(B):
        chosen_tpls = rng.choice(keys, size=T, replace=True)
        means = []
        for k in chosen_tpls:
            grp = np.asarray(by_template_logits[k], dtype=float)
            m = sizes[k] if sizes[k] <= grp.size else grp.size
            resamp_idx = rng.integers(0, grp.size, size=m)
            grp_resamp = grp[resamp_idx]
            means.append(float(np.mean(grp_resamp)))
        dist.append(center_fn(np.array(means, dtype=float)))

    lo, hi = np.percentile(dist, [2.5, 97.5])

    counts = {k: len(v) for k, v in by_template_logits.items()}
    imbalance = max(counts.values()) / min(counts.values())
    tpl_iqr = float(np.percentile(tpl_means, 75) - np.percentile(tpl_means, 25))

    return ell_hat, (float(lo), float(hi)), {
        "n_templates": T,
        "counts_by_template": counts,
        "imbalance_ratio": imbalance,
        "template_iqr_logit": tpl_iqr,
        "method": "equal_by_template_cluster_bootstrap_trimmed" if center=="trimmed" else "equal_by_template_cluster_bootstrap"
    }

AGGREGATORS = {
    "simple": aggregate_simple,
    "clustered": aggregate_clustered
}