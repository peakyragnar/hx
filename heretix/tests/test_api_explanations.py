from __future__ import annotations

from heretix.explanations import extract_reasons


def test_extract_reasons_prefers_new_reasons_field():
    payload = {
        "raw": {
            "reasons": ["first", "second"],
            "contrary_considerations": ["fallback"],
        }
    }
    reasons = extract_reasons(payload)
    assert reasons[0].startswith("first")
    assert len(reasons) >= 2


def test_extract_reasons_handles_legacy_reasoning_bullets():
    payload = {
        "raw": {
            "reasoning_bullets": ["legacy"],
            "assumptions": ["assumption"],
        }
    }
    reasons = extract_reasons(payload)
    assert reasons and reasons[0].startswith("legacy")
