from heretix.provider.utils import infer_provider_from_model


def test_infer_provider_openai_default():
    assert infer_provider_from_model("gpt-5") == "openai"
    assert infer_provider_from_model(None) == "openai"


def test_infer_provider_grok():
    assert infer_provider_from_model("grok-4") == "xai"
    assert infer_provider_from_model("XAI:GROK4") == "xai"


def test_infer_provider_gemini():
    assert infer_provider_from_model("gemini25-default") == "google"
