# heretix_rpl/seed.py
from __future__ import annotations
import hashlib
from typing import Iterable

def make_bootstrap_seed(
    claim: str,
    model: str,
    prompt_version: str,
    k: int,
    r: int,
    template_hashes: Iterable[str],
    center: str = "trimmed",
    trim: float = 0.2,
    B: int = 5000,
) -> int:
    """
    Deterministic 64-bit seed from run config. Sort template hashes so order doesn't matter.
    """
    canon = "|".join([
        "RPL-G5",
        f"model={model}",
        f"prompt={prompt_version}",
        f"claim={claim}",
        f"K={k}",
        f"R={r}",
        f"center={center}",
        f"trim={trim}",
        f"B={B}",
        "templates=" + ",".join(sorted(set(template_hashes))),
    ])
    h = hashlib.sha256(canon.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")  # 0..2**64-1 for numpy.default_rng