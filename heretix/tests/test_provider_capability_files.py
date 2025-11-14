from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from heretix.provider import config as provider_config


CAP_FILES = {
    "openai": "config_openai.yaml",
    "xai": "config_grok.yaml",
    "google": "config_gemini.yaml",
    "deepseek": "config_deepseek.yaml",
}


def _load_capability(provider: str) -> provider_config.ProviderCapabilities:
    cfg_dir = Path(__file__).resolve().parents[1] / "provider"
    path = cfg_dir / CAP_FILES[provider]
    raw = yaml.safe_load(path.read_text())
    return provider_config.ProviderCapabilities.model_validate(raw)


@pytest.mark.parametrize("provider", CAP_FILES.keys())
def test_capability_files_validate_and_map_models(provider: str):
    caps = _load_capability(provider)
    assert caps.provider == provider
    assert caps.default_model in caps.api_model_map
    assert caps.max_output_tokens > 0


def test_openai_capability_details():
    caps = _load_capability("openai")
    assert caps.api_model_map["gpt5-default"].startswith("gpt-5")
    assert caps.supports_json_schema
    assert caps.supports_seed


def test_grok_capability_details():
    caps = _load_capability("xai")
    assert caps.api_model_map["grok4-default"] == "grok-4"
    assert caps.supports_json_mode
    assert not caps.supports_json_schema


def test_gemini_capability_details():
    caps = _load_capability("google")
    assert caps.api_model_map["gemini25-default"].startswith("gemini-2.5")
    assert caps.supports_tools
    assert not caps.supports_seed


def test_deepseek_capability_details():
    caps = _load_capability("deepseek")
    assert caps.api_model_map["deepseek-r1-default"] == "deepseek-reasoner"
    assert caps.max_output_tokens >= 4096
    assert not caps.supports_tools
