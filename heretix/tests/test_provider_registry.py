from __future__ import annotations

import pytest

from heretix.provider import deepseek_r1, gemini_google, grok_xai, openai_gpt5, registry


def test_registry_maps_gpt5_to_openai_adapter():
    fn = registry.get_score_fn("gpt-5")
    assert fn is openai_gpt5.score_claim

    fn2 = registry.get_live_scorer("gpt-5")
    assert fn2 is openai_gpt5.score_claim


def test_registry_supports_aliases_and_case_insensitivity():
    assert registry.get_score_fn("OPENAI:GPT-5") is openai_gpt5.score_claim
    assert registry.get_score_fn("openai") is openai_gpt5.score_claim


def test_registry_lists_models_and_errors_on_unknown():
    models = registry.list_registered_models()
    assert "gpt-5" in models
    assert "grok-4" in models
    assert "gemini-2.5" in models
    assert "deepseek-r1" in models

    with pytest.raises(ValueError):
        registry.get_score_fn("totally-unknown-model")


def test_registry_maps_grok_aliases():
    assert registry.get_score_fn("grok-4") is grok_xai.score_claim
    assert registry.get_score_fn("XAI:GROK-4") is grok_xai.score_claim
    assert registry.get_score_fn("grok-5") is grok_xai.score_claim


def test_registry_maps_gemini_and_deepseek():
    assert registry.get_score_fn("gemini-2.5") is gemini_google.score_claim
    assert registry.get_score_fn("google") is gemini_google.score_claim
    assert registry.get_score_fn("deepseek-r1") is deepseek_r1.score_claim
    assert registry.get_score_fn("deepseek:r1") is deepseek_r1.score_claim
