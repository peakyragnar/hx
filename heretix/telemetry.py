from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Dict, Any

log = logging.getLogger("heretix.telemetry")


@contextmanager
def timed(stage: str, ctx: Dict[str, Any] | None = None):
    """Context manager that logs elapsed ms for the given stage."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        payload = {"stage": stage, "ms": elapsed_ms}
        if ctx:
            payload.update(ctx)
        log.info("timing", extra=payload)


def est_tokens(char_count: int) -> int:
    """Rough token estimate using 4 chars/token heuristic."""
    if char_count <= 0:
        return 0
    return max(1, round(char_count / 4))


def est_cost(tokens_in: int, tokens_out: int, price_in_per_1k: float, price_out_per_1k: float) -> float:
    """Return approximate USD cost for a call given prompt/completion token counts."""
    cost_in = (tokens_in / 1000.0) * price_in_per_1k
    cost_out = (tokens_out / 1000.0) * price_out_per_1k
    return cost_in + cost_out

