"""
Inspection utility for RPL run JSONs.

Summarizes per-template means (probability and logit), IQR(logit), stability,
headline CI, and counts/imbalance for transparency.
"""
from __future__ import annotations                           # Enable forward type references

import json                                                  # JSON parsing for run files
from typing import Dict, List                                # Type annotations
import numpy as np                                           # Numerical computations


def _logit(p: float) -> float:
    """Convert probability to logit with numerical stability."""  # Function purpose
    p = min(max(float(p), 1e-6), 1 - 1e-6)                      # Clamp probability to avoid log(0) or log(inf)
    return float(np.log(p / (1 - p)))                            # Return log-odds transformation


def _sigmoid(x: float) -> float:
    """Convert logit to probability with numerical stability."""  # Function purpose
    x = float(np.clip(x, -709, 709))                            # Clamp logit to avoid overflow in exp
    return float(1 / (1 + np.exp(-x)))                          # Return sigmoid transformation


def summarize_run(
    run_path: str,
    show_ci_signal: bool = False,              # Show templates farthest from trimmed center (CI signal)
    show_replicates: bool = False,             # Show within-template replicate spreads
    limit: int = 3                             # Limit entries in optional sections
) -> str:
    """Parse RPL run JSON and return formatted summary string.

    Optional views:
      - show_ci_signal: highlights templates with largest |delta_logit| from 20% trimmed center.
      - show_replicates: shows per-template replicate probabilities and logit stdev/range.
    """
    doc = json.loads(open(run_path, "r").read())                   # Load JSON document from file

    # Accept three shapes:
    # 1) Plain RPL run (evaluate_rpl_gpt5 output) with top-level paraphrase_results
    # 2) Orchestrator top-level (auto) with stages[] and final.stage_id
    # 3) A stage snapshot object that has raw_run

    root = None                                                     # Initialize root data container
    # Case 3: direct stage snapshot with raw_run
    if isinstance(doc, dict) and "raw_run" in doc:                 # If document is stage snapshot
        root = doc["raw_run"]                                       # Extract raw run data
    # Case 2: orchestrator top-level
    elif isinstance(doc, dict) and "stages" in doc:                # If document is orchestrator output
        stages = doc.get("stages", []) or []                       # Get stages list
        # Choose the final stage if identified; else last stage
        final_id = (doc.get("final") or {}).get("stage_id")        # Get final stage ID
        stage = None                                               # Initialize stage variable
        if final_id:                                               # If final stage ID exists
            for s in stages:                                       # Iterate through stages
                if s.get("stage_id") == final_id:                  # If stage matches final ID
                    stage = s                                      # Set as target stage
                    break                                          # Stop searching
        if stage is None and stages:                               # If no final stage but stages exist
            stage = stages[-1]                                     # Use last stage
        root = (stage or {}).get("raw_run", {})                    # Extract raw run from stage
    # Case 1: plain run
    else:                                                          # If document is plain run
        root = doc                                                 # Use document directly

    par = root.get("paraphrase_results", [])                       # Get paraphrase results list
    by_tpl: Dict[str, List[float]] = {}                            # Group logits by template hash
    by_tpl_probs: Dict[str, List[float]] = {}                      # Group probabilities by template hash
    tpl_to_pidx: Dict[str, int] = {}                               # Map template hash to paraphrase_idx
    for row in par:                                                # Iterate through paraphrase results
        meta = row.get("meta", {})                                 # Get metadata for this result
        h = meta.get("prompt_sha256")                              # Get template hash
        raw = row.get("raw", {})                                   # Get raw model response
        if h is None or "prob_true" not in raw:                   # Skip if missing hash or probability
            continue                                               # Skip to next result
        p = float(raw["prob_true"])                                # Extract probability
        by_tpl.setdefault(h, []).append(_logit(p))                 # Add logit to template group
        by_tpl_probs.setdefault(h, []).append(p)                   # Track probabilities too
        if h not in tpl_to_pidx and "paraphrase_idx" in row:      # Record paraphrase index if present
            try:
                tpl_to_pidx[h] = int(row["paraphrase_idx"])      # Map hash to paraphrase_idx
            except Exception:
                pass

    stats = []                                                     # Initialize statistics list
    for h, L in by_tpl.items():                                    # Iterate through template groups
        arr = np.array(L, float)                                   # Convert logits to numpy array
        mean_l = float(arr.mean())                                 # Calculate mean logit for template
        mean_p = _sigmoid(mean_l)                                  # Convert mean logit to probability
        stats.append((h, h[:10], len(arr), mean_p, mean_l))        # Store (full_hash, short, n, mean_p, mean_logit)
    stats.sort(key=lambda x: x[4])                                # Sort by mean logit ascending

    tpl_means = np.array([s[4] for s in stats], float)             # Extract mean logits for stability calculation
    if tpl_means.size > 0:                                         # If templates exist
        iqr = float(np.percentile(tpl_means, 75) - np.percentile(tpl_means, 25))  # Calculate interquartile range
        stability = 1.0 / (1.0 + iqr)                              # Calculate stability score
    else:                                                          # If no templates
        iqr = 0.0                                                  # Set IQR to zero
        stability = 0.0                                            # Set stability to zero

    # Compute trimmed center used by aggregator (20% trim of template means)
    def _trimmed_mean(x: np.ndarray, trim: float = 0.2) -> float:
        x = np.sort(np.asarray(x, dtype=float))
        n = x.size
        k = int(n * trim)
        if 2 * k >= n:
            return float(np.mean(x))
        return float(np.mean(x[k:n - k]))

    center_logit = _trimmed_mean(tpl_means, trim=0.2) if tpl_means.size else 0.0

    a = root.get("aggregates", {})                                 # Get aggregates from root
    lines = []                                                     # Initialize output lines list
    lines.append(f"Claim: {root.get('claim', (doc.get('claim') if isinstance(doc, dict) else ''))}")  # Add claim line
    lines.append(f"Model: {root.get('model', (doc.get('model') if isinstance(doc, dict) else ''))}")  # Add model line
    samp = root.get("sampling", {})                                # Get sampling parameters
    lines.append(f"K={samp.get('K','?')}  R={samp.get('R','?')}  T={len(stats)}")  # Add sampling info line
    lines.append("")                                               # Add blank line
    lines.append("Per-template means (sorted by logit):")          # Add table header
    lines.append("  hash       n   mean_p   mean_logit")          # Add column headers
    for full_h, h, n, mp, ml in stats:                              # Iterate through template stats
        lines.append(f"  {h:<10} {n:<3d} {mp:7.3f}  {ml: .3f}")   # Add formatted template row
    lines.append("")                                               # Add blank line
    lines.append(f"IQR(logit) = {iqr:.3f}  → stability = {stability:.3f}")  # Add stability line
    if a:                                                          # If aggregates exist
        ci = a.get("ci95", [None, None])                           # Get confidence interval
        lines.append(                                              # Add aggregates summary line
            f"p_RPL = {a.get('prob_true_rpl', float('nan')):.3f}   CI95 = [{ci[0]:.3f}, {ci[1]:.3f}]   width = {a.get('ci_width', float('nan')):.3f}   is_stable = {str(a.get('is_stable', False))}"
        )
    
    # Optional: CI signal — templates farthest from trimmed center
    if show_ci_signal and len(stats) > 0:
        entries = []  # (|delta|, delta, short_h, pidx, mean_p, mean_l, full_h)
        for full_h, short_h, n, mp, ml in stats:
            delta = ml - center_logit
            pidx = tpl_to_pidx.get(full_h)
            entries.append((abs(delta), delta, short_h, pidx, mp, ml, full_h))
        entries.sort(key=lambda x: x[0], reverse=True)
        top = entries[: max(0, int(limit))]
        lines.append("")
        lines.append("CI signal (by |delta_logit| from trimmed center):")
        lines.append("  hash       pidx  mean_p   delta_logit  paraphrase")
        try:
            from heretix_rpl.rpl_prompts import PARAPHRASES as _PAR
        except Exception:
            _PAR = []
        for absd, delta, short_h, pidx, mp, ml, full_h in top:
            text = _PAR[pidx] if isinstance(pidx, int) and 0 <= pidx < len(_PAR) else "(template text unavailable)"
            lines.append(f"  {short_h:<10} {str(pidx):<4} {mp:7.3f}  {delta: .3f}  {text}")

    # Optional: Within-template replicate spreads
    if show_replicates and len(stats) > 0:
        spread = []  # (stdev_logit, range_p, short_h, pidx, probs)
        for full_h, short_h, n, mp, ml in stats:
            logits = np.array(by_tpl.get(full_h, []), float)
            probs = by_tpl_probs.get(full_h, [])
            stdev_l = float(np.std(logits)) if logits.size > 0 else 0.0
            range_p = (max(probs) - min(probs)) if probs else 0.0
            pidx = tpl_to_pidx.get(full_h)
            spread.append((stdev_l, range_p, short_h, pidx, probs))
        spread.sort(key=lambda x: (x[0], x[1]), reverse=True)
        top = spread[: max(0, int(limit))]
        lines.append("")
        lines.append("Within-template replicate spread (top by logit stdev):")
        lines.append("  hash       pidx  stdev_logit  range_p   replicates_p")
        for stdev_l, range_p, short_h, pidx, probs in top:
            probs_str = ", ".join(f"{p:.3f}" for p in probs)
            lines.append(f"  {short_h:<10} {str(pidx):<4} {stdev_l:10.3f}  {range_p:7.3f}   [{probs_str}]")
    return "\n".join(lines)                                        # Return formatted output string
