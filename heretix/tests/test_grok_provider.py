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
            resp.output_text = json.dumps(
                {
                    "prob_true": 0.42,
                    "confidence_self": 0.6,
                    "assumptions": ["baseline assumption"],
                    "reasoning_bullets": [
                        "The model recalls official tariff debates from 2018 that highlighted only small price movements.",
                        "Training data includes multiple economic summaries noting substitution effects that absorb tariff shocks.",
                        "Historical IMF briefings in the corpus emphasize that tariffs are often too small to raise CPI directly.",
                    ],
                    "contrary_considerations": ["Large, coordinated tariffs can still move prices in narrow sectors."],
                    "ambiguity_flags": [],
                }
            )
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
                msg = SimpleNamespace(
                    content=json.dumps(
                        {
                            "prob_true": 0.65,
                            "confidence_self": 0.55,
                            "assumptions": [],
                            "reasoning_bullets": [
                                "Internal economic surveys cite declining module prices across many countries in the training data.",
                                "Examples stored in the corpus show rooftop adopters offset costs through incentives after five years.",
                                "Historical payback analyses are summarized with explicit timelines in the model's prior knowledge.",
                            ],
                            "contrary_considerations": ["High interest rates can stretch the payback horizon in a few regions."],
                            "ambiguity_flags": [],
                        }
                    )
                )
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


class _ContextRetryClient:
    def __init__(self):
        parent = self
        self.calls = 0

        class _Responses:
            def create(self, **kwargs):
                parent.calls += 1
                if parent.calls == 1:
                    bullets = ["Too vague."]
                else:
                    bullets = [
                        "Training data cites multiple court filings detailing how the policy is applied in practice.",
                        "Model memory includes dated examples showing what counts as compliance under the statute.",
                        "Canonical summaries in the corpus explain how regulators measure violations year by year.",
                    ]
                resp = SimpleNamespace()
                resp.output_text = json.dumps(
                    {
                        "prob_true": 0.51,
                        "confidence_self": 0.5,
                        "assumptions": [],
                        "reasoning_bullets": bullets,
                        "contrary_considerations": ["Some interpretations differ for edge cases."],
                        "ambiguity_flags": [],
                    }
                )
                resp.model = kwargs.get("model", DEFAULT_MODEL)
                resp.id = f"resp-{parent.calls}"
                resp.output = []
                resp.created = 0
                return resp

        self.responses = _Responses()
        self.chat = SimpleNamespace(completions=None)


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


def test_grok_retries_until_context_present(monkeypatch: pytest.MonkeyPatch):
    limiter = _set_client(monkeypatch, _ContextRetryClient())

    res = _call_score("The statute always applies retroactively")

    # One extra acquire per attempt
    assert limiter.count == 2
    assert res["raw"]["prob_true"] == 0.51
    assert len(res["raw"]["reasoning_bullets"]) >= 3
