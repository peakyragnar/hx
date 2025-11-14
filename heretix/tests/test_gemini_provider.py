from __future__ import annotations

import json

import pytest

from heretix.provider import gemini_google


class _Limiter:
    def __init__(self):
        self.count = 0

    def acquire(self):
        self.count += 1


class _FakeResponse:
    def __init__(self):
        self._payload = {
            "model": "gemini-2.5-real",
            "responseId": "resp-123",
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": json.dumps({"prob_true": 0.61})},
                        ]
                    }
                }
            ],
        }

    def raise_for_status(self):  # pragma: no cover - nothing to raise
        return None

    def json(self):
        return self._payload


def test_gemini_rate_limiter_and_payload(monkeypatch: pytest.MonkeyPatch):
    limiter = _Limiter()
    monkeypatch.setattr(gemini_google, "_GEMINI_RATE_LIMITER", limiter)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    monkeypatch.setattr(
        gemini_google,
        "load_provider_capabilities",
        lambda: {"google": type("Cfg", (), {"api_model_map": {"gemini25-default": "gemini-2.5-real"}})()},
    )

    called = {}

    def fake_post(url, params=None, json=None, timeout=None):
        called["url"] = url
        called["params"] = params
        called["json"] = json
        return _FakeResponse()

    monkeypatch.setattr(gemini_google.requests, "post", fake_post)

    result = gemini_google.score_claim(
        claim="Do tariffs cause inflation?",
        system_text="system",
        user_template="Answer {CLAIM}",
        paraphrase_text="{CLAIM}?",
    )

    assert limiter.count == 1
    assert "gemini-2.5-real" in called["url"]
    assert called["params"]["key"] == "secret-key"
    assert result["raw"].get("prob_true") == 0.61

