from __future__ import annotations

import json

import pytest

from heretix.provider import openai_gpt5
from heretix.tests._samples import make_rpl_sample


class FakeUsage:
    input_tokens = 120
    output_tokens = 60


class FakeResponse:
    def __init__(self, model_name: str = "gpt-5"):
        self.output_text = json.dumps(make_rpl_sample(0.5))
        self.model = model_name
        self.id = "resp-1"
        self.created = 0
        self.usage = FakeUsage()


class FakeResponses:
    def __init__(self, parent):
        self._parent = parent

    def create(self, **kwargs):
        self._parent.calls.append(kwargs)
        return FakeResponse(kwargs.get("model", "gpt-5"))


class FakeClient:
    def __init__(self):
        self.calls = []
        self.responses = FakeResponses(self)


class Limiter:
    def __init__(self, counter):
        self._counter = counter

    def acquire(self):
        self._counter["count"] += 1


def test_openai_rate_limiter_invoked(monkeypatch: pytest.MonkeyPatch):
    called = {"count": 0}

    monkeypatch.setattr(openai_gpt5, "_OPENAI_RATE_LIMITER", Limiter(called))
    monkeypatch.setattr(openai_gpt5, "_OPENAI_CLIENT", None)
    monkeypatch.setattr(openai_gpt5, "load_provider_capabilities", lambda: {})
    client = FakeClient()
    monkeypatch.setattr(openai_gpt5, "OpenAI", lambda: client)

    result = openai_gpt5.score_claim(
        claim="test",
        system_text="system",
        user_template="template",
        paraphrase_text="{CLAIM}",
    )
    assert called["count"] == 1
    assert client.calls and client.calls[0]["model"] == "gpt-5"
    assert result["sample"]["belief"]["prob_true"] == pytest.approx(0.5)
    assert result["warnings"] == []
    telemetry = result["telemetry"]
    assert telemetry.provider == "openai"
    assert telemetry.logical_model == "gpt-5"
    assert telemetry.api_model == "gpt-5"
    assert telemetry.tokens_in == FakeUsage.input_tokens
    assert telemetry.tokens_out == FakeUsage.output_tokens


def test_openai_resolves_logical_model(monkeypatch: pytest.MonkeyPatch):
    called = {"count": 0}
    monkeypatch.setattr(openai_gpt5, "_OPENAI_RATE_LIMITER", Limiter(called))
    monkeypatch.setattr(openai_gpt5, "_OPENAI_CLIENT", None)

    caps_obj = type("Caps", (), {"api_model_map": {"gpt5-default": "gpt-5.2025-01-15"}})()
    monkeypatch.setattr(openai_gpt5, "load_provider_capabilities", lambda: {"openai": caps_obj})
    client = FakeClient()
    monkeypatch.setattr(openai_gpt5, "OpenAI", lambda: client)

    result = openai_gpt5.score_claim(
        claim="test",
        system_text="system",
        user_template="template",
        paraphrase_text="{CLAIM}",
        model="gpt5-default",
    )

    assert called["count"] == 1
    assert client.calls and client.calls[0]["model"] == "gpt-5.2025-01-15"
    telemetry = result["telemetry"]
    assert telemetry.logical_model == "gpt5-default"
    assert telemetry.api_model == "gpt-5.2025-01-15"
