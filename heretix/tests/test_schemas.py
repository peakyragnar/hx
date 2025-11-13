from __future__ import annotations

import pytest
from pydantic import ValidationError

from heretix.schemas import (
    Belief,
    CombinedBlockV1,
    PriorBlockV1,
    RPLSampleV1,
    SimpleExplV1,
    WELDocV1,
)


def test_rpl_sample_v1_normalizes_lists():
    sample = RPLSampleV1(
        belief=Belief(prob_true=0.62, label="likely"),
        reasons=["Tariff data shows muted impact"],
        assumptions="Energy prices stay flat",
        uncertainties=[None, "Data recency"],
    )
    assert sample.assumptions == ["Energy prices stay flat"]
    assert sample.uncertainties == ["Data recency"]


def test_belief_rejects_invalid_label():
    with pytest.raises(ValidationError):
        Belief(prob_true=0.4, label="maybe")


def test_wel_doc_v1_validates_stance_label():
    with pytest.raises(ValidationError):
        WELDocV1(
            stance_prob_true=0.5,
            stance_label="neutral",
            support_bullets=["placeholder"],
            oppose_bullets=[],
        )


def test_prior_block_requires_prob_inside_ci():
    with pytest.raises(ValidationError):
        PriorBlockV1(
            prob_true=0.9,
            ci_lo=0.2,
            ci_hi=0.6,
            width=0.4,
            stability=0.5,
            compliance_rate=0.95,
        )


def test_combined_block_enforces_weight_sum():
    with pytest.raises(ValidationError):
        CombinedBlockV1(
            prob_true=0.55,
            ci_lo=0.4,
            ci_hi=0.7,
            label="Uncertain",
            weight_prior=0.8,
            weight_web=0.1,
        )


def test_simple_expl_requires_body_paragraph():
    with pytest.raises(ValidationError):
        SimpleExplV1(title="Summary", body_paragraphs=[], bullets=["One"])


def test_simple_expl_strips_whitespace():
    expl = SimpleExplV1(
        title="  Combined verdict  ",
        body_paragraphs=["  Prior leans true."],
        bullets=["  Evidence is balanced.  ", ""],
    )
    assert expl.title == "Combined verdict"
    assert expl.body_paragraphs == ["Prior leans true."]
    assert expl.bullets == ["Evidence is balanced."]
