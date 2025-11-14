from __future__ import annotations

import json

import pytest

from heretix.provider import deepseek_r1
from heretix.provider.json_utils import extract_and_validate
from heretix.schemas import RPLSampleV1
from heretix.tests._samples import make_rpl_sample


class _Limiter:
    def __init__(self):
        self.count = 0

    def acquire(self):
        self.count += 1


class _FakeResponse:
    def __init__(self):
        self._payload = {
            "id": "deepseek-xyz",
            "model": "deepseek-r1",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(make_rpl_sample(0.44, label="unlikely")),
                    }
                }
            ],
        }

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_deepseek_invokes_rate_limiter(monkeypatch: pytest.MonkeyPatch):
    limiter = _Limiter()
    monkeypatch.setattr(deepseek_r1, "_DEEPSEEK_RATE_LIMITER", limiter)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")

    called = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        called["url"] = url
        called["json"] = json
        called["headers"] = headers
        return _FakeResponse()

    monkeypatch.setattr(deepseek_r1.requests, "post", fake_post)

    result = deepseek_r1.score_claim(
        claim="Solar panels",
        system_text="system",
        user_template="Explain {CLAIM}",
        paraphrase_text="{CLAIM}?",
    )

    assert limiter.count == 1
    assert called["headers"]["Authorization"] == "Bearer ds-key"
    parsed, warnings = extract_and_validate(json.dumps(result["raw"]), RPLSampleV1)
    assert parsed.belief.prob_true == pytest.approx(0.44)
    assert warnings == []
