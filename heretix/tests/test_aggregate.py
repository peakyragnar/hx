from __future__ import annotations

import numpy as np
import pytest

from heretix.aggregate import aggregate_clustered


def test_aggregate_trimmed_downweights_outliers():
    logits = {
        "tpl_a": [0.0, 0.0],
        "tpl_b": [0.1, 0.1],
        "tpl_c": [0.2, 0.2],
        "tpl_d": [0.3, 0.3],
        "tpl_outlier": [5.0, 5.0],
    }

    rng_trim = np.random.default_rng(123)
    ell_trimmed, ci_trimmed, meta_trimmed = aggregate_clustered(
        logits,
        B=1024,
        rng=rng_trim,
        center="trimmed",
        trim=0.2,
    )

    assert meta_trimmed["method"].startswith("equal_by_template_cluster_bootstrap_trimmed")
    assert ell_trimmed == pytest.approx(0.2)
    assert ci_trimmed[0] <= ell_trimmed <= ci_trimmed[1]

    rng_mean = np.random.default_rng(123)
    ell_mean, _, meta_mean = aggregate_clustered(
        logits,
        B=1024,
        rng=rng_mean,
        center="mean",
    )

    assert meta_mean["method"] == "equal_by_template_cluster_bootstrap"
    assert ell_mean == pytest.approx(1.12, abs=1e-3)
    assert ell_mean > ell_trimmed
