"""
Monitor Run Summary Generator

Analyzes JSONL monitor output files and generates statistical summaries.
Reports probability distributions, CI widths, stability metrics, drift counts,
and identifies claims with widest confidence intervals for quality assessment.
"""
from __future__ import annotations                           # Enable forward type references

import json                                                  # JSON parsing for JSONL files
from pathlib import Path                                     # Path handling
from typing import Any, Dict, List                           # Type annotations


def _safe_mean(vals: List[float]) -> float:
    """Calculate mean of list, returning 0.0 for empty lists."""  # Function purpose
    return sum(vals) / len(vals) if vals else 0.0           # Return mean or zero if empty


def summarize_jsonl(path: str) -> Dict[str, Any]:
    """Parse JSONL monitor file and return comprehensive summary statistics."""  # Function purpose
    p = Path(path)                                           # Create Path object from file path
    rows: List[Dict[str, Any]] = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]  # Parse JSONL into list of dicts
    n = len(rows)                                            # Count total number of rows
    p_vals = [float(r.get("p_RPL")) for r in rows if r.get("p_RPL") is not None]  # Extract valid RPL probabilities
    widths = [float(r.get("ci_width")) for r in rows if r.get("ci_width") is not None]  # Extract valid CI widths
    stabs = [float(r.get("stability")) for r in rows if r.get("stability") is not None]  # Extract valid stability scores
    high = sum(1 for v in p_vals if v >= 0.9)               # Count high-confidence predictions (≥0.9)
    low = sum(1 for v in p_vals if v <= 0.1)                # Count low-confidence predictions (≤0.1)
    mid = sum(1 for v in p_vals if 0.4 <= v <= 0.6)         # Count neutral predictions (0.4-0.6)
    drift_p = sum(1 for r in rows if r.get("drift_p"))      # Count probability drift flags
    drift_s = sum(1 for r in rows if r.get("drift_stability"))  # Count stability drift flags
    drift_ci = sum(1 for r in rows if r.get("drift_ci"))    # Count CI width drift flags
    # Top 3 widest CIs
    widest = sorted(                                         # Sort claims by CI width (descending)
        (                                                    # Create tuples of (ci_width, claim)
            (float(r.get("ci_width", 0.0)), str(r.get("claim", "")))  # Extract CI width and claim text
            for r in rows                                    # Iterate through all rows
        ),
        key=lambda x: x[0],                                  # Sort by CI width (first element)
        reverse=True,                                        # Largest CI widths first
    )[:3]                                                    # Take top 3 widest
    models = sorted({str(r.get("model")) for r in rows if r.get("model")})  # Get unique sorted model names
    versions = sorted({str(r.get("prompt_version")) for r in rows if r.get("prompt_version")})  # Get unique sorted prompt versions

    return {                                                 # Return comprehensive summary dictionary
        "file": str(p),                                      # Original file path
        "n_rows": n,                                         # Total number of rows processed
        "models": models,                                    # Unique model names found
        "prompt_versions": versions,                         # Unique prompt versions found
        "mean_p": _safe_mean(p_vals),                       # Mean RPL probability across all claims
        "mean_ci_width": _safe_mean(widths),                # Mean CI width across all claims
        "mean_stability": _safe_mean(stabs),                # Mean stability score across all claims
        "count_high_ge_0_9": high,                          # Count of high-confidence predictions
        "count_low_le_0_1": low,                            # Count of low-confidence predictions
        "count_mid_0_4_to_0_6": mid,                        # Count of neutral predictions
        "drift_counts": {"p": drift_p, "stability": drift_s, "ci": drift_ci},  # Drift detection counts by type
        "widest_ci": [{"ci_width": w, "claim": c} for (w, c) in widest],  # Top 3 widest CI claims for inspection
    }

