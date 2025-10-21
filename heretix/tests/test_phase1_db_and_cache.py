from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from heretix.config import RunConfig
from heretix.rpl import run_single_version


# Tests use the mock provider; mock runs are routed to this DB
DB_PATH = Path("runs/heretix_mock.sqlite")


def test_db_row_count_matches_k_times_r(tmp_path: Path):
    cfg = RunConfig(
        claim=f"tariffs don't cause inflation [db_kxr_{tmp_path.name}]",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=12,
        R=3,
        T=8,
        B=5000,
        max_output_tokens=256,
    )
    prompt_file = str(Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml")
    res = run_single_version(cfg, prompt_file=prompt_file, mock=True)
    run_id = res["run_id"]
    assert DB_PATH.exists()
    conn = sqlite3.connect(str(DB_PATH))
    (n_samples,) = conn.execute("SELECT COUNT(*) FROM samples WHERE run_id=?", (run_id,)).fetchone()
    conn.close()
    assert n_samples == cfg.K * cfg.R


def test_cache_hit_behavior(tmp_path: Path):
    # Use a unique claim and force first run to bypass cache to avoid interference from existing DB state
    base = RunConfig(
        claim=f"tariffs don't cause inflation [cache_{tmp_path.name}]",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=8,
        R=2,
        T=8,
        B=5000,
        max_output_tokens=319,  # uncommon cap to reduce accidental reuse
    )
    prompt_file = str(Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml")

    # First run bypasses cache entirely
    cfg_clean = RunConfig(**{**base.__dict__})
    cfg_clean.no_cache = True
    res_clean = run_single_version(cfg_clean, prompt_file=prompt_file, mock=True)
    assert res_clean["aggregates"]["cache_hit_rate"] == 0.0

    # Second run populates run cache (may see sample hits from DB)
    cfg_populate = RunConfig(**{**base.__dict__})
    res_populate = run_single_version(cfg_populate, prompt_file=prompt_file, mock=True)
    assert res_populate["run_id"] == res_clean["run_id"]
    assert res_populate["execution_id"] != res_clean["execution_id"]

    # Third run should hit run cache and reuse populate execution payload
    cfg_cached = RunConfig(**{**base.__dict__})
    res_cached = run_single_version(cfg_cached, prompt_file=prompt_file, mock=True)
    assert res_cached["run_id"] == res_populate["run_id"]
    assert res_cached["execution_id"] == res_populate["execution_id"]
    assert res_cached["ci_status"]["phase"] == res_populate["ci_status"]["phase"]
