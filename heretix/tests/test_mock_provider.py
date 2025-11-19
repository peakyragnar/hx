from __future__ import annotations

from heretix.provider import mock


def test_mock_provider_emits_rpl_sample_schema():
    result = mock.score_claim_mock(
        claim="Sample claim",
        system_text="system",
        user_template="Answer {CLAIM}",
        paraphrase_text="Consider {CLAIM}",
    )

    raw = result.get("raw")
    assert isinstance(raw, dict)
    assert result["warnings"] == []
    sample = result["sample"]
    assert isinstance(sample, dict)
    assert 0.0 <= sample["belief"]["prob_true"] <= 1.0
    assert sample["belief"]["label"] in {
        "very_unlikely",
        "unlikely",
        "uncertain",
        "likely",
        "very_likely",
    }
    telemetry = result["telemetry"]
    assert telemetry.provider == "mock"
    assert telemetry.logical_model == "gpt-5"
    assert telemetry.api_model.endswith("-MOCK")
    assert telemetry.tokens_in > 0
    assert telemetry.tokens_out > 0
