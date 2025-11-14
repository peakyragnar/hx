from __future__ import annotations

import json

from heretix.provider import mock
from heretix.provider.json_utils import extract_and_validate
from heretix.schemas import RPLSampleV1


def test_mock_provider_emits_rpl_sample_schema():
    result = mock.score_claim_mock(
        claim="Sample claim",
        system_text="system",
        user_template="Answer {CLAIM}",
        paraphrase_text="Consider {CLAIM}",
    )

    raw = result.get("raw")
    assert isinstance(raw, dict)
    parsed, warnings = extract_and_validate(json.dumps(raw), RPLSampleV1)
    assert warnings == []
    assert 0.0 <= parsed.belief.prob_true <= 1.0
    assert parsed.belief.label in {
        "very_unlikely",
        "unlikely",
        "uncertain",
        "likely",
        "very_likely",
    }
