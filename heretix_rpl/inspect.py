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


def summarize_run(run_path: str) -> str:
    """Parse RPL run JSON and return formatted summary string."""  # Function purpose
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
    for row in par:                                                # Iterate through paraphrase results
        meta = row.get("meta", {})                                 # Get metadata for this result
        h = meta.get("prompt_sha256")                              # Get template hash
        raw = row.get("raw", {})                                   # Get raw model response
        if h is None or "prob_true" not in raw:                   # Skip if missing hash or probability
            continue                                               # Skip to next result
        by_tpl.setdefault(h, []).append(_logit(float(raw["prob_true"])))  # Add logit to template group

    stats = []                                                     # Initialize statistics list
    for h, L in by_tpl.items():                                    # Iterate through template groups
        arr = np.array(L, float)                                   # Convert logits to numpy array
        mean_l = float(arr.mean())                                 # Calculate mean logit for template
        mean_p = _sigmoid(mean_l)                                  # Convert mean logit to probability
        stats.append((h[:10], len(arr), mean_p, mean_l))           # Store template stats (hash, count, mean_p, mean_logit)
    stats.sort(key=lambda x: x[3])                                # Sort by mean logit ascending

    tpl_means = np.array([s[3] for s in stats], float)             # Extract mean logits for stability calculation
    if tpl_means.size > 0:                                         # If templates exist
        iqr = float(np.percentile(tpl_means, 75) - np.percentile(tpl_means, 25))  # Calculate interquartile range
        stability = 1.0 / (1.0 + iqr)                              # Calculate stability score
    else:                                                          # If no templates
        iqr = 0.0                                                  # Set IQR to zero
        stability = 0.0                                            # Set stability to zero

    a = root.get("aggregates", {})                                 # Get aggregates from root
    lines = []                                                     # Initialize output lines list
    lines.append(f"Claim: {root.get('claim', (doc.get('claim') if isinstance(doc, dict) else ''))}")  # Add claim line
    lines.append(f"Model: {root.get('model', (doc.get('model') if isinstance(doc, dict) else ''))}")  # Add model line
    samp = root.get("sampling", {})                                # Get sampling parameters
    lines.append(f"K={samp.get('K','?')}  R={samp.get('R','?')}  T={len(stats)}")  # Add sampling info line
    lines.append("")                                               # Add blank line
    lines.append("Per-template means (sorted by logit):")          # Add table header
    lines.append("  hash       n   mean_p   mean_logit")          # Add column headers
    for h, n, mp, ml in stats:                                     # Iterate through template stats
        lines.append(f"  {h:<10} {n:<3d} {mp:7.3f}  {ml: .3f}")   # Add formatted template row
    lines.append("")                                               # Add blank line
    lines.append(f"IQR(logit) = {iqr:.3f}  → stability = {stability:.3f}")  # Add stability line
    if a:                                                          # If aggregates exist
        ci = a.get("ci95", [None, None])                           # Get confidence interval
        lines.append(                                              # Add aggregates summary line
            f"p_RPL = {a.get('prob_true_rpl', float('nan')):.3f}   CI95 = [{ci[0]:.3f}, {ci[1]:.3f}]   width = {a.get('ci_width', float('nan')):.3f}   is_stable = {str(a.get('is_stable', False))}"
        )
    return "\n".join(lines)                                        # Return formatted output string
