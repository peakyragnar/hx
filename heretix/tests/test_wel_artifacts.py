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


def test_gcs_store_upload_private(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    get_artifact_store.cache_clear()  # type: ignore[attr-defined]

    class FakeBlob:
        def __init__(self):
            self.calls: list[str | None] = []

        def upload_from_string(self, payload, content_type=None, predefined_acl=None):
            self.calls.append(predefined_acl)

    fake_blob = FakeBlob()

    class FakeBucket:
        def __init__(self):
            self.name = "test-bucket"

        def blob(self, name):  # pragma: no cover - simple proxy
            fake_blob.name = name
            return fake_blob

    class FakeClient:
        def bucket(self, name):  # pragma: no cover - simple proxy
            assert name == "test-bucket"
            return FakeBucket()

    monkeypatch.setenv("HERETIX_ARTIFACT_BACKEND", "gcs")
    monkeypatch.setenv("HERETIX_ARTIFACT_BUCKET", "test-bucket")
    monkeypatch.delenv("HERETIX_ARTIFACT_PREFIX", raising=False)
    monkeypatch.setattr("google.cloud.storage.Client", lambda: FakeClient())

    store = get_artifact_store()
    uri = store.write_bytes("foo/bar.json", b"data", content_type="application/json")
    assert uri == "gs://test-bucket/foo/bar.json"
    assert fake_blob.calls == ["private"]

    get_artifact_store.cache_clear()  # type: ignore[attr-defined]


def test_gcs_store_upload_fallback(monkeypatch: pytest.MonkeyPatch):
    get_artifact_store.cache_clear()  # type: ignore[attr-defined]

    from google.api_core import exceptions as gcloud_exceptions

    class FakeBlob:
        def __init__(self):
            self.calls: list[str | None] = []
            self._failed = False

        def upload_from_string(self, payload, content_type=None, predefined_acl=None):
            self.calls.append(predefined_acl)
            if predefined_acl == "private" and not self._failed:
                self._failed = True
                raise gcloud_exceptions.BadRequest("uniform bucket access enabled")

    fake_blob = FakeBlob()

    class FakeBucket:
        def __init__(self):
            self.name = "test-bucket"

        def blob(self, name):
            return fake_blob

    class FakeClient:
        def bucket(self, name):
            return FakeBucket()

    monkeypatch.setenv("HERETIX_ARTIFACT_BACKEND", "gcs")
    monkeypatch.setenv("HERETIX_ARTIFACT_BUCKET", "test-bucket")
    monkeypatch.setattr("google.cloud.storage.Client", lambda: FakeClient())

    store = get_artifact_store()
    uri = store.write_bytes("foo.txt", b"data", content_type="text/plain")
    assert uri == "gs://test-bucket/foo.txt"
    assert fake_blob.calls == ["private", None]

    get_artifact_store.cache_clear()  # type: ignore[attr-defined]
