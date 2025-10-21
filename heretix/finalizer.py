from __future__ import annotations

import atexit
import threading
from typing import Dict, Callable, Any

import numpy as np

from .aggregate import aggregate_clustered


_PENDING: list[threading.Thread] = []
_PENDING_LOCK = threading.Lock()


def _sigmoid(x: float) -> float:
    x = float(np.clip(x, -709, 709))
    return float(1 / (1 + np.exp(-x)))


def _register_thread(th: threading.Thread) -> None:
    with _PENDING_LOCK:
        _PENDING.append(th)


def _thread_finished(th: threading.Thread) -> None:
    with _PENDING_LOCK:
        try:
            _PENDING.remove(th)
        except ValueError:
            pass


def _join_pending_threads() -> None:
    while True:
        with _PENDING_LOCK:
            threads = list(_PENDING)
        if not threads:
            break
        for thread in threads:
            thread.join()


atexit.register(_join_pending_threads)


def kick_off_final_ci(
    *,
    by_template_logits: Dict[str, list[float]],
    seed: int,
    final_B: int,
    update_fn: Callable[[Dict[str, Any]], None],
    run_cache_writer: Callable[[Dict[str, Any]], None],
):
    """Spawn background worker to recompute the CI with final_B bootstrap resamples."""

    def _job():
        try:
            rng = np.random.default_rng(seed)
            ell_hat, (lo_l, hi_l), diag_final = aggregate_clustered(
                by_template_logits=by_template_logits,
                B=final_B,
                rng=rng,
                center="trimmed",
                trim=0.2,
                fixed_m=None,
            )
            p_hat = _sigmoid(ell_hat)
            lo_p, hi_p = _sigmoid(lo_l), _sigmoid(hi_l)
            width = float(hi_p - lo_p)
            update_payload = {
                "prob_true_rpl": p_hat,
                "ci95": [lo_p, hi_p],
                "ci_width": width,
                "aggregation": {
                    "B": final_B,
                    "counts_by_template": diag_final.get("counts_by_template", {}),
                    "imbalance_ratio": diag_final.get("imbalance_ratio"),
                    "template_iqr_logit": diag_final.get("template_iqr_logit"),
                },
            }
            update_fn(update_payload)
            run_cache_writer(update_payload)
        finally:
            _thread_finished(threading.current_thread())

    th = threading.Thread(target=_job, daemon=False)
    _register_thread(th)
    th.start()
    return th
