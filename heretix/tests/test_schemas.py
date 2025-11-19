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
    WebBlockV1,
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
            ci95=[0.4, 0.7],
            label="Uncertain",
            weight_prior=0.8,
            weight_web=0.1,
        )


def test_combined_block_accepts_resolution_metadata():
    block = CombinedBlockV1(
        prob_true=0.8,
        ci_lo=0.7,
        ci_hi=0.9,
        ci95=[0.7, 0.9],
        label="Likely true",
        weight_prior=0.25,
        weight_web=0.75,
        resolved=True,
        resolved_truth=True,
        resolved_reason="Consensus",
        resolved_citations=[{"url": "https://example.com"}],
        support=3.2,
        contradict=0.4,
        domains=3,
    )
    assert block.resolved is True
    assert block.resolved_citations[0]["url"] == "https://example.com"
    assert block.support == pytest.approx(3.2)
    assert block.domains == 3


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


def test_rpl_sample_accepts_canonical_payload():
    payload = {
        "belief": {"prob_true": 0.74, "label": "likely"},
        "reasons": ["Underlying data favors the claim", "Expert consensus is aligned"],
        "assumptions": "macroeconomic conditions stay stable",
        "uncertainties": ["sample size", "regional variance"],
        "flags": {"refused": False, "off_topic": False},
    }
    sample = RPLSampleV1(**payload)
    assert sample.belief.prob_true == pytest.approx(0.74)
    assert sample.belief.label == "likely"
    assert sample.assumptions == ["macroeconomic conditions stay stable"]
    assert len(sample.reasons) == 2
    assert not sample.flags.refused


def test_wel_doc_accepts_canonical_payload():
    payload = {
        "stance_prob_true": 0.32,
        "stance_label": "supports",
        "support_bullets": ["Study reports improvement", "Pilot showed similar gains"],
        "oppose_bullets": ["Sparse replication"],
        "notes": "Source limited to U.S. trials",
    }
    doc = WELDocV1(**payload)
    assert doc.stance_label == "supports"
    assert doc.support_bullets == ["Study reports improvement", "Pilot showed similar gains"]
    assert doc.oppose_bullets == ["Sparse replication"]
    assert doc.notes == ["Source limited to U.S. trials"]


def test_block_models_accept_canonical_payloads():
    prior = PriorBlockV1(
        prob_true=0.61,
        ci_lo=0.48,
        ci_hi=0.72,
        width=0.24,
        stability=0.67,
        compliance_rate=0.98,
    )
    web = WebBlockV1(prob_true=0.58, ci_lo=0.41, ci_hi=0.70, evidence_strength="moderate")
    combined = CombinedBlockV1(
        prob_true=0.6,
        ci_lo=0.5,
        ci_hi=0.7,
        ci95=[0.5, 0.7],
        label="Balanced",
        weight_prior=0.55,
        weight_web=0.45,
    )

    assert prior.prob_true == pytest.approx(0.61)
    assert web.evidence_strength == "moderate"
    assert combined.weight_prior + combined.weight_web == pytest.approx(1.0)


def test_simple_expl_canonical_payload():
    payload = {
        "title": "Why the verdict looks this way",
        "body_paragraphs": [
            "  Model prior clusters near fifty percent.",
            "Web evidence remains mixed but leans supportive.",
        ],
        "bullets": ["First supporting detail", "Second supporting detail"],
    }
    expl = SimpleExplV1(**payload)
    assert expl.title == "Why the verdict looks this way"
    assert expl.body_paragraphs == [
        "Model prior clusters near fifty percent.",
        "Web evidence remains mixed but leans supportive.",
    ]
    assert expl.bullets == ["First supporting detail", "Second supporting detail"]


def test_rpl_sample_rejects_probabilities_out_of_bounds():
    bad_payload = {
        "belief": {"prob_true": 1.2, "label": "likely"},
        "reasons": ["text"],
    }
    with pytest.raises(ValidationError):
        RPLSampleV1(**bad_payload)


def test_web_block_rejects_invalid_strength():
    with pytest.raises(ValidationError):
        WebBlockV1(prob_true=0.4, ci_lo=0.3, ci_hi=0.5, evidence_strength="overwhelming")


def test_simple_expl_rejects_blank_title():
    with pytest.raises(ValidationError):
        SimpleExplV1(title="   ", body_paragraphs=["Valid body"], bullets=[])
