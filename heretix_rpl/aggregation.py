"""
Statistical Aggregation for Raw Prior Lens (RPL) Evaluations

Robust methods for combining probability samples into estimates with confidence intervals.
Clustered method fixes paraphrase imbalance bias via equal template weighting.
Uses trimmed means and cluster bootstrap for outlier resistance and proper uncertainty.
"""
from __future__ import annotations                           # Enable forward type references
from typing import Dict, List, Tuple, Optional               # Type annotations
import numpy as np                                           # Numerical computations

def aggregate_simple(all_logits: List[float], B: int = 1000) -> Tuple[float, Tuple[float, float], dict]:
    """Legacy: mean over all logits + bootstrap CI (unclustered)."""  # Function purpose
    arr = np.asarray(all_logits, dtype=float)                # Convert to numpy array
    ell_hat = float(np.mean(arr))                            # Compute mean in logit space
    idx = np.random.randint(0, arr.size, size=(B, arr.size))  # Bootstrap sample indices
    means = np.mean(arr[idx], axis=1)                        # Compute B bootstrap means
    lo, hi = np.percentile(means, [2.5, 97.5])              # Get 95% confidence interval
    return ell_hat, (float(lo), float(hi)), {                # Return estimate, CI, and diagnostics
        "n_samples": int(arr.size),                          # Total number of samples
        "method": "simple_mean"                              # Method identifier
    }

def _trimmed_mean(x: np.ndarray, trim: float = 0.2) -> float:
    """Symmetric trimmed mean; drop trim*len(x) from each tail (in logit space)."""  # Function purpose
    x = np.sort(np.asarray(x, dtype=float))                  # Sort values ascending
    n = x.size                                               # Number of values
    k = int(n * trim)                                        # Number to trim from each end
    if 2*k >= n:                                             # Check if too few values to trim
        return float(np.mean(x))                             # Fall back to regular mean
    return float(np.mean(x[k:n-k]))                          # Mean of middle values after trimming

def aggregate_clustered(                                     # Robust equal-by-template aggregation
    by_template_logits: Dict[str, List[float]],              # Logits grouped by template hash
    B: int = 5000,                                           # Bootstrap iterations (increased for smoothness)
    rng: Optional[np.random.Generator] = None,               # Optional deterministic RNG
    center: str = "trimmed",                                 # Center method: "trimmed" or "mean"
    trim: float = 0.2,                                       # Trim percentage (20% = drop min/max)
    fixed_m: Optional[int] = None                            # Optional fixed resample size per template
) -> Tuple[float, Tuple[float, float], dict]:               # Returns estimate, CI, diagnostics
    """
    Equal-by-template aggregation (cluster bootstrap, deterministic if rng provided).
    1) Average replicates per template in logit space.
    2) Combine templates with equal weight using a robust center (default: 20% trimmed mean).
    3) Cluster bootstrap: resample templates, then replicates, to get CI95.
    """
    keys = list(by_template_logits.keys())                   # Get template hash keys
    T = len(keys)                                            # Number of unique templates
    if T == 0:                                               # Check for empty input
        raise ValueError("No templates to aggregate")        # Raise error if no templates

    # Choose center function
    if center == "trimmed":                                  # Trimmed mean option
        center_fn = lambda arr: _trimmed_mean(np.asarray(arr, dtype=float), trim=trim)  # Trimmed mean function
    elif center == "mean":                                   # Regular mean option
        center_fn = lambda arr: float(np.mean(np.asarray(arr, dtype=float)))  # Regular mean function
    else:                                                    # Invalid center option
        raise ValueError(f"Unknown center '{center}'")      # Raise error for unknown center

    # Deterministic generator if provided
    rng = rng or np.random.default_rng()                     # Use provided RNG or create new one

    # Per-template means (logit space)
    tpl_means = np.array([np.mean(by_template_logits[k]) for k in keys], dtype=float)  # Compute template means
    ell_hat = center_fn(tpl_means)                           # Apply center function to template means

    # Cluster bootstrap
    # Optionally standardize within-template resample size to fixed_m to equalize inner variance
    if fixed_m is None:                                      # No fixed resample size
        sizes = {k: len(by_template_logits[k]) for k in keys}  # Use actual template sizes
    else:                                                    # Fixed resample size specified
        sizes = {k: fixed_m for k in keys}                   # Use fixed size for all templates

    dist = []                                                # Bootstrap distribution storage
    for _ in range(B):                                       # B bootstrap iterations
        chosen_tpls = rng.choice(keys, size=T, replace=True)  # Resample templates with replacement
        means = []                                           # Template means for this bootstrap sample
        for k in chosen_tpls:                                # For each chosen template
            grp = np.asarray(by_template_logits[k], dtype=float)  # Get template's logits
            m = sizes[k] if sizes[k] <= grp.size else grp.size  # Determine resample size
            resamp_idx = rng.integers(0, grp.size, size=m)   # Get random indices for resampling
            grp_resamp = grp[resamp_idx]                     # Resample within template
            means.append(float(np.mean(grp_resamp)))         # Compute mean of resampled values
        dist.append(center_fn(np.array(means, dtype=float)))  # Apply center function and store

    lo, hi = np.percentile(dist, [2.5, 97.5])               # Compute 95% confidence interval
    # Ensure CI contains point estimate (important for small B)
    lo = min(float(lo), ell_hat)                            # Lower bound should not exceed estimate
    hi = max(float(hi), ell_hat)                            # Upper bound should not be below estimate

    counts = {k: len(v) for k, v in by_template_logits.items()}  # Count samples per template
    imbalance = max(counts.values()) / min(counts.values())  # Compute imbalance ratio
    tpl_iqr = float(np.percentile(tpl_means, 75) - np.percentile(tpl_means, 25))  # Template IQR

    return ell_hat, (float(lo), float(hi)), {                # Return estimate, CI, and diagnostics
        "n_templates": T,                                    # Number of unique templates
        "counts_by_template": counts,                        # Samples per template
        "imbalance_ratio": imbalance,                        # Max/min template count ratio
        "template_iqr_logit": tpl_iqr,                       # IQR across template means
        "method": "equal_by_template_cluster_bootstrap_trimmed" if center=="trimmed" else "equal_by_template_cluster_bootstrap"  # Method name
    }

AGGREGATORS = {                                              # Registry of available aggregation methods
    "simple": aggregate_simple,                              # Legacy simple aggregation
    "clustered": aggregate_clustered                         # Robust clustered aggregation (default)
}