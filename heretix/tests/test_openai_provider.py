from __future__ import annotations

import json

import pytest

from heretix.provider import openai_gpt5
from heretix.provider.json_utils import extract_and_validate
from heretix.schemas import RPLSampleV1
from heretix.tests._samples import make_rpl_sample


class FakeResponse:
    def __init__(self):
        self.output_text = json.dumps(make_rpl_sample(0.5))
        self.model = "gpt-5"
        self.id = "resp-1"
        self.created = 0


class FakeClient:
    class responses:
        @staticmethod
        def create(**kwargs):
            return FakeResponse()


class Limiter:
    def __init__(self, counter):
        self._counter = counter

    def acquire(self):
        self._counter["count"] += 1


def test_openai_rate_limiter_invoked(monkeypatch: pytest.MonkeyPatch):
    called = {"count": 0}

    monkeypatch.setattr(openai_gpt5, "_OPENAI_RATE_LIMITER", Limiter(called))
    monkeypatch.setattr(openai_gpt5, "OpenAI", lambda: FakeClient())

    result = openai_gpt5.score_claim(
        claim="test",
        system_text="system",
        user_template="template",
        paraphrase_text="{CLAIM}",
    )
    assert called["count"] == 1
    parsed, warnings = extract_and_validate(json.dumps(result["raw"]), RPLSampleV1)
    assert parsed.belief.prob_true == pytest.approx(0.5)
    assert warnings == []
