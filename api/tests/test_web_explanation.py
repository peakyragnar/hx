from api.main import build_web_explanation, _build_web_block_v1


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
    assert "0.1" in summary
    assert any("Web evidence across" in r for r in reasons)
    assert any("Recent coverage" in r for r in reasons)


def test_build_web_block_preserves_resolution():
    payload = {
        "p": 0.55,
        "ci95": [0.45, 0.65],
        "resolved": True,
        "resolved_truth": False,
        "resolved_reason": "Resolver disagreed with the claim.",
        "resolved_citations": [" https://example.com/post "],
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
    assert block.resolved_citations == ["https://example.com/post"]
    assert block.support == 4
    assert block.evidence and block.evidence.n_docs == 6
