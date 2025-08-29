from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from heretix.config import RunConfig
from heretix.rpl import run_single_version


DB_PATH = Path("runs/heretix.sqlite")


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
    # First run: expect near-0 cache hit rate
    cfg = RunConfig(
        claim=f"tariffs don't cause inflation [cache_{tmp_path.name}]",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=8,
        R=2,
        T=8,
        B=5000,
        max_output_tokens=256,
    )
    prompt_file = str(Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml")
    res1 = run_single_version(cfg, prompt_file=prompt_file, mock=True)
    assert res1["aggregates"]["cache_hit_rate"] <= 0.1

    # Second identical run: expect high cache hit rate
    res2 = run_single_version(cfg, prompt_file=prompt_file, mock=True)
    assert res2["aggregates"]["cache_hit_rate"] >= 0.9

    # No-cache override: expect zero again
    cfg.no_cache = True
    res3 = run_single_version(cfg, prompt_file=prompt_file, mock=True)
    assert res3["aggregates"]["cache_hit_rate"] == 0.0
