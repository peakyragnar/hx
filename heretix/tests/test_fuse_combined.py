import pytest
from heretix_api.fuse import fuse_prior_web

def test_fuse_prior_web_includes_weights_and_label():
    prior = {"p": 0.45, "ci95": (0.3, 0.6)}
    web = {
        "p": 0.7,
        "ci95": (0.6, 0.8),
        "evidence": {"n_docs": 4, "n_domains": 3, "median_age_days": 5, "dispersion": 0.1, "json_valid_rate": 1.0},
        "resolved": False,
    }

    combined, weights = fuse_prior_web("Claim text", prior, web)

    assert weights["w_web"] > 0
    assert combined["weight_web"] == pytest.approx(weights["w_web"])
    assert combined["weight_prior"] == pytest.approx(1 - weights["w_web"])
    assert combined["prob_true"] == combined["p"]
    assert combined["label"] in {"Likely true", "Uncertain", "Likely false"}


def test_fuse_prior_web_resolved_short_circuits_weights():
    prior = {"p": 0.3, "ci95": (0.2, 0.4)}
    web = {
        "p": 0.95,
        "ci95": (0.9, 0.99),
        "evidence": {},
        "resolved": True,
        "resolved_truth": True,
    }

    combined, weights = fuse_prior_web("Another claim", prior, web)

    assert combined["weight_web"] == 1.0
    assert combined["weight_prior"] == 0.0
    assert combined["label"] == "Likely true"
    assert weights["w_web"] == 1.0
