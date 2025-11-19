from __future__ import annotations

from heretix.provider.registry import get_score_fn, list_registered_models


ALIAS_TO_MODULE = {
    "gpt-5": "heretix.provider.openai_gpt5",
    "gpt5-default": "heretix.provider.openai_gpt5",
    "openai": "heretix.provider.openai_gpt5",
    "grok-4": "heretix.provider.grok_xai",
    "grok4-default": "heretix.provider.grok_xai",
    "gemini25-default": "heretix.provider.gemini_google",
    "google": "heretix.provider.gemini_google",
}


def test_registered_models_include_expected_aliases():
    models = set(list_registered_models())
    missing = {alias for alias in ALIAS_TO_MODULE if alias not in models}
    assert not missing, f"Missing registered aliases: {missing}"


def test_get_score_fn_returns_adapter_functions():
    for alias, module_name in ALIAS_TO_MODULE.items():
        fn = get_score_fn(alias)
        assert callable(fn), f"Adapter for {alias} should be callable"
        assert fn.__module__ == module_name
