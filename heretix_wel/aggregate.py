from __future__ import annotations

from typing import Iterable, Tuple

import numpy as np

from .weights import logit, sigmoid


def combine_replicates_ps(replicate_ps: Iterable[float]) -> Tuple[float, Tuple[float, float], float]:
    """
    Combine replicate probabilities into a single estimate, CI95, and dispersion.
    """
    arr_p = np.asarray(list(replicate_ps), dtype=float)
    if arr_p.size == 0:
        raise ValueError("No replicate probabilities provided")

    arr_l = np.vectorize(logit)(arr_p)
    center_l = float(np.mean(arr_l))
    p_hat = sigmoid(center_l)

    if arr_l.size >= 2:
        std = float(np.std(arr_l, ddof=1))
        sigma = std / np.sqrt(arr_l.size)
        lo_l = center_l - 1.96 * sigma
        hi_l = center_l + 1.96 * sigma
        q25, q75 = np.percentile(arr_l, [25, 75])
        dispersion = float(q75 - q25)
    else:
        lo_l = center_l - 1.0
        hi_l = center_l + 1.0
        dispersion = 0.0

    return p_hat, (sigmoid(lo_l), sigmoid(hi_l)), dispersion
