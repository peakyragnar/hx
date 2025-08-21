from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _safe_mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def summarize_jsonl(path: str) -> Dict[str, Any]:
    p = Path(path)
    rows: List[Dict[str, Any]] = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    n = len(rows)
    p_vals = [float(r.get("p_RPL")) for r in rows if r.get("p_RPL") is not None]
    widths = [float(r.get("ci_width")) for r in rows if r.get("ci_width") is not None]
    stabs = [float(r.get("stability")) for r in rows if r.get("stability") is not None]
    high = sum(1 for v in p_vals if v >= 0.9)
    low = sum(1 for v in p_vals if v <= 0.1)
    mid = sum(1 for v in p_vals if 0.4 <= v <= 0.6)
    drift_p = sum(1 for r in rows if r.get("drift_p"))
    drift_s = sum(1 for r in rows if r.get("drift_stability"))
    drift_ci = sum(1 for r in rows if r.get("drift_ci"))
    # Top 3 widest CIs
    widest = sorted(
        (
            (float(r.get("ci_width", 0.0)), str(r.get("claim", "")))
            for r in rows
        ),
        key=lambda x: x[0],
        reverse=True,
    )[:3]
    models = sorted({str(r.get("model")) for r in rows if r.get("model")})
    versions = sorted({str(r.get("prompt_version")) for r in rows if r.get("prompt_version")})

    return {
        "file": str(p),
        "n_rows": n,
        "models": models,
        "prompt_versions": versions,
        "mean_p": _safe_mean(p_vals),
        "mean_ci_width": _safe_mean(widths),
        "mean_stability": _safe_mean(stabs),
        "count_high_ge_0_9": high,
        "count_low_le_0_1": low,
        "count_mid_0_4_to_0_6": mid,
        "drift_counts": {"p": drift_p, "stability": drift_s, "ci": drift_ci},
        "widest_ci": [{"ci_width": w, "claim": c} for (w, c) in widest],
    }

