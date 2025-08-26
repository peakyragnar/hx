"""
Tests for summarize_jsonl helper.

Creates a small JSONL file, verifies means, counts, and top-3 widest reporting.
"""
import json
from pathlib import Path

from heretix_rpl.summarize import summarize_jsonl


def test_summarize_jsonl(tmp_path):
    rows = [
        {"claim": "a", "model": "gpt-5", "prompt_version": "v", "p_RPL": 0.95, "ci_width": 0.05, "stability": 0.95, "drift_p": False, "drift_stability": False, "drift_ci": False},
        {"claim": "b", "model": "gpt-5", "prompt_version": "v", "p_RPL": 0.05, "ci_width": 0.20, "stability": 0.80, "drift_p": True,  "drift_stability": False, "drift_ci": True},
        {"claim": "c", "model": "gpt-5", "prompt_version": "v", "p_RPL": 0.50, "ci_width": 0.30, "stability": 0.60, "drift_p": False, "drift_stability": True,  "drift_ci": False},
        {"claim": "d", "model": "gpt-5", "prompt_version": "v", "p_RPL": 0.60, "ci_width": 0.10, "stability": 0.90, "drift_p": False, "drift_stability": False, "drift_ci": False},
    ]
    p = tmp_path / "rows.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))

    s = summarize_jsonl(str(p))
    assert s["n_rows"] == 4
    assert set(s["models"]) == {"gpt-5"}
    assert set(s["prompt_versions"]) == {"v"}
    # Basic count checks
    assert s["count_high_ge_0_9"] == 1
    assert s["count_low_le_0_1"] == 1
    assert s["count_mid_0_4_to_0_6"] >= 1
    # Drift counts aggregated
    dc = s["drift_counts"]
    assert dc["p"] == 1 and dc["stability"] == 1 and dc["ci"] == 1
    # Widest top-3 present and sorted
    widest = s["widest_ci"]
    assert len(widest) == 3
    widths = [w["ci_width"] for w in widest]
    assert widths == sorted(widths, reverse=True)

