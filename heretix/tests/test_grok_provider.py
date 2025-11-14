from __future__ import annotations

import json

import pytest

from heretix.provider import grok_xai


class _Limiter:
    def __init__(self, counter):
        self._counter = counter

    def acquire(self):
        self._counter["count"] += 1


class _FakeResponse:
    def __init__(self, *, model: str = "grok-4") -> None:
        self.output_text = json.dumps({"prob_true": 0.42})
        self.model = model
        self.id = "resp-xyz"
        self.created = 0


class _FakeResponses:
    def __init__(self, parent):
        self._parent = parent

    def create(self, **kwargs):
        self._parent.requests.append(kwargs)
        return _FakeResponse()


class _FakeClient:
    def __init__(self):
        self.requests = []
        self.responses = _FakeResponses(self)
        self.chat_requests = []
        self.chat = _FakeChat(self)


class _FakeChat:
    def __init__(self, parent):
        self.completions = _FakeChatCompletions(parent)


class _FakeChatCompletions:
    def __init__(self, parent):
        self._parent = parent

    def create(self, **kwargs):
        self._parent.chat_requests.append(kwargs)

        class Choice:
            def __init__(self):
                self.message = type("Msg", (), {"content": json.dumps({"prob_true": 0.51})})

        class Resp:
            def __init__(self):
                self.choices = [Choice()]
                self.model = "mystery-model"
                self.id = "chat-abc"
                self.created = 0

        return Resp()


class _FailingResponses:
    def __init__(self, parent):
        self._parent = parent

    def create(self, **kwargs):  # pragma: no cover - exercised via fallback
        raise RuntimeError("boom")


class _FallbackClient(_FakeClient):
    def __init__(self):
        super().__init__()
        self.responses = _FailingResponses(self)


def test_grok_adapter_invokes_rate_limiter(monkeypatch: pytest.MonkeyPatch):
    counter = {"count": 0}
    monkeypatch.setattr(grok_xai, "_XAI_RATE_LIMITER", _Limiter(counter))
    client = _FakeClient()
    monkeypatch.setattr(grok_xai, "_build_client", lambda: client)

    result = grok_xai.score_claim(
        claim="Tariffs raise prices",
        system_text="system",
        user_template="Answer for {CLAIM}",
        paraphrase_text="Consider: {CLAIM}",
    )

    assert counter["count"] == 1
    assert client.requests and client.requests[0]["model"] == "grok-4"
    assert result["raw"].get("prob_true") == 0.42


def test_grok_adapter_fallbacks_to_chat_completion(monkeypatch: pytest.MonkeyPatch):
    counter = {"count": 0}
    monkeypatch.setattr(grok_xai, "_XAI_RATE_LIMITER", _Limiter(counter))
    client = _FallbackClient()
    monkeypatch.setattr(grok_xai, "_build_client", lambda: client)

    result = grok_xai.score_claim(
        claim="Solar",
        system_text="system",
        user_template="Explain {CLAIM}",
        paraphrase_text="{CLAIM}?",
        model="grok-4",
    )

    assert counter["count"] == 1
    assert client.chat_requests, "chat completions should be used as fallback"
    assert result["raw"].get("prob_true") == 0.51
    assert "model_warning" in result["meta"]
