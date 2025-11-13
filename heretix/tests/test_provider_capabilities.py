from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from heretix.provider import config


@pytest.fixture(autouse=True)
def _reset_capability_cache(monkeypatch: pytest.MonkeyPatch):
    config.reset_provider_capabilities_cache()
    monkeypatch.delenv(config.PROVIDER_CAPABILITIES_ENV, raising=False)
    yield
    config.reset_provider_capabilities_cache()


def test_loads_builtin_capabilities():
    caps = config.load_provider_capabilities(refresh=True)
    assert {"openai", "xai", "google", "deepseek"}.issubset(set(caps.keys()))

    openai = caps["openai"]
    assert openai.default_model == "gpt5-default"
    assert openai.api_model_map["gpt5-default"].startswith("gpt-5")
    assert openai.supports_json_schema is True

    cached = config.load_provider_capabilities()
    assert cached is caps


def test_environment_override_with_single_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    custom_cfg = {
        "provider": "foo",
        "default_model": "foo-default",
        "api_model_map": {"foo-default": "foo-1.0"},
        "supports_json_schema": False,
        "supports_json_mode": True,
        "supports_tools": False,
        "supports_seed": False,
        "max_output_tokens": 1024,
        "default_temperature": 0.25,
    }
    cfg_path = tmp_path / "custom.yaml"
    cfg_path.write_text(yaml.safe_dump(custom_cfg, sort_keys=False), encoding="utf-8")

    monkeypatch.setenv(config.PROVIDER_CAPABILITIES_ENV, str(cfg_path))

    caps = config.load_provider_capabilities(refresh=True)
    assert set(caps.keys()) == {"foo"}

    foo = caps["foo"]
    assert foo.default_model == "foo-default"
    assert foo.api_model_map["foo-default"] == "foo-1.0"
    assert foo.max_output_tokens == 1024
    assert foo.default_temperature == 0.25


def test_capabilities_rich_logging_snapshot():
    """Rich-rendered snapshot of provider capabilities for quick operator review."""

    console = Console(record=True, width=100)
    console.rule("[bold green]Provider capability snapshot")

    console.print(
        Panel.fit(
            "[bold]Functions invoked[/]\n"
            "- heretix.provider.config.load_provider_capabilities(refresh=True)\n"
            "- rich.Table for provider summaries",
            border_style="cyan",
        )
    )

    caps = config.load_provider_capabilities(refresh=True)
    table = Table(title="Capabilities", header_style="bold magenta")
    table.add_column("provider")
    table.add_column("default_model")
    table.add_column("json_schema")
    table.add_column("json_mode")
    table.add_column("seed")
    table.add_column("max_tokens", justify="right")

    for provider, cap in sorted(caps.items()):
        table.add_row(
            provider,
            cap.default_model,
            "yes" if cap.supports_json_schema else "no",
            "yes" if cap.supports_json_mode else "no",
            "yes" if cap.supports_seed else "no",
            str(cap.max_output_tokens),
        )

    console.print(table)
    log_text = console.export_text()

    assert "Provider capability snapshot" in log_text
    assert "Capabilities" in log_text
    assert "openai" in log_text and "gpt5-default" in log_text
