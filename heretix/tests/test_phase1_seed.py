from __future__ import annotations

import os
from pathlib import Path

from heretix.config import RunConfig
from heretix.rpl import run_single_version
from heretix.seed import make_bootstrap_seed


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


def test_make_bootstrap_seed_deterministic_and_order_invariant():
    base = make_bootstrap_seed(
        claim="order test",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        k=8,
        r=2,
        template_hashes=["ccc", "aaa", "bbb"],
        center="trimmed",
        trim=0.2,
        B=5000,
    )
    permuted = make_bootstrap_seed(
        claim="order test",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        k=8,
        r=2,
        template_hashes=["bbb", "ccc", "aaa"],
        center="trimmed",
        trim=0.2,
        B=5000,
    )
    assert base == permuted


def test_make_bootstrap_seed_changes_when_params_change():
    seed_a = make_bootstrap_seed(
        claim="same",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        k=8,
        r=2,
        template_hashes=["x", "y"],
        center="trimmed",
        trim=0.2,
        B=5000,
    )
    seed_b = make_bootstrap_seed(
        claim="same",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        k=8,
        r=2,
        template_hashes=["x", "y"],
        center="mean",
        trim=0.0,
        B=5000,
    )
    seed_c = make_bootstrap_seed(
        claim="same",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        k=8,
        r=2,
        template_hashes=["x", "y"],
        center="trimmed",
        trim=0.2,
        B=1000,
    )
    assert seed_a != seed_b
    assert seed_a != seed_c
