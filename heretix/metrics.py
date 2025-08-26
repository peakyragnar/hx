from __future__ import annotations

import numpy as np
from typing import Union, List, Tuple


def stability_from_iqr(iqr_logit: float, s: float = 0.2, alpha: float = 1.7) -> float:
    iqr = max(0.0, float(iqr_logit))
    s_safe = max(s, 1e-12)
    alpha_safe = max(alpha, 1e-6)
    return 1.0 / (1.0 + (iqr / s_safe) ** alpha_safe)


def stability_band_from_iqr(iqr_logit: float, high_max: float = 0.05, medium_max: float = 0.30) -> str:
    iqr = max(0.0, float(iqr_logit))
    if iqr <= high_max:
        return "high"
    elif iqr <= medium_max:
        return "medium"
    else:
        return "low"


def compute_stability_calibrated(logits: Union[List[float], np.ndarray]) -> Tuple[float, float]:
    logits_arr = np.asarray(logits, dtype=float)
    if logits_arr.size == 0:
        return 0.0, 0.0
    iqr_logit = float(np.percentile(logits_arr, 75) - np.percentile(logits_arr, 25))
    stability_score = stability_from_iqr(iqr_logit)
    return stability_score, iqr_logit

