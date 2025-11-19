from types import SimpleNamespace

import pytest

import heretix.rpl as rpl


def test_resolve_provider_and_model_matches_inferred():
    provider, model = rpl._resolve_provider_and_model("openai", "gpt5-default")
    assert provider == "openai"
    assert model == "gpt5-default"


def test_resolve_provider_and_model_uses_capabilities(monkeypatch):
    caps = {"xai": SimpleNamespace(default_model="grok4-default")}
    monkeypatch.setattr(rpl, "load_provider_capabilities", lambda: caps)

    provider, model = rpl._resolve_provider_and_model("xai", "gpt5-default")

    assert provider == "xai"
    assert model == "grok4-default"


def test_resolve_provider_and_model_unknown_provider(monkeypatch):
    monkeypatch.setattr(rpl, "load_provider_capabilities", lambda: {})

    with pytest.raises(ValueError):
        rpl._resolve_provider_and_model("unknown-provider", "gpt5-default")
