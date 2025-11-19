from __future__ import annotations

import pytest

from heretix import reasoning_llm
from heretix.prompts.prompt_builder import PromptParts


class FakeTelemetry:
    def model_dump(self):
        return {"provider": "test"}


def test_generate_reasoning_paragraph(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_prompt(provider: str, *, claim: str, verdict: str, probability_text: str, context: str):
        captured["provider"] = provider
        captured["claim"] = claim
        captured["verdict"] = verdict
        captured["probability_text"] = probability_text
        captured["context"] = context
        return PromptParts(system="SYS", user="USER")

    def fake_adapter(**kwargs):
        captured["adapter_kwargs"] = kwargs
        return {"text": "Reasoning paragraph.", "telemetry": FakeTelemetry(), "warnings": []}

    monkeypatch.setattr(reasoning_llm, "build_reasoning_prompt", fake_prompt)
    monkeypatch.setattr(reasoning_llm, "get_expl_adapter", lambda model: fake_adapter)

    result = reasoning_llm.generate_reasoning_paragraph(
        claim="Sample claim",
        verdict="Likely true",
        probability_text="60%",
        context="Evidence snippets:\n- example",
        model="gpt-5",
        provider="openai",
    )

    assert result["reasoning"] == "Reasoning paragraph."
    assert captured["provider"] == "openai"
    assert captured["adapter_kwargs"]["instructions"] == "SYS"
    assert captured["adapter_kwargs"]["user_text"] == "USER"
