from heretix import pipeline


def test_should_generate_llm_narration_blocks_cache_hits():
    assert pipeline._should_generate_llm_narration(False, {"p": 0.5}, 0.5) is True
    assert pipeline._should_generate_llm_narration(False, {"p": 0.5}, 0.999) is False


def test_should_generate_llm_narration_respects_mock_and_missing_blocks():
    assert pipeline._should_generate_llm_narration(True, {"p": 0.5}, 0.0) is False
    assert pipeline._should_generate_llm_narration(False, None, 0.0) is False
