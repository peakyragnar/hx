from __future__ import annotations

from heretix.provider import factory


def _invoke_adapter(adapter):
    return adapter.score_claim(
        claim="Test claim",
        system_text="System instructions",
        user_template="Claim: {CLAIM}",
        paraphrase_text="Assess {CLAIM}",
        model="gpt-5",
        max_output_tokens=128,
    )


def test_live_adapter_uses_registry(monkeypatch):
    captured = {}

    def fake_scorer(**kwargs):
        captured["kwargs"] = kwargs
        return {"raw": {"belief": {"prob_true": 0.5}}, "meta": {}, "timing": {}, "telemetry": None}

    monkeypatch.setattr(factory, "_get_score_fn", lambda model: fake_scorer)

    adapter = factory.get_rpl_adapter(provider_mode="live", model="gpt5-default")
    _invoke_adapter(adapter)

    assert captured["kwargs"]["claim"] == "Test claim"
    assert captured["kwargs"]["model"] == "gpt-5"


def test_mock_adapter_calls_mock_provider(monkeypatch):
    called = {}

    def fake_mock(**kwargs):
        called["kwargs"] = kwargs
        return {"raw": {"belief": {"prob_true": 0.1}}, "meta": {}, "timing": {}, "telemetry": None}

    monkeypatch.setattr(factory._mock, "score_claim_mock", fake_mock)  # type: ignore[attr-defined]

    adapter = factory.get_rpl_adapter(provider_mode="mock", model="irrelevant")
    _invoke_adapter(adapter)

    assert called["kwargs"]["claim"] == "Test claim"
    assert called["kwargs"]["model"] == "gpt-5"
