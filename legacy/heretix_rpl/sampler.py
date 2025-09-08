"""
Balanced sampler with deterministic rotation for paraphrase template selection.

Given a template bank of size T and a desired number of paraphrase slots K,
produce an order of template indices (0..T-1) whose counts differ by at most 1.

Rotation offset is derived deterministically from (claim|model|prompt_version)
to avoid always favoring low indices when K % T != 0.
"""
from __future__ import annotations

from typing import List, Tuple
import hashlib


def rotation_offset(claim: str, model: str, prompt_version: str, T: int) -> int:
    """Deterministic rotation offset in [0, T-1] from inputs.

    Uses sha256 of the concatenated string to derive an integer.
    """
    if T <= 0:
        return 0
    h = hashlib.sha256(f"{claim}|{model}|{prompt_version}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) % T


def balanced_indices_with_rotation(T: int, K: int, offset: int) -> List[int]:
    """Return a length-K list of template indices (0..T-1) with near-equal counts.

    Example: T=5, K=7, offset=0 -> [0,1,2,3,4,0,1]
    Rotation applies first, then counts are distributed as evenly as possible.
    """
    if T <= 0 or K <= 0:
        return []
    # Build base order [0,1,...,T-1] and rotate by offset
    base = list(range(T))
    if T > 1 and offset % T != 0:
        rot = offset % T
        order = base[rot:] + base[:rot]
    else:
        order = base

    # Even distribution of K over T: each of first (K % T) gets one extra
    per = K // T
    rem = K % T
    seq: List[int] = []
    for i, idx in enumerate(order):
        reps = per + (1 if i < rem else 0)
        if reps:
            seq.extend([idx] * reps)
    return seq


def planned_counts(order: List[int], T: int) -> Tuple[List[int], float]:
    """Compute counts per template and imbalance ratio (max/min) for the planned order."""
    counts = [0] * max(T, 0)
    for idx in order:
        if 0 <= idx < T:
            counts[idx] += 1
    nonzero = [c for c in counts if c > 0]
    if not nonzero:
        return counts, 1.0
    cmax, cmin = max(nonzero), min(nonzero)
    ratio = (cmax / cmin) if cmin > 0 else float("inf")
    return counts, ratio

