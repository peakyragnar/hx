from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from heretix.config import RunConfig
from heretix.db.migrate import ensure_schema
from heretix.pipeline import PipelineOptions, perform_run

EXPECTED_P = 0.2522065033414231
EXPECTED_CI = (0.23489284282029446, 0.2674774091536606)
EXPECTED_STABILITY = 0.5602924528340515
EXPECTED_COUNTS = {
    "c6b597e399db3d288f3acd4749126fdd6af3e50dd2692872c8731634e97ecb91": 2,
    "112c5fb6141301554380911b2b4f2be2632f896cd2a65f8d1a557ff67d933ec7": 2,
    "6e616b2ad88d245c0baaffd16ec4084399a0764b59d63800765f12825424d1d7": 2,
    "711e46f1d2afff9a9270e36fe31acc3cd2c375d323f33ad87e9a718e8c023e24": 2,
    "dbe048dd4fbec41311c53c7a73d75f5060190031345f9bf3236d80a83b79c165": 2,
    "a0881e23c0ce8ca903cff4620be7cc792ae69aea9ff8eb5c55897273a01a4a0a": 2,
}


def _run_pipeline(tmp_path: Path, mode: str):
    db_path = tmp_path / f"{mode}_checks.sqlite"
    db_url = f"sqlite:///{db_path}"
    ensure_schema(db_url)
    engine = create_engine(db_url, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    cfg = RunConfig(
        claim="RPL regression reference claim",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=6,
        R=2,
        T=6,
        B=500,
        seed=777,
        max_output_tokens=256,
        max_prompt_chars=2000,
        no_cache=True,
    )
    try:
        with SessionLocal() as session:
            artifacts = perform_run(
                session=session,
                cfg=cfg,
                mode=mode,
                options=PipelineOptions(),
                use_mock=True,
                user_id=None,
                anon_token=None,
                request_id=None,
            )
            session.commit()
            return artifacts
    finally:
        engine.dispose()


def test_baseline_metrics_align_with_reference(tmp_path: Path):
    artifacts = _run_pipeline(tmp_path, mode="baseline")
    aggregates = artifacts.result["aggregates"]
    aggregation = artifacts.result["aggregation"]
    assert aggregates["prob_true_rpl"] == pytest.approx(EXPECTED_P)
    assert aggregates["ci95"][0] == pytest.approx(EXPECTED_CI[0])
    assert aggregates["ci95"][1] == pytest.approx(EXPECTED_CI[1])
    assert aggregates["stability_score"] == pytest.approx(EXPECTED_STABILITY)
    assert aggregation["counts_by_template"] == EXPECTED_COUNTS
    assert aggregation["imbalance_ratio"] == pytest.approx(1.0)
    assert artifacts.prior_block["p"] == pytest.approx(EXPECTED_P)
    assert artifacts.combined_block["p"] == pytest.approx(EXPECTED_P)
    assert artifacts.weights["w_web"] == pytest.approx(0.0)


def test_web_informed_mock_matches_prior_metrics(tmp_path: Path):
    artifacts = _run_pipeline(tmp_path, mode="web_informed")
    aggregates = artifacts.result["aggregates"]
    aggregation = artifacts.result["aggregation"]
    assert aggregates["prob_true_rpl"] == pytest.approx(EXPECTED_P)
    assert aggregation["counts_by_template"] == EXPECTED_COUNTS
    assert aggregation["imbalance_ratio"] == pytest.approx(1.0)
    assert artifacts.prior_block["p"] == pytest.approx(EXPECTED_P)
    assert artifacts.web_block is not None
    assert artifacts.web_block["p"] == pytest.approx(EXPECTED_P)
    assert artifacts.weights is not None and artifacts.weights["w_web"] == pytest.approx(0.0)
    assert artifacts.combined_block["p"] == pytest.approx(EXPECTED_P)
