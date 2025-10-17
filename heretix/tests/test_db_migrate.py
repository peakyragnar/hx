from __future__ import annotations

import sqlite3
from pathlib import Path

from heretix.db.migrate import ensure_schema


def test_ensure_schema_upgrades_existing_sqlite(tmp_path: Path):
    db_path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE checks (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            env TEXT,
            user_id TEXT,
            claim TEXT,
            model TEXT,
            prompt_version TEXT,
            K INTEGER,
            R INTEGER,
            T INTEGER,
            B INTEGER,
            seed TEXT,
            bootstrap_seed TEXT,
            max_output_tokens INTEGER,
            prob_true_rpl REAL,
            ci_lo REAL,
            ci_hi REAL,
            ci_width REAL,
            template_iqr_logit REAL,
            stability_score REAL,
            imbalance_ratio REAL,
            rpl_compliance_rate REAL,
            cache_hit_rate REAL,
            config_json TEXT,
            sampler_json TEXT,
            counts_by_template_json TEXT,
            artifact_json_path TEXT,
            mode TEXT
        )
        """
    )
    conn.execute("INSERT INTO checks (id, mode) VALUES ('run-1', '')")
    conn.commit()
    conn.close()

    ensure_schema(f"sqlite:///{db_path}")

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(checks)").fetchall()]
    assert "p_web" in cols
    mode_value = conn.execute("SELECT mode FROM checks WHERE id='run-1'").fetchone()[0]
    assert mode_value == "baseline"
    conn.close()
