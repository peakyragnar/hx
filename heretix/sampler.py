from __future__ import annotations

from typing import List, Tuple
import hashlib


def rotation_offset(claim: str, model: str, prompt_version: str, T: int) -> int:
    if T <= 0:
        return 0
    h = hashlib.sha256(f"{claim}|{model}|{prompt_version}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) % T


def balanced_indices_with_rotation(T: int, K: int, offset: int) -> List[int]:
    if T <= 0 or K <= 0:
        return []
    base = list(range(T))
    order = base
    if T > 1 and offset % T != 0:
        rot = offset % T
        order = base[rot:] + base[:rot]
    per = K // T
    rem = K % T
    seq: List[int] = []
    for i, idx in enumerate(order):
        reps = per + (1 if i < rem else 0)
        if reps:
            seq.extend([idx] * reps)
    return seq


def planned_counts(order: List[int], T: int) -> Tuple[List[int], float]:
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

