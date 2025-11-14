import numpy as np
import pytest

from heretix.aggregate import aggregate_clustered
from heretix.metrics import compute_stability_calibrated
from heretix.seed import make_bootstrap_seed


def test_aggregate_clustered_trimmed_center_downweights_outliers():
    by_template = {
        "tpl_a": [-1.0],
        "tpl_b": [0.0],
        "tpl_c": [0.1],
        "tpl_d": [0.2],
        "tpl_outlier": [10.0],
    }

    ell_hat, _, meta = aggregate_clustered(
        by_template,
        B=32,
        rng=np.random.default_rng(42),
        center="trimmed",
        trim=0.2,
    )

    assert ell_hat == pytest.approx(0.1, abs=1e-9)
    assert meta["n_templates"] == 5
    assert meta["method"].endswith("trimmed")


def test_aggregate_clustered_bootstrap_seed_reuses_rng_sequence():
    by_template = {
        "tpl_a": [-0.5, -0.45, -0.55],
        "tpl_b": [0.2, 0.25, 0.15],
        "tpl_c": [0.8, 0.75, 0.85],
    }

    bootstrap_seed = make_bootstrap_seed(
        claim="Synthetic claim",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        k=3,
        r=2,
        template_hashes=by_template.keys(),
    )

    ell1, ci1, _ = aggregate_clustered(
        by_template,
        B=128,
        rng=np.random.default_rng(bootstrap_seed),
    )
    ell2, ci2, _ = aggregate_clustered(
        by_template,
        B=128,
        rng=np.random.default_rng(bootstrap_seed),
    )
    _, ci3, _ = aggregate_clustered(
        by_template,
        B=128,
        rng=np.random.default_rng(bootstrap_seed + 1),
    )

    assert ell1 == pytest.approx(ell2)
    assert ci1 == pytest.approx(ci2)
    assert not pytest.approx(ci1[0], rel=1e-6, abs=1e-6) == ci3[0]
    assert not pytest.approx(ci1[1], rel=1e-6, abs=1e-6) == ci3[1]


def test_compute_stability_calibrated_tracks_dispersion_changes():
    tight_logits = [-0.1, -0.05, 0.0, 0.05, 0.1]
    noisy_logits = [-1.2, -0.2, 0.0, 0.4, 1.3]

    tight_score, tight_iqr = compute_stability_calibrated(tight_logits)
    noisy_score, noisy_iqr = compute_stability_calibrated(noisy_logits)

    assert tight_iqr < noisy_iqr
    assert tight_score > noisy_score
    assert 0.0 < noisy_score < 1.0
    assert 0.0 <= tight_iqr < 1.0
    assert tight_score <= 1.0
