"""
Tests for inspect summarization and drift monitor helpers.

Covers summarize_run acceptance of different input shapes and drift flag logic.
"""
import json
from pathlib import Path

from heretix_rpl.inspect import summarize_run
from heretix_rpl.monitor import compare_row_to_baseline, compare_to_baseline


def _write(tmp_path: Path, name: str, obj: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(obj))
    return p


def test_inspect_plain_run(tmp_path):
    # Minimal plain run shape
    run = {
        "claim": "C",
        "model": "gpt-5",
        "aggregates": {"prob_true_rpl": 0.6, "ci95": [0.5, 0.7], "ci_width": 0.2, "is_stable": True},
        "paraphrase_results": [
            {"raw": {"prob_true": 0.6}, "meta": {"prompt_sha256": "h1"}},
            {"raw": {"prob_true": 0.5}, "meta": {"prompt_sha256": "h2"}},
            {"raw": {"prob_true": 0.7}, "meta": {"prompt_sha256": "h2"}},
        ],
        "sampling": {"K": 2, "R": 2},
    }
    p = _write(tmp_path, "plain.json", run)
    out = summarize_run(str(p))
    assert "IQR(logit)" in out and "p_RPL" in out


def test_inspect_orchestrator_top_level(tmp_path):
    # Orchestrator-like top level with stages and final pointer
    stage = {
        "stage_id": "S1-aaaa",
        "raw_run": {
            "claim": "C2",
            "model": "gpt-5",
            "aggregates": {"prob_true_rpl": 0.4, "ci95": [0.3, 0.5], "ci_width": 0.2, "is_stable": True},
            "paraphrase_results": [
                {"raw": {"prob_true": 0.4}, "meta": {"prompt_sha256": "hA"}},
                {"raw": {"prob_true": 0.5}, "meta": {"prompt_sha256": "hB"}},
            ],
            "sampling": {"K": 2, "R": 1},
        },
    }
    doc = {"stages": [stage], "final": {"stage_id": "S1-aaaa"}}
    p = _write(tmp_path, "auto.json", doc)
    out = summarize_run(str(p))
    assert "Per-template means" in out and "stability" in out


def test_inspect_stage_snapshot(tmp_path):
    # Direct stage snapshot object
    snap = {
        "raw_run": {
            "claim": "C3",
            "model": "gpt-5",
            "aggregates": {"prob_true_rpl": 0.5, "ci95": [0.45, 0.55], "ci_width": 0.10, "is_stable": True},
            "paraphrase_results": [
                {"raw": {"prob_true": 0.45}, "meta": {"prompt_sha256": "hX"}},
                {"raw": {"prob_true": 0.55}, "meta": {"prompt_sha256": "hX"}},
            ],
            "sampling": {"K": 1, "R": 2},
        }
    }
    p = _write(tmp_path, "stage.json", snap)
    out = summarize_run(str(p))
    assert "K=1  R=2" in out


def test_compare_row_to_baseline_flags():
    base = {"claim": "X", "p_RPL": 0.5, "stability": 0.9, "ci_width": 0.1}
    row_same = {"claim": "X", "p_RPL": 0.55, "stability": 0.85, "ci_width": 0.15}
    # Defaults: p_thresh=0.10, stab_drop=0.20, ci_increase=0.10
    flagged = compare_row_to_baseline(row_same, {"X": base})
    assert flagged["drift_p"] is False
    assert flagged["drift_stability"] is False
    assert flagged["drift_ci"] is False

    row_drift = {"claim": "X", "p_RPL": 0.7, "stability": 0.6, "ci_width": 0.25}
    flagged2 = compare_row_to_baseline(row_drift, {"X": base})
    assert flagged2["drift_p"] is True
    assert flagged2["drift_stability"] is True
    assert flagged2["drift_ci"] is True


def test_compare_to_baseline_validation():
    rows = [{"claim": "X", "p_RPL": 0.5, "stability": 0.9, "ci_width": 0.1}]
    try:
        compare_to_baseline(rows, baseline=None, p_thresh=-0.1)
        assert False, "negative threshold should raise"
    except ValueError:
        pass

