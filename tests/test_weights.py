from heretix_wel.weights import (
    fuse_probabilities,
    recency_score,
    strength_score,
    web_weight,
)


def test_recency_score_blends_claim_and_docs():
    timely_high = recency_score(True, 1.0)
    timely_low = recency_score(True, 30.0)
    untimely = recency_score(False, 30.0)
    assert timely_high > timely_low > untimely


def test_strength_score_improves_with_coverage_diversity_agreement():
    strong = strength_score(n_docs=20, n_domains=6, dispersion=0.05, json_valid_rate=1.0)
    weak = strength_score(n_docs=2, n_domains=1, dispersion=0.4, json_valid_rate=0.5)
    assert strong > weak


def test_web_weight_bounds():
    assert 0.20 <= web_weight(-1.0, -1.0) <= 0.90
    assert web_weight(1.0, 1.0) > web_weight(0.0, 0.0)


def test_fuse_probabilities_moves_toward_web():
    fused_p, _ = fuse_probabilities(
        prior_p=0.2,
        prior_ci=(0.18, 0.22),
        web_p=0.8,
        web_ci=(0.75, 0.85),
        w=0.6,
    )
    assert 0.2 < fused_p < 0.8
