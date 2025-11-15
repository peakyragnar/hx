from __future__ import annotations

import json

import pytest
import requests

from heretix.provider import gemini_google
from heretix.tests._samples import make_rpl_sample


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
                            {"text": json.dumps(make_rpl_sample(0.61, label="likely"))},
                        ]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 200,
                "candidatesTokenCount": 80,
                "totalTokenCount": 280,
            },
        }

    def raise_for_status(self):  # pragma: no cover - nothing to raise
        return None

    def json(self):
        return self._payload


class _ErrorResponse:
    def __init__(self, *, status: int = 403, message: str = "permission denied"):
        self.status_code = status
        self._body = json.dumps({"error": {"message": message, "status": "PERMISSION_DENIED"}})

    def raise_for_status(self):
        raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return json.loads(self._body)

    @property
    def text(self):
        return self._body


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
    assert result["sample"]["belief"]["prob_true"] == pytest.approx(0.61)
    assert result["warnings"] == []
    telemetry = result["telemetry"]
    assert telemetry.provider == "google"
    assert telemetry.logical_model == "gemini25-default"
    assert telemetry.api_model == "gemini-2.5-real"
    assert telemetry.tokens_in == 200
    assert telemetry.tokens_out == 80


def test_gemini_http_error_is_surface(monkeypatch: pytest.MonkeyPatch):
    limiter = _Limiter()
    monkeypatch.setattr(gemini_google, "_GEMINI_RATE_LIMITER", limiter)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    monkeypatch.setattr(
        gemini_google,
        "load_provider_capabilities",
        lambda: {"google": type("Cfg", (), {"api_model_map": {"gemini25-default": "gemini-2.5-real"}})()},
    )
    resp = _ErrorResponse(status=403, message="Permission denied for this model")
    monkeypatch.setattr(gemini_google.requests, "post", lambda *a, **k: resp)

    with pytest.raises(RuntimeError) as excinfo:
        gemini_google.score_claim(
            claim="Does it fail?",
            system_text="sys",
            user_template="Answer {CLAIM}",
            paraphrase_text="{CLAIM}",
        )

    message = str(excinfo.value)
    assert "HTTP 403" in message
    assert "Permission denied for this model" in message


def test_effective_output_tokens_raises_floor_for_reasoning_models():
    assert gemini_google._effective_output_tokens("gemini-2.5-pro", 1200) == 4000
    assert gemini_google._effective_output_tokens("gemini-2.5-pro", 9000) == 8192
    assert gemini_google._effective_output_tokens("gemini-1.5", 500) == 500
