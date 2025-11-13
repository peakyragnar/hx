from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from heretix.provider.json_utils import extract_and_validate, strip_markdown_json
from heretix.schemas import RPLSampleV1


def _sample_payload(prob: float | str = 0.58) -> dict:
    return {
        "belief": {"prob_true": prob, "label": "likely"},
        "reasons": ["Recent CPI prints decelerated"],
        "assumptions": ["No external shocks"],
        "uncertainties": ["Sample size small"],
    }


def test_strip_markdown_json_handles_fence():
    payload = json.dumps(_sample_payload())
    wrapped = f"```json\n{payload}\n```"
    assert strip_markdown_json(wrapped) == payload


def test_strip_markdown_json_errors_without_json():
    with pytest.raises(ValueError):
        strip_markdown_json("no json here")


def test_extract_and_validate_happy_path():
    raw = json.dumps(_sample_payload())
    parsed, warnings = extract_and_validate(raw, RPLSampleV1)
    assert parsed.belief.prob_true == pytest.approx(0.58)
    assert warnings == []


def test_extract_and_validate_repairs_wrapped_text():
    payload = json.dumps(_sample_payload())
    raw = f"Here you go:```json\n{payload}\n```Thanks!"
    parsed, warnings = extract_and_validate(raw, RPLSampleV1)
    assert parsed.belief.label == "likely"
    assert warnings == ["json_repaired_simple"]


def test_extract_and_validate_marks_validation_coercion():
    raw = json.dumps(_sample_payload(prob="0.61"))
    parsed, warnings = extract_and_validate(raw, RPLSampleV1)
    assert parsed.belief.prob_true == pytest.approx(0.61)
    assert "validation_coerced" in warnings


def test_extract_and_validate_raises_when_schema_fails():
    bad_payload = json.dumps({"belief": {"prob_true": 2.0, "label": "likely"}})
    with pytest.raises(ValidationError):
        extract_and_validate(bad_payload, RPLSampleV1)
