"""
Inspection utility for RPL run JSONs.

Summarizes per-template means (probability and logit), IQR(logit), stability,
headline CI, and counts/imbalance for transparency.
"""
from __future__ import annotations

import json
from typing import Dict, List
import numpy as np


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return float(np.log(p / (1 - p)))


def _sigmoid(x: float) -> float:
    x = float(np.clip(x, -709, 709))
    return float(1 / (1 + np.exp(-x)))


def summarize_run(run_path: str) -> str:
    doc = json.loads(open(run_path, "r").read())

    # Accept three shapes:
    # 1) Plain RPL run (evaluate_rpl_gpt5 output) with top-level paraphrase_results
    # 2) Orchestrator top-level (auto) with stages[] and final.stage_id
    # 3) A stage snapshot object that has raw_run

    root = None
    # Case 3: direct stage snapshot with raw_run
    if isinstance(doc, dict) and "raw_run" in doc:
        root = doc["raw_run"]
    # Case 2: orchestrator top-level
    elif isinstance(doc, dict) and "stages" in doc:
        stages = doc.get("stages", []) or []
        # Choose the final stage if identified; else last stage
        final_id = (doc.get("final") or {}).get("stage_id")
        stage = None
        if final_id:
            for s in stages:
                if s.get("stage_id") == final_id:
                    stage = s
                    break
        if stage is None and stages:
            stage = stages[-1]
        root = (stage or {}).get("raw_run", {})
    # Case 1: plain run
    else:
        root = doc

    par = root.get("paraphrase_results", [])
    by_tpl: Dict[str, List[float]] = {}
    for row in par:
        meta = row.get("meta", {})
        h = meta.get("prompt_sha256")
        raw = row.get("raw", {})
        if h is None or "prob_true" not in raw:
            continue
        by_tpl.setdefault(h, []).append(_logit(float(raw["prob_true"])))

    stats = []
    for h, L in by_tpl.items():
        arr = np.array(L, float)
        mean_l = float(arr.mean())
        mean_p = _sigmoid(mean_l)
        stats.append((h[:10], len(arr), mean_p, mean_l))
    stats.sort(key=lambda x: x[3])  # sort by logit

    tpl_means = np.array([s[3] for s in stats], float)
    if tpl_means.size > 0:
        iqr = float(np.percentile(tpl_means, 75) - np.percentile(tpl_means, 25))
        stability = 1.0 / (1.0 + iqr)
    else:
        iqr = 0.0
        stability = 0.0

    a = root.get("aggregates", {})
    lines = []
    lines.append(f"Claim: {root.get('claim', (doc.get('claim') if isinstance(doc, dict) else ''))}")
    lines.append(f"Model: {root.get('model', (doc.get('model') if isinstance(doc, dict) else ''))}")
    samp = root.get("sampling", {})
    lines.append(f"K={samp.get('K','?')}  R={samp.get('R','?')}  T={len(stats)}")
    lines.append("")
    lines.append("Per-template means (sorted by logit):")
    lines.append("  hash       n   mean_p   mean_logit")
    for h, n, mp, ml in stats:
        lines.append(f"  {h:<10} {n:<3d} {mp:7.3f}  {ml: .3f}")
    lines.append("")
    lines.append(f"IQR(logit) = {iqr:.3f}  → stability = {stability:.3f}")
    if a:
        ci = a.get("ci95", [None, None])
        lines.append(
            f"p_RPL = {a.get('prob_true_rpl', float('nan')):.3f}   CI95 = [{ci[0]:.3f}, {ci[1]:.3f}]   width = {a.get('ci_width', float('nan')):.3f}   is_stable = {str(a.get('is_stable', False))}"
        )
    return "\n".join(lines)
