from __future__ import annotations

import json

import pytest

from heretix.provider import registry
from heretix_wel import scoring
from heretix_wel.scoring import WELSchemaError


def test_call_wel_once_uses_registered_adapter(monkeypatch):
    payload = {
        "stance_prob_true": 0.72,
        "stance_label": "supports",
        "support_bullets": ["snippet supports claim"],
        "oppose_bullets": [],
        "notes": [],
    }

    def fake_adapter(**kwargs):
        assert "instructions" in kwargs
        assert kwargs["bundle_text"] == "bundle-text"
        assert kwargs["model"] == "gpt-standin"
        return {"text": json.dumps(payload), "warnings": ["adapter_warning"]}

    monkeypatch.setattr(scoring, "get_wel_score_fn", lambda model: fake_adapter)

    canonical, warnings, prompt_hash = scoring.call_wel_once("bundle-text", model="gpt-standin")

    assert canonical["stance_label"] == "supports"
    assert pytest.approx(canonical["stance_prob_true"], rel=1e-6) == 0.72
    assert warnings == ["adapter_warning"]
    assert len(prompt_hash) == 64


def test_call_wel_once_raises_when_schema_invalid(monkeypatch):
    def bad_adapter(**kwargs):
        return {"text": "{}", "warnings": []}

    monkeypatch.setattr(scoring, "get_wel_score_fn", lambda model: bad_adapter)

    with pytest.raises(WELSchemaError):
        scoring.call_wel_once("bundle-text")
