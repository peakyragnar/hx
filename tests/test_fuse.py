import pytest

from heretix_api.fuse import fuse_prior_web
from heretix_wel.weights import fuse_probabilities


def test_fuse_probabilities_symmetry_at_half_weight():
    p, ci = fuse_probabilities(0.5, (0.45, 0.55), 0.5, (0.45, 0.55), 0.5)
    assert 0.49 < p < 0.51
    assert len(ci) == 2


def test_fuse_probabilities_limits():
    p_high, _ = fuse_probabilities(0.1, (0.09, 0.11), 0.9, (0.85, 0.95), 1.0)
    p_low, _ = fuse_probabilities(0.1, (0.09, 0.11), 0.9, (0.85, 0.95), 0.0)
    assert p_high > p_low


def test_fuse_prior_web_combines_weights():
    prior = {"p": 0.2, "ci95": [0.18, 0.22]}
    web = {
        "p": 0.8,
        "ci95": [0.75, 0.85],
        "evidence": {
            "n_docs": 10,
            "n_domains": 4,
            "median_age_days": 2.0,
            "dispersion": 0.05,
            "json_valid_rate": 1.0,
        },
    }
    combined, weights = fuse_prior_web("Earnings release tomorrow", prior, web)
    assert combined["p"] > prior["p"]
    assert 0.2 <= weights["w_web"] <= 0.90
    assert combined["prob_true"] == combined["p"]
    assert combined["weight_web"] == weights["w_web"]
    assert combined["weight_prior"] == pytest.approx(1.0 - weights["w_web"])
    assert combined["label"] in {"Likely true", "Likely false", "Uncertain"}
