from __future__ import annotations

import json

import pytest
import responses

from heretix.provider import deepseek_r1
from heretix.tests._samples import make_rpl_sample


class _Limiter:
    def __init__(self):
        self.count = 0

    def acquire(self):
        self.count += 1


def _add_deepseek_response(payload: dict) -> None:
    responses.add(
        responses.POST,
        deepseek_r1._API_URL,
        json=payload,
        status=200,
    )


@responses.activate
def test_deepseek_invokes_rate_limiter_and_posts(monkeypatch: pytest.MonkeyPatch):
    limiter = _Limiter()
    monkeypatch.setattr(deepseek_r1, "_DEEPSEEK_RATE_LIMITER", limiter)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")

    sample = make_rpl_sample(0.44, label="unlikely")
    payload = {
        "id": "deepseek-xyz",
        "model": "deepseek-r1",
        "choices": [{"message": {"content": json.dumps(sample)}}],
        "usage": {"prompt_tokens": 180, "completion_tokens": 70},
    }
    _add_deepseek_response(payload)

    result = deepseek_r1.score_claim(
        claim="Solar panels",
        system_text="system",
        user_template="Explain {CLAIM}",
        paraphrase_text="{CLAIM}?",
    )

    assert limiter.count == 1
    assert len(responses.calls) == 1
    call = responses.calls[0]
    assert call.request.url == deepseek_r1._API_URL
    assert call.request.headers["Authorization"] == "Bearer ds-key"
    body = call.request.body
    serialized = body if isinstance(body, str) else body.decode("utf-8")
    req_payload = json.loads(serialized)
    assert req_payload["model"] == "deepseek-r1"
    assert req_payload["messages"][0]["role"] == "system"

    assert result["sample"]["belief"]["prob_true"] == pytest.approx(0.44)
    assert result["warnings"] == []
    telemetry = result["telemetry"]
    assert telemetry.provider == "deepseek"
    assert telemetry.logical_model == "deepseek-r1"
    assert telemetry.api_model == "deepseek-r1"
    assert telemetry.tokens_in == 180
    assert telemetry.tokens_out == 70


@responses.activate
def test_deepseek_parses_markdown_wrapped_payload(monkeypatch: pytest.MonkeyPatch):
    limiter = _Limiter()
    monkeypatch.setattr(deepseek_r1, "_DEEPSEEK_RATE_LIMITER", limiter)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")

    sample = make_rpl_sample(0.63, label="likely")
    wrapped = f"Here you go ```json\n{json.dumps(sample)}\n``` thanks"
    payload = {
        "id": "deepseek-abc",
        "model": "deepseek-r1",
        "choices": [{"message": {"content": wrapped}}],
        "usage": {"prompt_tokens": 210, "completion_tokens": 90},
    }
    _add_deepseek_response(payload)

    result = deepseek_r1.score_claim(
        claim="New policy",
        system_text="system",
        user_template="Explain {CLAIM}",
        paraphrase_text="{CLAIM}?",
    )

    assert limiter.count == 1
    assert len(responses.calls) == 1
    assert result["sample"]["belief"]["prob_true"] == pytest.approx(0.63)
    assert "json_repaired_simple" in result["warnings"]
    telemetry = result["telemetry"]
    assert telemetry.provider == "deepseek"
    assert telemetry.logical_model == "deepseek-r1"
    assert telemetry.tokens_in == 210
    assert telemetry.tokens_out == 90
