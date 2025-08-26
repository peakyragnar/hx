from __future__ import annotations

from pathlib import Path

from heretix.config import RunConfig
from heretix.rpl import run_single_version


def test_smoke_different_params(tmp_path: Path):
    cfg = RunConfig(
        claim="tariffs don't cause inflation",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=12,
        R=2,
        T=8,
        B=5000,
        max_output_tokens=256,
    )
    prompt_file = str(Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml")
    res = run_single_version(cfg, prompt_file=prompt_file, mock=True)
    a = res["aggregates"]
    assert 0.0 <= a["prob_true_rpl"] <= 1.0
    assert 0.0 < a["ci_width"] < 0.4
    assert 0.0 <= a["stability_score"] <= 1.0

