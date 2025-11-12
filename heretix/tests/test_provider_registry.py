from __future__ import annotations

from heretix.provider import registry, grok_xai


def test_registry_returns_mock_for_use_mock():
    scorer = registry.get_scorer("gpt-5", use_mock=True)
    from heretix.provider.mock import score_claim_mock

    assert scorer is score_claim_mock


def test_registry_aliases_grok_models(monkeypatch):
    # Ensure alias lookup pulls Grok adapter
    default_model = grok_xai._DEFAULT_GROK_MODEL  # type: ignore[attr-defined]

    scorer = registry.get_scorer(default_model, use_mock=False)
    assert scorer is grok_xai.score_claim

    scorer2 = registry.get_scorer("grok-5", use_mock=False)
    assert scorer2 is grok_xai.score_claim


def test_registry_defaults_to_openai():
    from heretix.provider import openai_gpt5

    scorer = registry.get_scorer("unknown", use_mock=False)
    assert scorer is openai_gpt5.score_claim
