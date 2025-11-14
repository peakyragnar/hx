from __future__ import annotations

import json

import pytest

from heretix.provider import wel_deepseek, wel_gemini, wel_grok


def test_wel_grok_adapter_reads_bundle(monkeypatch):
    class FakeResp:
        output_text = json.dumps(
            {
                "stance_prob_true": 0.42,
                "stance_label": "supports",
                "support_bullets": ["a"],
                "oppose_bullets": [],
                "notes": [],
            }
        )
        model = "grok-4"
        id = "resp_123"
        created = 123456.0

    class FakeResponses:
        def create(self, **kwargs):
            assert kwargs["instructions"] == "instr"
            assert kwargs["input"][0]["content"][0]["text"] == "bundle text"
            return FakeResp()

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponses()

    monkeypatch.setenv("XAI_API_KEY", "test")
    monkeypatch.setattr(wel_grok._grok, "_build_client", lambda: FakeClient())
    monkeypatch.setattr(wel_grok._XAI_WEL_RATE_LIMITER, "acquire", lambda *a, **k: None)

    result = wel_grok.score_wel_bundle(instructions="instr", bundle_text="bundle text", model="grok-4", max_output_tokens=256)

    assert json.loads(result["text"])["stance_label"] == "supports"
    assert result["meta"]["provider_model_id"] == "grok-4"
    assert result["timing"]["latency_ms"] >= 0
    assert result["telemetry"].provider == "xai"


def test_wel_gemini_adapter_reads_text(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "model": "models/gemini-2.5",
                "responseId": "abc",
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "stance_prob_true": 0.5,
                                            "stance_label": "supports",
                                            "support_bullets": ["gemini"],
                                            "oppose_bullets": [],
                                            "notes": [],
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
            }

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(wel_gemini.requests, "post", lambda *a, **k: FakeResponse())
    monkeypatch.setattr(wel_gemini._GEMINI_WEL_RATE_LIMITER, "acquire", lambda *a, **k: None)

    result = wel_gemini.score_wel_bundle(instructions="instr", bundle_text="bundle text", model="gemini-2.5", max_output_tokens=256)

    assert json.loads(result["text"])["support_bullets"] == ["gemini"]
    assert result["meta"]["provider_model_id"].startswith("models")
    assert result["telemetry"].provider == "google"


def test_wel_deepseek_adapter_reads_text(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "model": "deepseek-r1",
                "id": "deep123",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "stance_prob_true": 0.33,
                                    "stance_label": "mixed",
                                    "support_bullets": [],
                                    "oppose_bullets": [],
                                    "notes": [],
                                }
                            )
                        }
                    }
                ],
            }

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setattr(wel_deepseek.requests, "post", lambda *a, **k: FakeResponse())
    monkeypatch.setattr(wel_deepseek._DEEPSEEK_WEL_RATE_LIMITER, "acquire", lambda *a, **k: None)

    result = wel_deepseek.score_wel_bundle(instructions="instr", bundle_text="bundle text", model="deepseek-r1", max_output_tokens=256)

    assert json.loads(result["text"])["stance_label"] == "mixed"
    assert result["meta"]["provider_model_id"] == "deepseek-r1"
    assert result["telemetry"].provider == "deepseek"
