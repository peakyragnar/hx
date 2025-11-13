from __future__ import annotations

import pytest

from heretix.provider import openai_gpt5, registry


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

    with pytest.raises(ValueError):
        registry.get_score_fn("totally-unknown-model")
