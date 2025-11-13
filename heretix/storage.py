from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import os
import time
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_DB_PATH = Path("runs/heretix.sqlite")


def _db_path_from_env(override: Path | None = None) -> Path:
    """Resolve the SQLite DB path with optional env override.

    Precedence: explicit override > HERETIX_DB_PATH env > DEFAULT_DB_PATH.
    """
    if override is not None:
        return override
    p = os.getenv("HERETIX_DB_PATH")
    return Path(p) if p else DEFAULT_DB_PATH


def _ensure_db(path: Path | None = None) -> sqlite3.Connection:
    path_resolved = _db_path_from_env(path)
    path_resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path_resolved))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            created_at INTEGER,
            claim TEXT,
            model TEXT,
            provider TEXT,
            logical_model TEXT,
            prompt_version TEXT,
            schema_version TEXT,
            K INTEGER,
            R INTEGER,
            T INTEGER,
            B INTEGER,
            seed TEXT,
            bootstrap_seed TEXT,
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
            tokens_in INTEGER,
            tokens_out INTEGER,
            cost_usd REAL
        )
        """
    )
    # Attempt to add new columns for forward-compat schema
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN prompt_char_len_max INTEGER")
    except Exception:
        pass
    for sql in [
        "ALTER TABLE runs ADD COLUMN provider TEXT",
        "ALTER TABLE runs ADD COLUMN logical_model TEXT",
        "ALTER TABLE runs ADD COLUMN schema_version TEXT",
        "ALTER TABLE runs ADD COLUMN tokens_in INTEGER",
        "ALTER TABLE runs ADD COLUMN tokens_out INTEGER",
        "ALTER TABLE runs ADD COLUMN cost_usd REAL",
    ]:
        try:
            conn.execute(sql)
        except Exception:
            pass
    # PQS and gate columns for runs
    for sql in [
        "ALTER TABLE runs ADD COLUMN pqs INTEGER",
        "ALTER TABLE runs ADD COLUMN gate_compliance_ok INTEGER",
        "ALTER TABLE runs ADD COLUMN gate_stability_ok INTEGER",
        "ALTER TABLE runs ADD COLUMN gate_precision_ok INTEGER",
        "ALTER TABLE runs ADD COLUMN pqs_version TEXT",
    ]:
        try:
            conn.execute(sql)
        except Exception:
            pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS samples (
            run_id TEXT,
            cache_key TEXT,
            prompt_sha256 TEXT,
            paraphrase_idx INTEGER,
            replicate_idx INTEGER,
            prob_true REAL,
            logit REAL,
            provider_model_id TEXT,
            response_id TEXT,
            created_at INTEGER,
            tokens_out INTEGER,
            latency_ms REAL,
            json_valid INTEGER,
            PRIMARY KEY (cache_key),
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        )
        """
    )
    # Executions: immutable per-invocation summaries
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS executions (
            execution_id TEXT PRIMARY KEY,
            run_id TEXT,
            created_at INTEGER,
            claim TEXT,
            model TEXT,
            prompt_version TEXT,
            K INTEGER,
            R INTEGER,
            T INTEGER,
            B INTEGER,
            seed TEXT,
            bootstrap_seed TEXT,
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
            prompt_char_len_max INTEGER,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        )
        """
    )
    # PQS and gate columns for executions
    for sql in [
        "ALTER TABLE executions ADD COLUMN pqs INTEGER",
        "ALTER TABLE executions ADD COLUMN gate_compliance_ok INTEGER",
        "ALTER TABLE executions ADD COLUMN gate_stability_ok INTEGER",
        "ALTER TABLE executions ADD COLUMN gate_precision_ok INTEGER",
        "ALTER TABLE executions ADD COLUMN pqs_version TEXT",
    ]:
        try:
            conn.execute(sql)
        except Exception:
            pass
    # Mapping of which cached samples were used by an execution
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_samples (
            execution_id TEXT,
            cache_key TEXT,
            PRIMARY KEY (execution_id, cache_key),
            FOREIGN KEY (execution_id) REFERENCES executions(execution_id),
            FOREIGN KEY (cache_key) REFERENCES samples(cache_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS result_cache (
            key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            computed_at INTEGER NOT NULL,
            ttl_seconds INTEGER NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_prompt_model ON runs(prompt_version, model)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_run ON samples(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_run ON executions(run_id)")
    # Prompts table stores full prompt text by prompt_version for provenance
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompts (
            prompt_version TEXT PRIMARY KEY,
            yaml_hash TEXT,
            system_text TEXT,
            user_template TEXT,
            paraphrases_json TEXT,
            source_path TEXT,
            created_at INTEGER,
            author_note TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prompts_hash ON prompts(yaml_hash)")
    return conn


def insert_run(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    cols = ",".join(row.keys())
    q = f"INSERT OR REPLACE INTO runs ({cols}) VALUES ({','.join(['?']*len(row))})"
    conn.execute(q, list(row.values()))
    conn.commit()


def insert_samples(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    q = f"INSERT OR REPLACE INTO samples ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"
    conn.executemany(q, [[r[c] for c in cols] for r in rows])
    conn.commit()


def get_cached_sample(cache_key: str, db_path: Path | None = None) -> Optional[Dict[str, Any]]:
    conn = _ensure_db(db_path)
    cur = conn.execute("SELECT * FROM samples WHERE cache_key=?", (cache_key,))
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return {k: row[i] for i, k in enumerate(cols)}


def get_cached_run(key: str, *, db_path: Path | None = None, ttl_seconds: int = 259200) -> Optional[Dict[str, Any]]:
    conn = _ensure_db(db_path)
    cur = conn.execute("SELECT payload_json, computed_at, ttl_seconds FROM result_cache WHERE key=?", (key,))
    row = cur.fetchone()
    if not row:
        return None
    payload_json, computed_at, ttl_row = row
    if ttl_row is None:
        ttl_row = ttl_seconds
    if int(time.time()) > int(computed_at) + int(ttl_row):
        conn.execute("DELETE FROM result_cache WHERE key=?", (key,))
        conn.commit()
        return None
    return json.loads(payload_json)


def set_cached_run(key: str, payload: Dict[str, Any], ttl_seconds: int, *, db_path: Path | None = None) -> None:
    conn = _ensure_db(db_path)
    conn.execute(
        """
        INSERT INTO result_cache (key, payload_json, computed_at, ttl_seconds)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET payload_json=excluded.payload_json, computed_at=excluded.computed_at, ttl_seconds=excluded.ttl_seconds
        """,
        (key, json.dumps(payload), int(time.time()), int(ttl_seconds)),
    )
    conn.commit()


def update_run_ci(conn: sqlite3.Connection, run_id: str, *, ci_lo: float, ci_hi: float, ci_width: float, B: int):
    conn.execute(
        "UPDATE runs SET ci_lo=?, ci_hi=?, ci_width=?, B=? WHERE run_id=?",
        (ci_lo, ci_hi, ci_width, B, run_id),
    )
    conn.commit()


def update_execution_ci(conn: sqlite3.Connection, execution_id: str, *, ci_lo: float, ci_hi: float, ci_width: float, B: int):
    conn.execute(
        "UPDATE executions SET ci_lo=?, ci_hi=?, ci_width=?, B=? WHERE execution_id=?",
        (ci_lo, ci_hi, ci_width, B, execution_id),
    )
    conn.commit()


def insert_execution(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    cols = ",".join(row.keys())
    q = f"INSERT OR REPLACE INTO executions ({cols}) VALUES ({','.join(['?']*len(row))})"
    conn.execute(q, list(row.values()))
    conn.commit()


def insert_execution_samples(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    q = f"INSERT OR REPLACE INTO execution_samples ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"
    conn.executemany(q, [[r[c] for c in cols] for r in rows])
    conn.commit()


def update_run_artifact_path(conn: sqlite3.Connection, run_id: str, artifact_path: str) -> None:
    conn.execute(
        "UPDATE runs SET artifact_json_path=? WHERE run_id=?",
        (artifact_path, run_id),
    )
    conn.commit()


def insert_prompt(
    conn: sqlite3.Connection,
    *,
    prompt_version: str,
    yaml_hash: str,
    system_text: str,
    user_template: str,
    paraphrases_json: str,
    source_path: str | None,
    created_at: int,
    author_note: str | None = None,
) -> None:
    """Insert prompt text for a given version if not already present.

    If a row exists with the same version but a different yaml_hash, the existing
    row is kept (append-only by version); no overwrite occurs.
    """
    cur = conn.execute(
        "SELECT yaml_hash FROM prompts WHERE prompt_version=?",
        (prompt_version,),
    )
    row = cur.fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO prompts (
                prompt_version, yaml_hash, system_text, user_template,
                paraphrases_json, source_path, created_at, author_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prompt_version,
                yaml_hash,
                system_text,
                user_template,
                paraphrases_json,
                source_path,
                created_at,
                author_note,
            ),
        )
        conn.commit()
    else:
        # If existing hash differs, do not overwrite; leave as-is for auditability.
        try:
            existing_hash = row[0]
            if existing_hash != yaml_hash:
                # Best-effort informational print; avoid raising.
                print(
                    f"WARN: prompts[{prompt_version}] exists with different yaml_hash; keeping existing row.")
        except Exception:
            pass
