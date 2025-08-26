from __future__ import annotations

import hashlib
from typing import Optional, Dict, Any
from pathlib import Path

from .storage import get_cached_sample as _get_cached_sample, DEFAULT_DB_PATH


def make_cache_key(
    *,
    claim: str,
    model: str,
    prompt_version: str,
    prompt_sha256: str,
    replicate_idx: int,
    max_output_tokens: int,
) -> str:
    s = f"{claim}|{model}|{prompt_version}|{prompt_sha256}|{replicate_idx}|{max_output_tokens}"
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def get_cached_sample(cache_key: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    return _get_cached_sample(cache_key, db_path)

