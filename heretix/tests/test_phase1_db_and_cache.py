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

    # First run (no cache): expect 0.0
    cfg1 = RunConfig(**{**base.__dict__})
    cfg1.no_cache = True
    res1 = run_single_version(cfg1, prompt_file=prompt_file, mock=True)
    assert res1["aggregates"]["cache_hit_rate"] == 0.0

    # Second identical run (use cache): expect high hit rate
    cfg2 = RunConfig(**{**base.__dict__})
    res2 = run_single_version(cfg2, prompt_file=prompt_file, mock=True)
    assert res2["aggregates"]["cache_hit_rate"] >= 0.9

    # No-cache override again: expect 0.0
    cfg3 = RunConfig(**{**base.__dict__})
    cfg3.no_cache = True
    res3 = run_single_version(cfg3, prompt_file=prompt_file, mock=True)
    assert res3["aggregates"]["cache_hit_rate"] == 0.0
