"""
Lightweight drift monitor for RPL.

Runs a sentinel set of claims at fixed settings and records p, CI width,
and stability. Compares to an optional baseline to flag drift.
"""
from __future__ import annotations                           # Enable forward type references

import json, time                                            # JSON parsing and timestamp generation
from pathlib import Path                                     # Path handling
from typing import List, Dict, Any, Optional                 # Type annotations

from heretix_rpl.rpl_eval import evaluate_rpl_gpt5          # Main RPL evaluation function
from heretix_rpl.rpl_prompts import PROMPT_VERSION          # Current prompt version for provenance
from heretix_rpl.constants import (                         # Default drift detection thresholds
    DRIFT_P_THRESH_DEFAULT,                                  # Default probability drift threshold
    DRIFT_STAB_DROP_DEFAULT,                                 # Default stability drop threshold
    DRIFT_CI_INCREASE_DEFAULT,                               # Default CI width increase threshold
)


def run_bench(bench_path: str, model: str = "gpt-5", K: int = 8, R: int = 2) -> List[Dict[str, Any]]:
    """Run the full bench and return all rows (blocking)."""  # Function purpose
    bench = json.loads(Path(bench_path).read_text())         # Load benchmark claims from JSON file
    out: List[Dict[str, Any]] = []                           # Initialize output results list
    for item in bench:                                       # Iterate through benchmark items
        claim = item["claim"]                                # Extract claim text
        res = evaluate_rpl_gpt5(claim, model=model, K=K, R=R, agg="clustered")  # Run RPL evaluation
        a = res["aggregates"]                                # Get aggregate results
        out.append({                                         # Add result row to output
            "timestamp": int(time.time()),                   # Current Unix timestamp
            "claim": claim,                                  # Original claim text
            "model": model,                                  # Model identifier
            "prompt_version": PROMPT_VERSION,                # Prompt version for provenance
            "p_RPL": a.get("prob_true_rpl"),                # RPL probability estimate
            "ci95": a.get("ci95"),                          # 95% confidence interval
            "ci_width": a.get("ci_width"),                  # CI width
            "stability": a.get("stability_score"),          # Stability score
        })
    return out                                               # Return all benchmark results


def run_bench_iter(bench_path: str, model: str = "gpt-5", K: int = 8, R: int = 2, verbose: bool = False, claims: Optional[List[str]] = None):
    """Yield one result row per claim; useful for streaming output/progress.  # Function purpose

    If `claims` is provided, iterate over that list instead of reading all from bench_path.
    """
    bench_items = json.loads(Path(bench_path).read_text())   # Load benchmark items from JSON file
    claim_list = claims if claims is not None else [x["claim"] for x in bench_items]  # Use provided claims or extract from bench
    total = len(claim_list)                                  # Get total number of claims
    for i, claim in enumerate(claim_list, start=1):          # Iterate through claims with counter
        if verbose:                                          # If verbose output requested
            print(f"[monitor] {i}/{total}: {claim} (K={K}, R={R})", flush=True)  # Print progress
        res = evaluate_rpl_gpt5(claim, model=model, K=K, R=R, agg="clustered")  # Run RPL evaluation
        a = res["aggregates"]                                # Get aggregate results
        yield {                                              # Yield result row for streaming
            "timestamp": int(time.time()),                   # Current Unix timestamp
            "claim": claim,                                  # Original claim text
            "model": model,                                  # Model identifier
            "prompt_version": PROMPT_VERSION,                # Prompt version for provenance
            "p_RPL": a.get("prob_true_rpl"),                # RPL probability estimate
            "ci95": a.get("ci95"),                          # 95% confidence interval
            "ci_width": a.get("ci_width"),                  # CI width
            "stability": a.get("stability_score"),          # Stability score
        }


def compare_to_baseline(current: List[Dict[str, Any]], baseline: Optional[List[Dict[str, Any]]] = None,
                        p_thresh: float = DRIFT_P_THRESH_DEFAULT, stab_drop: float = DRIFT_STAB_DROP_DEFAULT, ci_increase: float = DRIFT_CI_INCREASE_DEFAULT) -> List[Dict[str, Any]]:
    """Compare current results to baseline and flag drift."""  # Function purpose
    # Validate thresholds (non-negative)
    if p_thresh < 0 or stab_drop < 0 or ci_increase < 0:     # Check threshold validity
        raise ValueError("Drift thresholds must be non-negative.")  # Raise error for invalid thresholds
    if not baseline:                                         # If no baseline provided
        # No baseline: mark no drift
        for row in current:                                  # Iterate through current results
            row.update({"drift_p": False, "drift_stability": False, "drift_ci": False})  # Mark no drift flags
        return current                                       # Return current results with no drift flags
    base_map = {r["claim"]: r for r in baseline}            # Create claim lookup map from baseline
    out = []                                                 # Initialize output list
    for row in current:                                      # Iterate through current results
        claim = row["claim"]                                 # Get claim text
        b = base_map.get(claim)                             # Look up baseline for this claim
        if not b:                                           # If no baseline found for claim
            row.update({"drift_p": False, "drift_stability": False, "drift_ci": False})  # Mark no drift flags
            out.append(row)                                 # Add row to output
            continue                                        # Skip to next row
        dp = abs((row.get("p_RPL") or 0) - (b.get("p_RPL") or 0)) > p_thresh  # Check probability drift
        ds = ((row.get("stability") or 0) - (b.get("stability") or 0)) < (-stab_drop)  # Check stability drop
        dci = ((row.get("ci_width") or 0) - (b.get("ci_width") or 0)) > ci_increase  # Check CI width increase
        row.update({"drift_p": dp, "drift_stability": ds, "drift_ci": dci})  # Update row with drift flags
        out.append(row)                                     # Add row to output
    return out                                              # Return results with drift flags


def compare_row_to_baseline(row: Dict[str, Any], base_map: Dict[str, Dict[str, Any]],
                            p_thresh: float = DRIFT_P_THRESH_DEFAULT, stab_drop: float = DRIFT_STAB_DROP_DEFAULT, ci_increase: float = DRIFT_CI_INCREASE_DEFAULT) -> Dict[str, Any]:
    """Compare a single row to a baseline map and return a new row with drift flags."""  # Function purpose
    if p_thresh < 0 or stab_drop < 0 or ci_increase < 0:     # Check threshold validity
        raise ValueError("Drift thresholds must be non-negative.")  # Raise error for invalid thresholds
    claim = row["claim"]                                     # Get claim text from row
    b = base_map.get(claim)                                 # Look up baseline for this claim
    if not b:                                               # If no baseline found for claim
        return {**row, "drift_p": False, "drift_stability": False, "drift_ci": False}  # Return row with no drift flags
    dp = abs((row.get("p_RPL") or 0) - (b.get("p_RPL") or 0)) > p_thresh  # Check probability drift
    ds = ((row.get("stability") or 0) - (b.get("stability") or 0)) < (-stab_drop)  # Check stability drop
    dci = ((row.get("ci_width") or 0) - (b.get("ci_width") or 0)) > ci_increase  # Check CI width increase
    return {**row, "drift_p": dp, "drift_stability": ds, "drift_ci": dci}  # Return row with drift flags


def write_jsonl(rows: List[Dict[str, Any]], out_path: str) -> None:
    """Write list of dictionaries to JSONL format file."""   # Function purpose
    p = Path(out_path)                                       # Create Path object from output path
    p.parent.mkdir(parents=True, exist_ok=True)              # Create parent directories if needed
    with p.open("w") as f:                                   # Open file for writing
        for r in rows:                                       # Iterate through result rows
            f.write(json.dumps(r) + "\n")                    # Write each row as JSON line
