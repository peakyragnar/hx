"""Test Gemini explanation adapter normalization logic."""

from __future__ import annotations

import json
import pytest

from heretix.provider import expl_gemini


class _FakeRateLimiter:
    def acquire(self):
        pass


class _FakeResponse:
    def __init__(self, text_payload: str):
        self.status_code = 200
        self._text_payload = text_payload
        self._json_payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": text_payload}
                        ]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 150,
                "candidatesTokenCount": 200,
            },
        }

    def raise_for_status(self):
        pass

    def json(self):
        return self._json_payload


def test_gemini_expl_normalizes_nested_dict_in_body_paragraphs(monkeypatch: pytest.MonkeyPatch):
    """Test that Gemini adapter properly extracts text from nested dicts in body_paragraphs."""

    monkeypatch.setattr(expl_gemini, "_GEMINI_RATE_LIMITER", _FakeRateLimiter())
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    # Simulate Gemini returning JSON with a nested dict in body_paragraphs
    problematic_json = {
        "title": "Why this assessment leans toward likely false",
        "body_paragraphs": [
            {"text": "Caleb Williams is a promising player, but not the best QB."},
            "ESPN's 2025 Total QBR ranks Williams 18th.",
        ],
        "bullets": [
            "Established QBs have proven track records.",
            "Web articles nudged the estimate slightly upward.",
        ],
    }

    def fake_post(url, params=None, json=None, timeout=None):
        import json as json_module
        return _FakeResponse(json_module.dumps(problematic_json))

    fake_session = type("Session", (), {"post": staticmethod(fake_post)})()
    monkeypatch.setattr("requests.post", fake_post)

    result = expl_gemini.write_simple_expl_gemini(
        instructions="Test instructions",
        user_text="Test user text",
        model="gemini25-default",
        max_output_tokens=640,
    )

    # The returned text should be normalized JSON
    assert "text" in result
    text = result["text"]

    # Parse the returned text to verify normalization
    parsed = json.loads(text)
    assert isinstance(parsed, dict)
    assert "body_paragraphs" in parsed
    assert isinstance(parsed["body_paragraphs"], list)

    # All body_paragraphs should be strings, not dicts
    for para in parsed["body_paragraphs"]:
        assert isinstance(para, str), f"Expected string but got {type(para)}: {para}"
        # Should contain the actual text, not a dict representation
        assert "Caleb Williams" in para or "ESPN" in para
        # Should NOT be a JSON string or dict repr
        assert not para.strip().startswith("{")
        assert not para.strip().startswith("{'")


def test_gemini_expl_handles_reason_field_fallback(monkeypatch: pytest.MonkeyPatch):
    """Test that Gemini adapter maps 'reason' field to body_paragraphs when schema is violated."""

    monkeypatch.setattr(expl_gemini, "_GEMINI_RATE_LIMITER", _FakeRateLimiter())
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    # Simulate Gemini returning wrong schema (reason instead of body_paragraphs)
    wrong_schema_json = {
        "title": "Analysis",
        "reason": "This is the main explanation text.",
        "bullets": ["Point 1", "Point 2"],
    }

    def fake_post(url, params=None, json=None, timeout=None):
        import json as json_module
        return _FakeResponse(json_module.dumps(wrong_schema_json))

    monkeypatch.setattr("requests.post", fake_post)

    result = expl_gemini.write_simple_expl_gemini(
        instructions="Test instructions",
        user_text="Test user text",
        model="gemini25-default",
        max_output_tokens=640,
    )

    # Parse the returned text
    text = result["text"]
    parsed = json.loads(text)

    # 'reason' should have been mapped to 'body_paragraphs'
    assert "body_paragraphs" in parsed
    assert isinstance(parsed["body_paragraphs"], list)
    assert len(parsed["body_paragraphs"]) == 1
    assert "main explanation text" in parsed["body_paragraphs"][0]
    # 'reason' should be removed
    assert "reason" not in parsed
