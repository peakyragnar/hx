from __future__ import annotations

import pytest

from heretix_api.fuse import fuse_prior_web
from heretix_wel.timeliness import heuristic_is_timely
from heretix_wel.weights import fuse_probabilities, recency_score, strength_score, web_weight


def test_fuse_prior_web_blends_prior_and_web():
    prior = {"p": 0.4, "ci95": [0.3, 0.5]}
    web = {
        "p": 0.65,
        "ci95": [0.5, 0.8],
        "resolved": False,
        "evidence": {
            "median_age_days": 12.0,
            "n_docs": 6,
            "n_domains": 3,
            "dispersion": 0.08,
            "json_valid_rate": 1.0,
        },
    }
    claim_text = "GDP grew 5% in 2024"
    combined, weights = fuse_prior_web(claim_text, prior, web)

    recency = recency_score(heuristic_is_timely(claim_text), 12.0)
    strength = strength_score(6, 3, 0.08, 1.0)
    expected_weight = web_weight(recency, strength)
    expected_p, expected_ci = fuse_probabilities(prior["p"], tuple(prior["ci95"]), web["p"], tuple(web["ci95"]), expected_weight)

    assert pytest.approx(weights["w_web"], rel=1e-6) == expected_weight
    assert pytest.approx(combined["p"], rel=1e-6) == expected_p
    assert pytest.approx(combined["ci95"][0], rel=1e-6) == expected_ci[0]
    assert pytest.approx(combined["ci95"][1], rel=1e-6) == expected_ci[1]
    assert combined["weight_web"] == pytest.approx(expected_weight, rel=1e-6)
    assert combined["weight_prior"] == pytest.approx(1.0 - expected_weight, rel=1e-6)


def test_fuse_prior_web_handles_resolved_web_block():
    prior = {"p": 0.6, "ci95": [0.5, 0.7]}
    web = {
        "p": 0.05,
        "ci95": [0.05, 0.05],
        "resolved": True,
        "resolved_truth": False,
        "resolved_reason": "Official certification contradicts the claim.",
        "resolved_citations": ["https://example.com/doc"],
        "support": ["Support bullet"],
        "contradict": ["Contradiction bullet"],
        "domains": 2,
    }
    combined, weights = fuse_prior_web("Claim resolved", prior, web)

    assert combined["resolved"] is True
    assert combined["p"] == pytest.approx(web["p"])
    assert combined["ci95"][0] == pytest.approx(web["ci95"][0])
    assert combined["ci95"][1] == pytest.approx(web["ci95"][1])
    assert weights["w_web"] == 1.0
    assert combined["weight_web"] == 1.0
    assert combined["weight_prior"] == 0.0
