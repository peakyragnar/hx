from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from heretix.provider import grok_xai

DEFAULT_MODEL = grok_xai._DEFAULT_GROK_MODEL  # type: ignore[attr-defined]


class _Limiter:
    def __init__(self):
        self.count = 0

    def acquire(self):
        self.count += 1


class _FakeResponsesClient:
    class responses:
        @staticmethod
        def create(**kwargs):
            resp = SimpleNamespace()
            resp.output_text = json.dumps({
                "prob_true": 0.42,
                "confidence_self": 0.6,
                "assumptions": [],
                "reasoning_bullets": [],
                "contrary_considerations": [],
                "ambiguity_flags": [],
            })
            resp.model = kwargs.get("model", DEFAULT_MODEL)
            resp.id = "resp-xyz"
            resp.response_id = "resp-xyz"
            resp.created = 0
            resp.output = []
            return resp


class _FakeChatClient:
    class responses:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("responses api unavailable")

    class chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                msg = SimpleNamespace(content=json.dumps({"prob_true": 0.65}))
                choice = SimpleNamespace(message=msg)
                resp = SimpleNamespace(
                    choices=[choice],
                    model=kwargs.get("model", DEFAULT_MODEL),
                    id="chat-abc",
                    created=0,
                )
                return resp


class _InvalidJSONClient:
    class responses:
        @staticmethod
        def create(**kwargs):
            resp = SimpleNamespace()
            resp.output_text = "{not-json"
            resp.model = kwargs.get("model", DEFAULT_MODEL)
            resp.id = "resp-bad"
            resp.output = []
            resp.created = 0
            return resp


def _set_client(monkeypatch: pytest.MonkeyPatch, client) -> _Limiter:
    limiter = _Limiter()
    monkeypatch.setattr(grok_xai, "_XAI_RATE_LIMITER", limiter)
    monkeypatch.setattr(grok_xai, "OpenAI", lambda api_key=None, base_url=None: client)
    return limiter


def _call_score(claim: str = "Tariffs always raise prices") -> dict[str, object]:
    return grok_xai.score_claim(
        claim=claim,
        system_text="system",
        user_template="template {CLAIM}",
        paraphrase_text="{CLAIM}",
        model=DEFAULT_MODEL,
        max_output_tokens=256,
    )


def test_grok_rate_limiter_and_json_parse(monkeypatch: pytest.MonkeyPatch):
    limiter = _set_client(monkeypatch, _FakeResponsesClient())

    res = _call_score()

    assert limiter.count == 1
    assert res["raw"]["prob_true"] == 0.42
    assert res["meta"]["provider_model_id"] == DEFAULT_MODEL
    assert res["meta"]["prompt_sha256"]


def test_grok_fallback_to_chat_completions(monkeypatch: pytest.MonkeyPatch):
    _set_client(monkeypatch, _FakeChatClient())

    res = _call_score("Solar panels pay back in 5 years")

    assert res["raw"]["prob_true"] == 0.65
    assert res["meta"]["provider_model_id"] == DEFAULT_MODEL
    assert res["meta"]["response_id"] == "chat-abc"


def test_grok_invalid_json_returns_empty_dict(monkeypatch: pytest.MonkeyPatch):
    _set_client(monkeypatch, _InvalidJSONClient())

    res = _call_score("Interest rates stay low")

    assert res["raw"] == {}
    # Still reports metadata so upstream can log provenance
    assert res["meta"]["provider_model_id"] == DEFAULT_MODEL
