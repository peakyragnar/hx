from heretix.verdicts import finalize_combined_block, verdict_label


def test_verdict_label_thresholds():
    assert verdict_label(0.75) == "Likely true"
    assert verdict_label(0.2) == "Likely false"
    assert verdict_label(0.5) == "Uncertain"
    assert verdict_label(None) == "Uncertain"
    assert verdict_label("not-a-number") == "Uncertain"


def test_finalize_combined_block_adds_metadata():
    block = {"p": 0.55, "ci95": [0.4, 0.7]}
    enriched = finalize_combined_block(block, weight_web=0.65)

    assert enriched["prob_true"] == 0.55
    assert enriched["ci_lo"] == 0.4
    assert enriched["ci_hi"] == 0.7
    assert enriched["label"] == "Uncertain"
    assert enriched["weight_web"] == 0.65
    assert enriched["weight_prior"] == 0.35


def test_finalize_combined_block_uses_existing_weight_when_missing_param():
    block = {"p": 0.9, "ci95": [0.8, 0.96], "weight_web": 0.25}
    enriched = finalize_combined_block(block, weight_web=None)

    assert enriched["weight_web"] == 0.25
    assert enriched["weight_prior"] == 0.75
    assert enriched["label"] == "Likely true"
