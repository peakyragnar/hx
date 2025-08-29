from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from heretix.config import RunConfig
from heretix.rpl import run_single_version


DB_PATH = Path("runs/heretix.sqlite")


def test_execution_row_and_mapping_created(tmp_path: Path):
    # unique claim to avoid cache confounds
    claim = f"exec mapping test [{tmp_path.name}]"
    cfg = RunConfig(
        claim=claim,
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=6,
        R=2,
        T=6,
        B=1000,
        max_output_tokens=128,
        seed=42,
    )
    prompt_file = str(Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml")
    res = run_single_version(cfg, prompt_file=prompt_file, mock=True)
    assert "execution_id" in res and res["execution_id"].startswith("exec-")
    run_id = res["run_id"]
    exec_id = res["execution_id"]

    # Aggregation counts sum
    agg = res["aggregation"]
    total_used = sum((agg["counts_by_template"][k] for k in agg["counts_by_template"]))

    conn = sqlite3.connect(str(DB_PATH))
    # Execution row exists and matches run_id
    row = conn.execute("SELECT run_id, bootstrap_seed FROM executions WHERE execution_id=?", (exec_id,)).fetchone()
    assert row is not None and row[0] == run_id

    # Mapping count equals number of used samples (valid only)
    (n_map,) = conn.execute("SELECT COUNT(*) FROM execution_samples WHERE execution_id=?", (exec_id,)).fetchone()
    assert n_map == total_used
    conn.close()

