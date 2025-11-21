from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from heretix.config import RunConfig
from heretix.constants import SCHEMA_VERSION
from heretix.db.migrate import ensure_schema
from heretix.db.models import Check
from heretix.pipeline import PipelineOptions, perform_run


def _run_pipeline(tmp_path: Path):
    db_path = tmp_path / "checks.sqlite"
    db_url = f"sqlite:///{db_path}"
    ensure_schema(db_url)
    engine = create_engine(db_url, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    cfg = RunConfig(
        claim="Check metadata regression claim",
        model="gpt-5",
        provider="openai",
        prompt_version="rpl_g5_v2",
        K=4,
        R=1,
        T=4,
        B=500,
        max_output_tokens=256,
        max_prompt_chars=2000,
        no_cache=True,
    )

    with SessionLocal() as session:
        artifacts = perform_run(
            session=session,
            cfg=cfg,
            mode="baseline",
            options=PipelineOptions(),
            use_mock=True,
            user_id=None,
            anon_token=None,
            request_id=None,
        )
        session.commit()

    return artifacts, engine, SessionLocal


def test_check_persists_provider_and_cost_metadata(tmp_path: Path):
    artifacts, engine, SessionLocal = _run_pipeline(tmp_path)
    run_id = artifacts.result["run_id"]

    try:
        with SessionLocal() as session:
            stmt = select(Check).where(Check.run_id == run_id)
            check: Check = session.execute(stmt).scalar_one()

            assert check.provider == "openai"
            assert check.logical_model == "gpt-5"
            assert check.schema_version == SCHEMA_VERSION
            assert isinstance(check.tokens_in, int) and check.tokens_in > 0
            assert isinstance(check.tokens_out, int) and check.tokens_out > 0
            assert check.cost_usd is not None and float(check.cost_usd) > 0.0
    finally:
        engine.dispose()
