from __future__ import annotations

import json

from typing import Any, Dict

import pytest

from heretix import explanations_llm
from heretix.prompts.prompt_builder import PromptParts


class FakeTelemetry:
    def __init__(self) -> None:
        self.provider = "openai"

    def model_dump(self) -> Dict[str, Any]:
        return {"provider": self.provider, "tokens_in": 123, "tokens_out": 456, "latency_ms": 789}


def test_generate_simple_expl_llm_uses_adapter(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_prompt(provider: str, *, claim: str, context: str, style: str = "narrator"):
        captured["provider"] = provider
        captured["claim"] = claim
        captured["context"] = context
        return PromptParts(system="SYS", user="USER")

    def fake_adapter(**kwargs):
        captured["adapter_kwargs"] = kwargs
        payload = {
            "title": "Why the verdict looks this way",
            "body_paragraphs": ["Body text"],
            "bullets": ["Point"],
        }
        return {
            "text": json.dumps(payload),
            "warnings": ["narrator_warning"],
            "telemetry": FakeTelemetry(),
        }

    monkeypatch.setattr(explanations_llm, "build_simple_expl_prompt", fake_prompt)
    monkeypatch.setattr(explanations_llm, "get_expl_adapter", lambda model: fake_adapter)

    prior = {"p": 0.4, "ci95": [0.3, 0.5], "stability": 0.8}
    combined = {"p": 0.45, "ci95": [0.35, 0.55], "weight_web": 0.4}
    web_block = {"p": 0.6, "ci95": [0.4, 0.7], "warning_counts": {"json_repaired": 2}}
    result = explanations_llm.generate_simple_expl_llm(
        claim="Example claim",
        mode="web_informed",
        prior_block=prior,
        combined_block=combined,
        web_block=web_block,
        warning_counts={"json_repaired": 2},
        sampling={"K": 8, "R": 2},
        weights={"w_web": 0.4},
        model="grok-4",
        provider="grok",
        style="narrator",
    )

    assert result["simple_expl"]["title"].startswith("Why")
    assert result["telemetry"]["provider"] == "openai"
    assert captured["provider"] == "grok"
    assert captured["adapter_kwargs"]["instructions"] == "SYS"
    assert captured["adapter_kwargs"]["user_text"] == "USER"
    assert "Mode: web_informed" in captured["context"]
    assert "Verdict:" in captured["context"]


def test_generate_simple_expl_llm_raises_on_invalid_payload(monkeypatch: pytest.MonkeyPatch):
    def fake_adapter(**kwargs):
        return {"text": "not json", "warnings": []}

    monkeypatch.setattr(explanations_llm, "get_expl_adapter", lambda model: fake_adapter)

    prior = {"p": 0.5, "ci95": [0.4, 0.6]}
    combined = {"p": 0.5, "ci95": [0.4, 0.6]}

    with pytest.raises(ValueError):
        explanations_llm.generate_simple_expl_llm(
            claim="Example claim",
            mode="baseline",
            prior_block=prior,
            combined_block=combined,
            web_block=None,
            warning_counts=None,
            sampling=None,
            weights=None,
        )
