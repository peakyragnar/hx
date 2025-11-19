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


def test_gemini_expl_flattens_body_paragraph_blocks(monkeypatch: pytest.MonkeyPatch):
    """Gemini sometimes nests a SimpleExpl shape inside body_paragraphs; ensure it flattens."""

    monkeypatch.setattr(expl_gemini, "_GEMINI_RATE_LIMITER", _FakeRateLimiter())
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    nested_payload = {
        "title": "Outer",
        "body_paragraphs": [
            {
                "title": "Inner title",
                "summary": "Inner summary sentence.",
                "body_paragraphs": [
                    "Nested paragraph one.",
                    "Nested paragraph two.",
                ],
            },
            "Standalone paragraph.",
        ],
        "bullets": [],
    }

    def fake_post(url, params=None, json=None, timeout=None):
        import json as json_module
        return _FakeResponse(json_module.dumps(nested_payload))

    monkeypatch.setattr("requests.post", fake_post)

    result = expl_gemini.write_simple_expl_gemini(
        instructions="Test instructions",
        user_text="Test user text",
        model="gemini25-default",
        max_output_tokens=640,
    )

    parsed = json.loads(result["text"])
    paragraphs = parsed.get("body_paragraphs")
    assert isinstance(paragraphs, list)
    # Should include the nested lines as separate paragraphs
    assert "Nested paragraph one." in paragraphs
    assert "Nested paragraph two." in paragraphs
    assert "Standalone paragraph." in paragraphs
    # None of the entries should be dicts or JSON blobs
    for para in paragraphs:
        assert isinstance(para, str)
        assert not para.strip().startswith("{")


def test_gemini_expl_extracts_from_json_string_in_body_paragraphs(monkeypatch: pytest.MonkeyPatch):
    """Test that Gemini adapter detects and parses JSON strings inside body_paragraphs."""

    monkeypatch.setattr(expl_gemini, "_GEMINI_RATE_LIMITER", _FakeRateLimiter())
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    # Simulate Gemini returning a JSON string inside body_paragraphs
    # This is the actual production issue
    nested_json_string = json.dumps({
        "body_paragraphs": ["The verdict leans towards likely true because Wayne Gretzky's historical performance in hockey is widely recognized."],
        "title": "Analysis of the verdict"
    })

    problematic_response = {
        "title": "Why this assessment leans toward Wayne Gretzky being the greatest hockey player",
        "body_paragraphs": [
            nested_json_string  # JSON as a string!
        ],
        "bullets": [
            "The verdict reflects Gretzky's statistical dominance.",
            "The assessment relies on prior knowledge.",
        ],
    }

    def fake_post(url, params=None, json=None, timeout=None):
        import json as json_module
        return _FakeResponse(json_module.dumps(problematic_response))

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

    # Should extract the actual text from the nested JSON string
    assert "body_paragraphs" in parsed
    assert isinstance(parsed["body_paragraphs"], list)
    assert len(parsed["body_paragraphs"]) >= 1

    # The first paragraph should be the extracted text, not the JSON string
    first_para = parsed["body_paragraphs"][0]
    assert isinstance(first_para, str)
    assert "Wayne Gretzky's historical performance" in first_para
    # Should NOT contain the nested JSON structure
    assert not first_para.startswith("{")
    assert "body_paragraphs" not in first_para
    assert "Analysis of the verdict" not in first_para


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
