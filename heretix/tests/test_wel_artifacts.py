from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pytest

from heretix.artifacts import get_artifact_store, write_web_artifact


@pytest.fixture(autouse=True)
def _reset_store_cache():
    # get_artifact_store is lru_cached; clear between tests
    get_artifact_store.cache_clear()  # type: ignore[attr-defined]
    try:
        yield
    finally:
        get_artifact_store.cache_clear()  # type: ignore[attr-defined]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_gzip_json(path: Path) -> list[dict]:
    data = gzip.decompress(path.read_bytes()).decode("utf-8")
    return json.loads(data)


def test_write_web_artifact_local_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HERETIX_ARTIFACT_BACKEND", "local")
    monkeypatch.setenv("HERETIX_ARTIFACT_PATH", str(tmp_path / "artifacts"))
    store = get_artifact_store()

    replicates = [
        {
            "replicate_idx": 0,
            "p_web": 0.25,
            "support_bullets": ["evidence A"],
            "oppose_bullets": ["counter A"],
            "notes": ["ok"],
            "json_valid": True,
        }
    ]

    record = write_web_artifact(
        run_id="test-run",
        claim="test claim",
        mode="web_informed",
        store=store,
        prior_block={"p": 0.2, "ci95": (0.1, 0.3)},
        web_block={"p": 0.25, "ci95": (0.1, 0.4), "replicates": replicates, "evidence": {"n_docs": 3}},
        combined_block={"p": 0.22, "ci95": (0.12, 0.33)},
        wel_provenance={"provider": "tavily", "seed": 42},
        replicates=replicates,
        debug_votes=[{"domain": "example.com", "stance": "support"}],
    )

    assert record is not None
    manifest_path = Path(record.manifest_uri)
    reps_path = Path(record.verdicts_uri)

    assert manifest_path.exists()
    assert reps_path.exists()

    manifest = _read_json(manifest_path)
    assert manifest["run_id"] == "test-run"
    assert manifest["web"]["p"] == 0.25
    assert manifest["replicates_uri"] == str(reps_path)

    assert record.docs_uri is None  # no Doc instances were provided

    reps = _read_gzip_json(reps_path)
    assert len(reps) == 1
    assert reps[0]["p_web"] == 0.25
    assert reps[0]["support_bullets"] == ["evidence A"]


def test_write_web_artifact_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HERETIX_ARTIFACT_BACKEND", "disabled")
    store = get_artifact_store()
    record = write_web_artifact(
        run_id="test-run",
        claim="test claim",
        mode="web_informed",
        store=store,
        prior_block={"p": 0.1, "ci95": (0.05, 0.2)},
        web_block={"p": 0.1, "ci95": (0.04, 0.2), "replicates": []},
        combined_block={"p": 0.1, "ci95": (0.05, 0.2)},
        wel_provenance=None,
        replicates=[],
        debug_votes=None,
    )
    assert record is None
