"""
Tests for Auto-RPL orchestrator decisions and stage control.

These tests monkeypatch internal orchestration pieces to avoid network calls
and to force deterministic pass/fail of gates without relying on bootstrap math.
"""
from types import SimpleNamespace

import pytest

import heretix_rpl.orchestrator as orch


def _mk_mock_call():
    """Return a mock call_rpl_once_gpt5 that emits unique prompt hashes per template."""
    def _call(claim, paraphrase, model):
        h = str(abs(hash(paraphrase)))  # stable within process
        return {
            "model": model,
            "raw": {"prob_true": 0.5},
            "meta": {"prompt_sha256": h, "provider_model_id": model, "prompt_version": orch.PROMPT_VERSION},
        }
    return _call


def test_auto_rpl_passes_stage1(monkeypatch):
    # Force stage 1 to pass gates
    monkeypatch.setattr(orch, "call_rpl_once_gpt5", _mk_mock_call())

    def _agg_ok(claim, model, by_tpl, tpl_hashes):
        # Return narrow CI and high stability; balanced counts
        aggs = {
            "prob_true_rpl": 0.55,
            "ci95": [0.50, 0.60],
            "ci_width": 0.10,
            "paraphrase_iqr_logit": 0.05,
            "stability_score": 0.95,
            "stability_band": "high",
            "is_stable": True,
        }
        info = {
            "method": "equal_by_template_cluster_bootstrap_trimmed",
            "B": 5000,
            "center": "trimmed",
            "trim": 0.2,
            "min_samples": 3,
            "stability_width": 0.2,
            "bootstrap_seed": 123,
            "n_templates": len(by_tpl),
            "counts_by_template": {k: len(v) for k, v in by_tpl.items()},
            "imbalance_ratio": 1.0,
            "template_iqr_logit": 0.05,
        }
        # return ell_hat and CI in logit space (arbitrary, not used by gates directly)
        return 0.2, (0.1, 0.3), aggs, info

    monkeypatch.setattr(orch, "_aggregate", _agg_ok)

    res = orch.auto_rpl("claim", model="gpt-5", verbose=False)
    assert res["final"]["K"] in (8, min(8, len(orch.PARAPHRASES)))
    assert res["final"]["R"] == 2
    # Only one stage since it passed
    assert len(res["stages"]) == 1
    assert any(d["action"] == "stop_pass" for d in res["decision_log"])


def test_auto_rpl_escalates_then_passes(monkeypatch):
    monkeypatch.setattr(orch, "call_rpl_once_gpt5", _mk_mock_call())
    calls = {"n": 0}

    def _agg_maybe(claim, model, by_tpl, tpl_hashes):
        calls["n"] += 1
        # First stage fails gates; second stage passes
        if calls["n"] == 1:
            aggs = {
                "prob_true_rpl": 0.55,
                "ci95": [0.20, 0.80],
                "ci_width": 0.60,
                "paraphrase_iqr_logit": 0.5,
                "stability_score": 0.50,
                "stability_band": "low",
                "is_stable": False,
            }
            info = {"imbalance_ratio": 1.0, "counts_by_template": {k: len(v) for k, v in by_tpl.items()}, "n_templates": len(by_tpl)}
        else:
            aggs = {
                "prob_true_rpl": 0.52,
                "ci95": [0.45, 0.59],
                "ci_width": 0.14,
                "paraphrase_iqr_logit": 0.05,
                "stability_score": 0.90,
                "stability_band": "high",
                "is_stable": True,
            }
            info = {"imbalance_ratio": 1.0, "counts_by_template": {k: len(v) for k, v in by_tpl.items()}, "n_templates": len(by_tpl)}
        return 0.0, (0.0, 0.0), aggs, info

    monkeypatch.setattr(orch, "_aggregate", _agg_maybe)

    res = orch.auto_rpl("claim", model="gpt-5", verbose=False)
    # Expect at least 2 stages, with stop on stage 2
    assert len(res["stages"]) >= 2
    assert res["decision_log"][0]["action"].startswith("escalate_to_")
    assert any(d["action"] == "stop_pass" for d in res["decision_log"])


def test_auto_rpl_warns_on_imbalance(monkeypatch):
    monkeypatch.setattr(orch, "call_rpl_once_gpt5", _mk_mock_call())

    def _agg_warn(claim, model, by_tpl, tpl_hashes):
        aggs = {
            "prob_true_rpl": 0.55,
            "ci95": [0.50, 0.60],
            "ci_width": 0.10,
            "paraphrase_iqr_logit": 0.05,
            "stability_score": 0.95,
            "stability_band": "high",
            "is_stable": True,
        }
        info = {"imbalance_ratio": 1.30, "counts_by_template": {k: len(v) for k, v in by_tpl.items()}, "n_templates": len(by_tpl)}
        return 0.0, (0.0, 0.0), aggs, info

    monkeypatch.setattr(orch, "_aggregate", _agg_warn)
    res = orch.auto_rpl("claim", model="gpt-5", verbose=False)
    # Should pass with warning in decision log
    pass_logs = [d for d in res["decision_log"] if d["action"] == "stop_pass"]
    assert pass_logs and pass_logs[0].get("warning") == "imbalance_warn"

