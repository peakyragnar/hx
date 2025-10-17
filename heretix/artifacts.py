from __future__ import annotations

import gzip
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Protocol, Tuple

from heretix_wel.types import Doc, WELReplicate


class ArtifactStore(Protocol):
    """Minimal interface for uploading artifact blobs."""

    def write_text(self, relative_path: str, text: str, content_type: str | None = None) -> str:
        ...

    def write_bytes(self, relative_path: str, payload: bytes, content_type: str | None = None) -> str:
        ...

    @property
    def root(self) -> str:
        ...


@dataclass
class ArtifactRecord:
    artifact_id: str
    manifest_uri: str
    verdicts_uri: Optional[str]
    docs_uri: Optional[str]
    local: bool


class _DisabledStore:
    root = ""

    def write_text(self, relative_path: str, text: str, content_type: str | None = None) -> str:
        raise RuntimeError("Artifact store is disabled")

    def write_bytes(self, relative_path: str, payload: bytes, content_type: str | None = None) -> str:
        raise RuntimeError("Artifact store is disabled")


class _LocalStore:
    def __init__(self, base_path: Path) -> None:
        self._root = base_path
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> str:
        return str(self._root)

    def write_text(self, relative_path: str, text: str, content_type: str | None = None) -> str:
        dest = self._root / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        return str(dest)

    def write_bytes(self, relative_path: str, payload: bytes, content_type: str | None = None) -> str:
        dest = self._root / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        return str(dest)


class _GCSStore:
    def __init__(self, bucket: str, prefix: str) -> None:
        try:
            from google.cloud import storage  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "google-cloud-storage is required for GCS artifact backend; install it first"
            ) from exc

        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket)
        self._prefix = prefix.rstrip("/")

    @property
    def root(self) -> str:
        return f"gs://{self._bucket.name}/{self._prefix}" if self._prefix else f"gs://{self._bucket.name}"

    def _blob_path(self, relative_path: str) -> str:
        relative = relative_path.lstrip("/")
        if self._prefix:
            return f"{self._prefix}/{relative}"
        return relative

    def write_text(self, relative_path: str, text: str, content_type: str | None = None) -> str:
        data = text.encode("utf-8")
        return self.write_bytes(relative_path, data, content_type=content_type or "application/json")

    def write_bytes(self, relative_path: str, payload: bytes, content_type: str | None = None) -> str:
        blob_name = self._blob_path(relative_path)
        blob = self._bucket.blob(blob_name)
        try:
            blob.upload_from_string(payload, content_type=content_type, predefined_acl="private")
        except TypeError:
            blob.upload_from_string(payload, content_type=content_type)
        except Exception as exc:
            try:
                from google.api_core import exceptions as gcloud_exceptions  # type: ignore

                if isinstance(exc, gcloud_exceptions.BadRequest):
                    blob.upload_from_string(payload, content_type=content_type)
                else:  # pragma: no cover - unexpected error; re-raise
                    raise
            except ImportError:  # pragma: no cover - optional dependency already loaded
                blob.upload_from_string(payload, content_type=content_type)
        return f"gs://{self._bucket.name}/{blob_name}"


@lru_cache(maxsize=1)
def get_artifact_store() -> ArtifactStore:
    backend = os.getenv("HERETIX_ARTIFACT_BACKEND", "").strip().lower()
    if backend in {"disabled", "none", "off"}:
        return _DisabledStore()
    if backend in {"", "local", "filesystem", "fs"}:
        base = Path(os.getenv("HERETIX_ARTIFACT_PATH", "runs/artifacts"))
        return _LocalStore(base)
    if backend in {"gcs", "google"}:
        bucket = os.getenv("HERETIX_ARTIFACT_BUCKET")
        if not bucket:
            raise RuntimeError("HERETIX_ARTIFACT_BUCKET must be set for GCS artifact backend")
        prefix = os.getenv("HERETIX_ARTIFACT_PREFIX", "").strip("/")
        return _GCSStore(bucket=bucket, prefix=prefix)
    raise RuntimeError(f"Unknown HERETIX_ARTIFACT_BACKEND: {backend}")


def _doc_to_dict(doc: Doc) -> Dict[str, Any]:
    return {
        "url": doc.url,
        "domain": doc.domain,
        "title": doc.title,
        "snippet": doc.snippet,
        "published_at": doc.published_at.isoformat() if doc.published_at else None,
        "published_method": doc.published_method,
        "published_confidence": doc.published_confidence,
    }


def _serialize_replicates(replicates: Iterable[Any]) -> Tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    doc_index: Dict[str, Dict[str, Any]] = {}
    rep_payload: list[Dict[str, Any]] = []

    for raw in replicates:
        if isinstance(raw, dict):
            rep_payload.append(raw)
            continue

        if not isinstance(raw, WELReplicate):
            continue

        doc_refs: list[str] = []
        for doc in raw.docs:
            doc_key = doc.url or uuid.uuid4().hex
            if doc_key not in doc_index:
                doc_index[doc_key] = _doc_to_dict(doc)
            doc_refs.append(doc_key)
        rep_payload.append(
            {
                "replicate_idx": raw.replicate_idx,
                "p_web": raw.p_web,
                "support_bullets": list(raw.support_bullets),
                "oppose_bullets": list(raw.oppose_bullets),
                "notes": list(raw.notes),
                "json_valid": raw.json_valid,
                "docs": doc_refs,
            }
        )

    docs_payload = [
        {"doc_id": doc_id, **payload} for doc_id, payload in doc_index.items()
    ]
    return rep_payload, docs_payload


def write_web_artifact(
    *,
    run_id: str,
    claim: Optional[str],
    mode: str,
    store: ArtifactStore,
    prior_block: Dict[str, Any],
    web_block: Dict[str, Any],
    combined_block: Dict[str, Any],
    wel_provenance: Optional[Dict[str, Any]],
    replicates: Iterable[Any],
    debug_votes: Optional[Iterable[Dict[str, Any]]],
) -> Optional[ArtifactRecord]:
    if isinstance(store, _DisabledStore):
        return None

    timestamp = datetime.now(timezone.utc).isoformat()
    artifact_id = f"{run_id}-{uuid.uuid4().hex[:8]}"
    base_path = f"artifacts/{run_id}/{artifact_id}"

    reps_payload, docs_payload = _serialize_replicates(replicates)

    replicates_uri = None
    docs_uri = None

    if reps_payload:
        reps_bytes = gzip.compress(json.dumps(reps_payload, default=str).encode("utf-8"), compresslevel=6)
        replicates_uri = store.write_bytes(
            f"{base_path}/replicates.json.gz", reps_bytes, content_type="application/json+gzip"
        )

    if docs_payload:
        docs_bytes = gzip.compress(json.dumps(docs_payload, default=str).encode("utf-8"), compresslevel=6)
        docs_uri = store.write_bytes(
            f"{base_path}/docs.json.gz", docs_bytes, content_type="application/json+gzip"
        )

    manifest = {
        "artifact_id": artifact_id,
        "run_id": run_id,
        "mode": mode,
        "claim": claim,
        "created_at": timestamp,
        "prior": prior_block,
        "web": {k: v for k, v in web_block.items() if k != "replicates"},
        "combined": combined_block,
        "wel_provenance": wel_provenance,
        "replicates_uri": replicates_uri,
        "docs_uri": docs_uri,
        "debug_votes": list(debug_votes) if debug_votes else None,
        "store_root": store.root,
    }
    manifest_text = json.dumps(manifest, indent=2, default=str)
    manifest_uri = store.write_text(f"{base_path}/manifest.json", manifest_text, content_type="application/json")

    return ArtifactRecord(
        artifact_id=artifact_id,
        manifest_uri=manifest_uri,
        verdicts_uri=replicates_uri,
        docs_uri=docs_uri,
        local=isinstance(store, _LocalStore),
    )
