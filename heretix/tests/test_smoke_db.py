from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from heretix.config import RunConfig
from heretix.rpl import run_single_version


# Tests use the mock provider; mock runs are routed to this DB
DB_PATH = Path("runs/heretix_mock.sqlite")


def test_db_persistence_and_counts(tmp_path: Path):
    cfg = RunConfig(
        claim=f"tariffs don't cause inflation [db_smoke_{tmp_path.name}]",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=3,
        R=1,
        T=3,
        B=5000,
        max_output_tokens=128,
    )
    prompt_file = str(Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml")
    res = run_single_version(cfg, prompt_file=prompt_file, mock=True)

    # Validate aggregation counts from JSON
    agg = res["aggregation"]
    counts = agg["counts_by_template"]
    assert isinstance(counts, dict) and len(counts) == agg["n_templates"]
    assert sum(counts.values()) == cfg.K * cfg.R

    # Check DB persisted data
    assert DB_PATH.exists()
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute("SELECT * FROM runs WHERE run_id=?", (res["run_id"],))
    row = cur.fetchone()
    assert row is not None

    # Column names mapping
    columns = [d[0] for d in cur.description]
    doc = {k: row[i] for i, k in enumerate(columns)}

    # sampler_json and counts_by_template_json should be present and parseable
    sampler = json.loads(doc["sampler_json"]) if doc.get("sampler_json") else {}
    counts_db = json.loads(doc["counts_by_template_json"]) if doc.get("counts_by_template_json") else {}
    assert isinstance(sampler, dict) and "tpl_indices" in sampler
    assert isinstance(counts_db, dict) and len(counts_db) == agg["n_templates"]

    # samples rows count equals K*R
    cur2 = conn.execute("SELECT COUNT(*) FROM samples WHERE run_id=?", (res["run_id"],))
    (n_samples,) = cur2.fetchone()
    assert n_samples == cfg.K * cfg.R

    # Seeds persisted; type may be coerced by SQLite, but string form must be non-empty
    assert str(doc["bootstrap_seed"]) and len(str(doc["bootstrap_seed"])) > 0
    # cleanup connection
    conn.close()
