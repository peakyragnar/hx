from __future__ import annotations

import json

import pytest

from heretix.provider import registry
from heretix.provider.telemetry import LLMTelemetry
from heretix_wel import scoring
from heretix_wel.scoring import WELSchemaError


def test_call_wel_once_uses_registered_adapter(monkeypatch):
    payload = {
        "stance_prob_true": 0.72,
        "stance_label": "supports",
        "support_bullets": ["snippet supports claim"],
        "oppose_bullets": [],
        "notes": [],
    }

    def fake_adapter(**kwargs):
        assert "instructions" in kwargs
        assert kwargs["bundle_text"] == "bundle-text"
        assert kwargs["model"] == "gpt-standin"
        telemetry = LLMTelemetry(provider="openai", logical_model="gpt-standin", api_model="gpt-standin")
        return {"text": json.dumps(payload), "warnings": ["adapter_warning"], "telemetry": telemetry}

    monkeypatch.setattr(scoring, "get_wel_score_fn", lambda model: fake_adapter)

    canonical, warnings, prompt_hash, telemetry = scoring.call_wel_once("bundle-text", model="gpt-standin")

    assert canonical["stance_label"] == "supports"
    assert pytest.approx(canonical["stance_prob_true"], rel=1e-6) == 0.72
    assert warnings == ["adapter_warning"]
    assert len(prompt_hash) == 64
    assert telemetry.provider == "openai"


def test_call_wel_once_raises_when_schema_invalid(monkeypatch):
    def bad_adapter(**kwargs):
        telemetry = LLMTelemetry(provider="openai", logical_model="gpt-standin", api_model=None)
        return {"text": "{}", "warnings": [], "telemetry": telemetry}

    monkeypatch.setattr(scoring, "get_wel_score_fn", lambda model: bad_adapter)

    with pytest.raises(WELSchemaError):
        scoring.call_wel_once("bundle-text")


def test_call_wel_once_uses_provider_specific_prompt(monkeypatch):
    payload = {
        "stance_prob_true": 0.5,
        "stance_label": "mixed",
        "support_bullets": [],
        "oppose_bullets": [],
        "notes": [],
    }
    captured = {}

    def fake_adapter(**kwargs):
        captured["instructions"] = kwargs["instructions"]
        telemetry = LLMTelemetry(provider="xai", logical_model="grok-4", api_model=None)
        return {"text": json.dumps(payload), "warnings": [], "telemetry": telemetry}

    monkeypatch.setattr(scoring, "get_wel_score_fn", lambda model: fake_adapter)

    def fake_builder(provider: str | None) -> str:
        captured["provider"] = provider
        return "provider instructions"

    monkeypatch.setattr(scoring, "build_wel_instructions", fake_builder)

    _, _, _, telemetry = scoring.call_wel_once("bundle", model="grok-4")

    assert captured["provider"] == "xai"
    assert captured["instructions"].startswith("provider instructions")
    assert scoring.WEL_SCHEMA.splitlines()[0] in captured["instructions"]
    assert telemetry.provider == "xai"
