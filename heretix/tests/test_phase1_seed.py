from __future__ import annotations

import os
from pathlib import Path

from heretix.config import RunConfig
from heretix.rpl import run_single_version


def test_config_seed_overrides_env(monkeypatch):
    # Set env seed but also set config seed; config should win
    monkeypatch.setenv("HERETIX_RPL_SEED", "9999")
    cfg = RunConfig(
        claim="seed precedence test",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=4,
        R=1,
        T=4,
        B=1000,
        seed=42,
        max_output_tokens=128,
    )
    prompt_file = str(Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml")
    res = run_single_version(cfg, prompt_file=prompt_file, mock=True)
    assert res["aggregation"]["bootstrap_seed"] == 42

