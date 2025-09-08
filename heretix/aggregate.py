from __future__ import annotations

from typing import Dict, List, Tuple, Optional
import numpy as np


def _trimmed_mean(x: np.ndarray, trim: float = 0.2) -> float:
    if trim >= 0.5:
        raise ValueError(f"Trim must be < 0.5, got {trim}")
    x = np.sort(np.asarray(x, dtype=float))
    n = x.size
    k = int(n * trim)
    if 2 * k >= n:
        return float(np.mean(x))
    return float(np.mean(x[k:n - k]))


def aggregate_clustered(
    by_template_logits: Dict[str, List[float]],
    B: int = 5000,
    rng: Optional[np.random.Generator] = None,
    center: str = "trimmed",
    trim: float = 0.2,
    fixed_m: Optional[int] = None,
) -> Tuple[float, Tuple[float, float], dict]:
    keys = list(by_template_logits.keys())
    T = len(keys)
    if T == 0:
        raise ValueError("No templates to aggregate")

    if center == "trimmed":
        center_fn = lambda arr: _trimmed_mean(np.asarray(arr, dtype=float), trim=trim)
    elif center == "mean":
        center_fn = lambda arr: float(np.mean(np.asarray(arr, dtype=float)))
    else:
        raise ValueError(f"Unknown center '{center}'")

    rng = rng or np.random.default_rng()

    tpl_means = np.array([np.mean(by_template_logits[k]) for k in keys], dtype=float)
    ell_hat = center_fn(tpl_means)

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
    lo = min(float(lo), ell_hat)
    hi = max(float(hi), ell_hat)

    counts = {k: len(v) for k, v in by_template_logits.items()}
    imbalance = max(counts.values()) / min(counts.values()) if counts else 1.0
    tpl_iqr = float(np.percentile(tpl_means, 75) - np.percentile(tpl_means, 25)) if tpl_means.size else 0.0

    return ell_hat, (float(lo), float(hi)), {
        "n_templates": T,
        "counts_by_template": counts,
        "imbalance_ratio": imbalance,
        "template_iqr_logit": tpl_iqr,
        "method": "equal_by_template_cluster_bootstrap_trimmed" if center == "trimmed" else "equal_by_template_cluster_bootstrap",
    }

