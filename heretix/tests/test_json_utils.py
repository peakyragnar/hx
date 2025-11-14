from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from heretix.provider.json_utils import extract_and_validate, strip_markdown_json
from heretix.schemas import (
    CombinedBlockV1,
    PriorBlockV1,
    RPLSampleV1,
    SimpleExplV1,
    WELDocV1,
    WebBlockV1,
)


def _sample_payload(prob: float | str = 0.58) -> dict:
    return {
        "belief": {"prob_true": prob, "label": "likely"},
        "reasons": ["Recent CPI prints decelerated"],
        "assumptions": ["No external shocks"],
        "uncertainties": ["Sample size small"],
    }


def _canonical_cases():
    return [
        (
            RPLSampleV1,
            {
                "belief": {"prob_true": 0.74, "label": "likely"},
                "reasons": ["Underlying data favors the claim"],
                "assumptions": "macroeconomic conditions stay stable",
                "uncertainties": ["sample size"],
                "flags": {"refused": False, "off_topic": False},
            },
        ),
        (
            WELDocV1,
            {
                "stance_prob_true": 0.32,
                "stance_label": "supports",
                "support_bullets": ["Study reports improvement", "Pilot showed similar gains"],
                "oppose_bullets": ["Sparse replication"],
                "notes": "Source limited to U.S. trials",
            },
        ),
        (
            PriorBlockV1,
            {
                "prob_true": 0.61,
                "ci_lo": 0.48,
                "ci_hi": 0.72,
                "width": 0.24,
                "stability": 0.67,
                "compliance_rate": 0.98,
            },
        ),
        (
            WebBlockV1,
            {
                "prob_true": 0.58,
                "ci_lo": 0.41,
                "ci_hi": 0.70,
                "evidence_strength": "moderate",
            },
        ),
        (
            CombinedBlockV1,
            {
                "prob_true": 0.6,
                "ci_lo": 0.5,
                "ci_hi": 0.7,
                "label": "Balanced",
                "weight_prior": 0.55,
                "weight_web": 0.45,
            },
        ),
        (
            SimpleExplV1,
            {
                "title": "Why the verdict looks this way",
                "body_paragraphs": [
                    "  Model prior clusters near fifty percent.",
                    "Web evidence remains mixed but leans supportive.",
                ],
                "bullets": ["First supporting detail", "Second supporting detail"],
            },
        ),
    ]


_CANONICAL_CASES = _canonical_cases()
_CANONICAL_IDS = [case[0].__name__ for case in _CANONICAL_CASES]


def test_strip_markdown_json_handles_fence():
    payload = json.dumps(_sample_payload())
    wrapped = f"```json\n{payload}\n```"
    assert strip_markdown_json(wrapped) == payload


def test_strip_markdown_json_drops_reasoning_tags():
    payload = json.dumps(_sample_payload())
    wrapped = f"<think>chain-of-thought</think>\n<reflection>more</reflection>{payload}"
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


def test_extract_and_validate_handles_reasoning_tags():
    payload = json.dumps(_sample_payload())
    raw = f"<think>deliberation</think>{payload}"
    parsed, warnings = extract_and_validate(raw, RPLSampleV1)
    assert parsed.belief.prob_true == pytest.approx(0.58)
    assert warnings == []


def test_extract_and_validate_marks_validation_coercion():
    raw = json.dumps(_sample_payload(prob="0.61"))
    parsed, warnings = extract_and_validate(raw, RPLSampleV1)
    assert parsed.belief.prob_true == pytest.approx(0.61)
    assert "validation_coerced" in warnings


@pytest.mark.parametrize("schema_model,payload", _CANONICAL_CASES, ids=_CANONICAL_IDS)
def test_extract_and_validate_accepts_canonical_payloads(schema_model, payload):
    raw = json.dumps(payload)
    parsed, warnings = extract_and_validate(raw, schema_model)
    assert warnings == []
    if schema_model is RPLSampleV1:
        assert parsed.belief.label == "likely"
        assert parsed.assumptions == ["macroeconomic conditions stay stable"]
    elif schema_model is WELDocV1:
        assert parsed.support_bullets[0] == "Study reports improvement"
        assert parsed.oppose_bullets == ["Sparse replication"]
    elif schema_model is PriorBlockV1:
        assert parsed.prob_true == pytest.approx(0.61)
        assert parsed.width == pytest.approx(0.24)
    elif schema_model is WebBlockV1:
        assert parsed.evidence_strength == "moderate"
        assert parsed.ci_hi == pytest.approx(0.70)
    elif schema_model is CombinedBlockV1:
        assert parsed.weight_prior + parsed.weight_web == pytest.approx(1.0)
    elif schema_model is SimpleExplV1:
        assert parsed.body_paragraphs[0] == "Model prior clusters near fifty percent."
        assert parsed.bullets[-1] == "Second supporting detail"


def test_extract_and_validate_raises_when_schema_fails():
    bad_payload = json.dumps({"belief": {"prob_true": 2.0, "label": "likely"}})
    with pytest.raises(ValidationError):
        extract_and_validate(bad_payload, RPLSampleV1)


def test_extract_and_validate_rejects_invalid_combined_weights():
    bad_payload = json.dumps(
        {
            "prob_true": 0.5,
            "ci_lo": 0.3,
            "ci_hi": 0.7,
            "label": "Uncertain",
            "weight_prior": 0.2,
            "weight_web": 0.2,
        }
    )
    with pytest.raises(ValidationError):
        extract_and_validate(bad_payload, CombinedBlockV1)
