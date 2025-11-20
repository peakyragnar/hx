from __future__ import annotations

import hashlib
import threading
import time
from typing import Optional, Dict, Any
from pathlib import Path

from .storage import (
    get_cached_sample as _get_cached_sample,
    DEFAULT_DB_PATH,
    get_cached_run as _get_cached_run,
    set_cached_run as _set_cached_run,
)


class TTLCache:
    """Simple in-process TTL cache with coarse eviction."""

    def __init__(self, max_items: int = 2048, ttl_seconds: int = 900):
        self.max = max(1, max_items)
        self.ttl = max(1, ttl_seconds)
        self._store: Dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def configure(self, *, max_items: Optional[int] = None, ttl_seconds: Optional[int] = None):
        with self._lock:
            if max_items is not None and max_items > 0:
                self.max = max_items
                # Trim if needed
                while len(self._store) > self.max:
                    self._store.pop(next(iter(self._store)))
            if ttl_seconds is not None and ttl_seconds > 0:
                self.ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            rec = self._store.get(key)
            if not rec:
                return None
            val, expires = rec
            if now > expires:
                self._store.pop(key, None)
                return None
            # Return a shallow copy to protect cache state
            if isinstance(val, dict):
                return dict(val)
            if isinstance(val, list):
                return list(val)
            return val

    def set(self, key: str, value: Any):
        with self._lock:
            if len(self._store) >= self.max:
                # Coarse eviction: drop oldest inserted entry
                self._store.pop(next(iter(self._store)))
            expires = time.time() + self.ttl
            self._store[key] = (value, expires)


def make_cache_key(
    *,
    claim: str,
    model: str,
    prompt_version: str,
    prompt_sha256: str,
    replicate_idx: int,
    max_output_tokens: int,
    provider_mode: str,  # "MOCK" or "LIVE" (or provider label)
) -> str:
    s = f"{claim}|{model}|{prompt_version}|{prompt_sha256}|{replicate_idx}|{max_output_tokens}|{provider_mode}"
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def make_run_cache_key(
    *,
    claim: str,
    model: str,
    provider: str,
    prompt_version: str,
    K: int,
    R: int,
    T: int,
    max_output_tokens: int,
    provider_mode: str,
    target_B: int,
    seed_marker: str,
) -> str:
    s = (
        f"{claim}|{model}|{provider}|{prompt_version}|K={K}|R={R}|T={T}|"
        f"max_out={max_output_tokens}|{provider_mode}|B={target_B}|seed={seed_marker}"
    )
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def get_cached_sample(cache_key: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    return _get_cached_sample(cache_key, db_path)


_SAMPLE_CACHE = TTLCache()
_RUN_CACHE = TTLCache()


def configure_runtime_caches(*, sample_ttl: int, sample_max: int, run_ttl: int, run_max: int):
    _SAMPLE_CACHE.configure(max_items=sample_max, ttl_seconds=sample_ttl)
    _RUN_CACHE.configure(max_items=run_max, ttl_seconds=run_ttl)


def sample_cache_get(cache_key: str, db_path: Path = DEFAULT_DB_PATH, ttl_seconds: int = 900) -> Optional[Dict[str, Any]]:
    hit = _SAMPLE_CACHE.get(cache_key)
    if hit is not None:
        return hit
    row = _get_cached_sample(cache_key, db_path)
    if row:
        _SAMPLE_CACHE.set(cache_key, dict(row))
    return row


def sample_cache_set(cache_key: str, payload: Dict[str, Any]):
    _SAMPLE_CACHE.set(cache_key, dict(payload))


def run_cache_get(key: str, db_path: Path = DEFAULT_DB_PATH, ttl_seconds: int = 259200) -> Optional[Dict[str, Any]]:
    hit = _RUN_CACHE.get(key)
    if hit is not None:
        return hit
    row = _get_cached_run(key, db_path=db_path, ttl_seconds=ttl_seconds)
    if row:
        _RUN_CACHE.set(key, dict(row))
    return row


def run_cache_set(key: str, payload: Dict[str, Any], db_path: Path = DEFAULT_DB_PATH, ttl_seconds: int = 259200):
    _RUN_CACHE.set(key, dict(payload))
    _set_cached_run(key, payload, ttl_seconds, db_path=db_path)
