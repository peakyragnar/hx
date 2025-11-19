import pytest

from api.main import build_web_explanation, _build_web_block_v1, _build_combined_block_v1


def test_build_web_explanation_basic():
    prior = {"p": 0.1}
    combined = {"p": 0.25}
    web = {
        "p": 0.4,
        "ci95": [0.3, 0.5],
        "evidence": {"n_docs": 5, "n_domains": 3, "median_age_days": 12},
    }
    weights = {"w_web": 0.65}
    replicates = [
        {
            "support_bullets": ["Recent coverage highlights strong late-season performance"],
            "oppose_bullets": [],
            "notes": [],
        }
    ]

    headline, summary, reasons = build_web_explanation(
        prior_block=prior,
        combined_block=combined,
        web_block=web,
        weights=weights,
        wel_replicates=replicates,
    )

    assert headline.startswith("Why the web-informed verdict")
    assert "10.0%" in summary
    assert any("Web evidence across" in r for r in reasons)
    assert any("Recent coverage" in r for r in reasons)


def test_build_web_block_preserves_resolution():
    payload = {
        "p": 0.55,
        "ci95": [0.45, 0.65],
        "resolved": True,
        "resolved_truth": False,
        "resolved_reason": "Resolver disagreed with the claim.",
        "resolved_citations": [
            {
                "url": " https://example.com/post ",
                "domain": "Example.com",
                "quote": "A direct quote",
                "stance": "support",
                "field": "inflation",
                "value": 0.8,
                "weight": 1.2,
                "published_at": "2024-01-01T00:00:00Z",
            }
        ],
        "support": 4,
        "contradict": 1,
        "domains": 3,
        "evidence": {"n_docs": 6, "n_domains": 3, "median_age_days": 9.5},
    }
    block = _build_web_block_v1(payload, {"strength": 0.7})
    assert block is not None
    assert block.resolved is True
    assert block.resolved_truth is False
    assert block.resolved_reason == "Resolver disagreed with the claim."
    assert block.resolved_citations and block.resolved_citations[0]["url"] == "https://example.com/post"
    assert block.resolved_citations[0]["domain"] == "Example.com"
    assert block.support == 4
    assert block.evidence and block.evidence.n_docs == 6


def test_build_combined_block_preserves_resolution_metadata():
    payload = {
        "p": 0.82,
        "ci_lo": 0.75,
        "ci_hi": 0.9,
        "label": "Likely true",
        "weight_prior": 0.2,
        "weight_web": 0.8,
        "resolved": True,
        "resolved_truth": True,
        "resolved_reason": " Consensus verdict ",
        "resolved_citations": [
            {
                "url": " https://example.com/fact ",
                "domain": " Example.com ",
                "quote": "Quoted text",
            }
        ],
        "support": 3.5,
        "contradict": 0.15,
        "domains": 4,
    }
    block = _build_combined_block_v1(payload)
    assert block is not None
    assert block.resolved is True
    assert block.resolved_truth is True
    assert block.resolved_reason == "Consensus verdict"
    assert block.resolved_citations and block.resolved_citations[0]["url"] == "https://example.com/fact"
    assert block.support == 3.5
    assert block.contradict == 0.15
    assert block.domains == 4
    assert block.ci95 == [pytest.approx(0.75), pytest.approx(0.9)]
