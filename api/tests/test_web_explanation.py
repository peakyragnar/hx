from api.main import build_web_explanation


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
