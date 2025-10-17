from __future__ import annotations

import os
import threading
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine


_MIGRATION_LOCK = threading.Lock()
_MIGRATED_URLS: set[str] = set()


def ensure_schema(database_url: str) -> None:
    """
    Idempotently apply Alembic migrations for the supplied database URL.
    """
    if not database_url:
        raise ValueError("database_url must be provided")

    with _MIGRATION_LOCK:
        # Avoid re-running migrations for the same URL within this process.
        if database_url in _MIGRATED_URLS:
            return

        repo_root = Path(__file__).resolve().parents[2]

        if database_url.startswith("sqlite"):
            engine = create_engine(database_url, future=True)
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    """
                    CREATE TABLE IF NOT EXISTS checks (
                        id TEXT PRIMARY KEY,
                        run_id TEXT UNIQUE,
                        env TEXT NOT NULL,
                        user_id TEXT,
                        claim TEXT,
                        claim_hash TEXT,
                        model TEXT NOT NULL,
                        prompt_version TEXT NOT NULL,
                        K INTEGER NOT NULL,
                        R INTEGER NOT NULL,
                        T INTEGER,
                        B INTEGER,
                        seed NUMERIC,
                        bootstrap_seed NUMERIC,
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
                        prompt_char_len_max INTEGER,
                        pqs REAL,
                        gate_compliance_ok INTEGER,
                        gate_stability_ok INTEGER,
                        gate_precision_ok INTEGER,
                        pqs_version TEXT,
                        mode TEXT NOT NULL DEFAULT 'baseline',
                        p_prior REAL,
                        ci_prior_lo REAL,
                        ci_prior_hi REAL,
                        stability_prior REAL,
                        p_web REAL,
                        ci_web_lo REAL,
                        ci_web_hi REAL,
                        n_docs INTEGER,
                        n_domains INTEGER,
                        median_age_days REAL,
                        web_dispersion REAL,
                        json_valid_rate REAL,
                        date_confident_rate REAL,
                        n_confident_dates REAL,
                        p_combined REAL,
                        ci_combined_lo REAL,
                        ci_combined_hi REAL,
                        w_web REAL,
                        recency_score REAL,
                        strength_score REAL,
                        resolved_flag INTEGER,
                        resolved_truth INTEGER,
                        resolved_reason TEXT,
                        resolved_support REAL,
                        resolved_contradict REAL,
                        resolved_domains INTEGER,
                        resolved_citations TEXT,
                        was_cached INTEGER NOT NULL DEFAULT 0,
                        provider_model_id TEXT,
                        anon_token TEXT,
                        created_at TEXT,
                        finished_at TEXT
                    )
                    """
                )
                existing_cols = {
                    row[1]
                    for row in conn.exec_driver_sql("PRAGMA table_info(checks)").fetchall()
                }

                column_defs = [
                    ("env", "TEXT"),
                    ("user_id", "TEXT"),
                    ("claim_hash", "TEXT"),
                    ("prompt_char_len_max", "INTEGER"),
                    ("pqs", "REAL"),
                    ("gate_compliance_ok", "INTEGER"),
                    ("gate_stability_ok", "INTEGER"),
                    ("gate_precision_ok", "INTEGER"),
                    ("pqs_version", "TEXT"),
                    ("cache_hit_rate", "REAL"),
                    ("config_json", "TEXT"),
                    ("sampler_json", "TEXT"),
                    ("counts_by_template_json", "TEXT"),
                    ("artifact_json_path", "TEXT"),
                    ("mode", "TEXT"),
                    ("p_prior", "REAL"),
                    ("ci_prior_lo", "REAL"),
                    ("ci_prior_hi", "REAL"),
                    ("stability_prior", "REAL"),
                    ("p_web", "REAL"),
                    ("ci_web_lo", "REAL"),
                    ("ci_web_hi", "REAL"),
                    ("n_docs", "INTEGER"),
                    ("n_domains", "INTEGER"),
                    ("median_age_days", "REAL"),
                    ("web_dispersion", "REAL"),
                    ("json_valid_rate", "REAL"),
                    ("date_confident_rate", "REAL"),
                    ("n_confident_dates", "REAL"),
                    ("p_combined", "REAL"),
                    ("ci_combined_lo", "REAL"),
                    ("ci_combined_hi", "REAL"),
                    ("w_web", "REAL"),
                    ("recency_score", "REAL"),
                    ("strength_score", "REAL"),
                    ("resolved_flag", "INTEGER"),
                    ("resolved_truth", "INTEGER"),
                    ("resolved_reason", "TEXT"),
                    ("resolved_support", "REAL"),
                    ("resolved_contradict", "REAL"),
                    ("resolved_domains", "INTEGER"),
                    ("resolved_citations", "TEXT"),
                    ("was_cached", "INTEGER"),
                    ("provider_model_id", "TEXT"),
                    ("anon_token", "TEXT"),
                    ("created_at", "TEXT"),
                    ("finished_at", "TEXT"),
                ]

                known_columns = {name for name, _ in column_defs}

                for column, ddl in column_defs:
                    if column not in existing_cols:
                        conn.exec_driver_sql(
                            'ALTER TABLE checks ADD COLUMN "{}" {}'.format(column, ddl)
                        )
                        existing_cols.add(column)

                if "mode" in existing_cols:
                    conn.exec_driver_sql(
                        "UPDATE checks SET mode='baseline' WHERE mode IS NULL OR TRIM(mode) = ''"
                    )
                if "was_cached" in existing_cols:
                    conn.exec_driver_sql("UPDATE checks SET was_cached=0 WHERE was_cached IS NULL")

                index_defs = {
                    "ix_checks_user_id": ("user_id",),
                    "ix_checks_env": ("env",),
                    "ix_checks_claim_hash": ("claim_hash",),
                    "ix_checks_env_anon_token": ("env", "anon_token"),
                }

                for index_name, cols in index_defs.items():
                    if all(col in existing_cols for col in cols):
                        conn.exec_driver_sql(
                            f"CREATE INDEX IF NOT EXISTS {index_name} ON checks({','.join(f'"{col}"' for col in cols)})"
                        )
            _MIGRATED_URLS.add(database_url)
            return
        alembic_cfg = Config(str(repo_root / "alembic.ini"))
        # Ensure script_location resolves correctly when invoked from arbitrary cwd.
        alembic_cfg.set_main_option("script_location", str(repo_root / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)

        # Alembic reads alembic.ini from CWD; mimic CLI behaviour by ensuring cwd does not matter.
        env = os.environ.copy()
        env["DATABASE_URL"] = database_url

        command.upgrade(alembic_cfg, "head")
        _MIGRATED_URLS.add(database_url)
