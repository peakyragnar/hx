from __future__ import annotations

import textwrap
from pathlib import Path

from heretix.config import RunConfig, load_run_config


def create_config(tmp_path: Path, payload: str) -> Path:
    path = tmp_path / "run.yaml"
    path.write_text(textwrap.dedent(payload))
    return path


def test_load_run_config_sets_logical_model_default(tmp_path):
    path = create_config(
        tmp_path,
        """
        claim: "example"
        model: "gpt-5"
        prompt_version: "rpl_g5_v2"
        """,
    )
    cfg = load_run_config(path)
    assert isinstance(cfg, RunConfig)
    assert cfg.logical_model == "gpt-5"
    assert cfg.model == "gpt-5"
    assert cfg.provider == "openai"
    assert cfg.provider_locked is False


def test_load_run_config_respects_explicit_logical_model(tmp_path):
    path = create_config(
        tmp_path,
        """
        claim: "example"
        model: "gpt-5"
        logical_model: "gpt5-default"
        provider: "openai"
        """,
    )
    cfg = load_run_config(path)
    assert cfg.logical_model == "gpt5-default"
    assert cfg.model == "gpt5-default"
    assert cfg.provider == "openai"
    assert cfg.provider_locked is True
