from __future__ import annotations

from pathlib import Path
import json

from heretix.config import RunConfig
from heretix.rpl import run_single_version


def test_smoke_mock_run(tmp_path: Path):
    cfg = RunConfig(
        claim="tariffs don't cause inflation",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=4,
        R=1,
        T=4,
        B=5000,
        max_output_tokens=256,
    )
    prompt_file = str(Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml")
    res = run_single_version(cfg, prompt_file=prompt_file, mock=True)
    a = res["aggregates"]
    assert 0.0 <= a["prob_true_rpl"] <= 1.0
    assert 0.0 <= a["ci95"][0] <= 1.0
    assert 0.0 <= a["ci95"][1] <= 1.0
    assert a["ci95"][0] <= a["ci95"][1]
    # write artifact
    out = tmp_path / "smoke.json"
    out.write_text(json.dumps(res))
    assert out.exists()

