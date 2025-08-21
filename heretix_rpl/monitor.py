"""
Lightweight drift monitor for RPL.

Runs a sentinel set of claims at fixed settings and records p, CI width,
and stability. Compares to an optional baseline to flag drift.
"""
from __future__ import annotations

import json, time
from pathlib import Path
from typing import List, Dict, Any, Optional

from heretix_rpl.rpl_eval import evaluate_rpl_gpt5
from heretix_rpl.rpl_prompts import PROMPT_VERSION
from heretix_rpl.constants import (
    DRIFT_P_THRESH_DEFAULT,
    DRIFT_STAB_DROP_DEFAULT,
    DRIFT_CI_INCREASE_DEFAULT,
)


def run_bench(bench_path: str, model: str = "gpt-5", K: int = 8, R: int = 2) -> List[Dict[str, Any]]:
    """Run the full bench and return all rows (blocking)."""
    bench = json.loads(Path(bench_path).read_text())
    out: List[Dict[str, Any]] = []
    for item in bench:
        claim = item["claim"]
        res = evaluate_rpl_gpt5(claim, model=model, K=K, R=R, agg="clustered")
        a = res["aggregates"]
        out.append({
            "timestamp": int(time.time()),
            "claim": claim,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "p_RPL": a.get("prob_true_rpl"),
            "ci95": a.get("ci95"),
            "ci_width": a.get("ci_width"),
            "stability": a.get("stability_score"),
        })
    return out


def run_bench_iter(bench_path: str, model: str = "gpt-5", K: int = 8, R: int = 2, verbose: bool = False, claims: Optional[List[str]] = None):
    """Yield one result row per claim; useful for streaming output/progress.

    If `claims` is provided, iterate over that list instead of reading all from bench_path.
    """
    bench_items = json.loads(Path(bench_path).read_text())
    claim_list = claims if claims is not None else [x["claim"] for x in bench_items]
    total = len(claim_list)
    for i, claim in enumerate(claim_list, start=1):
        if verbose:
            print(f"[monitor] {i}/{total}: {claim} (K={K}, R={R})", flush=True)
        res = evaluate_rpl_gpt5(claim, model=model, K=K, R=R, agg="clustered")
        a = res["aggregates"]
        yield {
            "timestamp": int(time.time()),
            "claim": claim,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "p_RPL": a.get("prob_true_rpl"),
            "ci95": a.get("ci95"),
            "ci_width": a.get("ci_width"),
            "stability": a.get("stability_score"),
        }


def compare_to_baseline(current: List[Dict[str, Any]], baseline: Optional[List[Dict[str, Any]]] = None,
                        p_thresh: float = DRIFT_P_THRESH_DEFAULT, stab_drop: float = DRIFT_STAB_DROP_DEFAULT, ci_increase: float = DRIFT_CI_INCREASE_DEFAULT) -> List[Dict[str, Any]]:
    # Validate thresholds (non-negative)
    if p_thresh < 0 or stab_drop < 0 or ci_increase < 0:
        raise ValueError("Drift thresholds must be non-negative.")
    if not baseline:
        # No baseline: mark no drift
        for row in current:
            row.update({"drift_p": False, "drift_stability": False, "drift_ci": False})
        return current
    base_map = {r["claim"]: r for r in baseline}
    out = []
    for row in current:
        claim = row["claim"]
        b = base_map.get(claim)
        if not b:
            row.update({"drift_p": False, "drift_stability": False, "drift_ci": False})
            out.append(row)
            continue
        dp = abs((row.get("p_RPL") or 0) - (b.get("p_RPL") or 0)) > p_thresh
        ds = ((row.get("stability") or 0) - (b.get("stability") or 0)) < (-stab_drop)
        dci = ((row.get("ci_width") or 0) - (b.get("ci_width") or 0)) > ci_increase
        row.update({"drift_p": dp, "drift_stability": ds, "drift_ci": dci})
        out.append(row)
    return out


def compare_row_to_baseline(row: Dict[str, Any], base_map: Dict[str, Dict[str, Any]],
                            p_thresh: float = DRIFT_P_THRESH_DEFAULT, stab_drop: float = DRIFT_STAB_DROP_DEFAULT, ci_increase: float = DRIFT_CI_INCREASE_DEFAULT) -> Dict[str, Any]:
    """Compare a single row to a baseline map and return a new row with drift flags."""
    if p_thresh < 0 or stab_drop < 0 or ci_increase < 0:
        raise ValueError("Drift thresholds must be non-negative.")
    claim = row["claim"]
    b = base_map.get(claim)
    if not b:
        return {**row, "drift_p": False, "drift_stability": False, "drift_ci": False}
    dp = abs((row.get("p_RPL") or 0) - (b.get("p_RPL") or 0)) > p_thresh
    ds = ((row.get("stability") or 0) - (b.get("stability") or 0)) < (-stab_drop)
    dci = ((row.get("ci_width") or 0) - (b.get("ci_width") or 0)) > ci_increase
    return {**row, "drift_p": dp, "drift_stability": ds, "drift_ci": dci}


def write_jsonl(rows: List[Dict[str, Any]], out_path: str) -> None:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
