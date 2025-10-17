from __future__ import annotations

from pathlib import Path
import json
from typer.testing import CliRunner

from heretix.cli import app


runner = CliRunner()


def test_cli_smoke_single_version(tmp_path: Path):
    # create a minimal config file
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "\n".join([
            'claim: "tariffs don\'t cause inflation"',
            "model: gpt-5",
            "prompt_version: rpl_g5_v2",
            "K: 6",
            "R: 1",
            "T: 6",
            "B: 5000",
            "max_output_tokens: 256",
        ])
    )
    out_path = tmp_path / "out.json"
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'smoke_single.sqlite'}"}
    result = runner.invoke(app, [
        "run",
        "--config", str(cfg_path),
        "--out", str(out_path),
        "--mock",
    ], env=env)
    assert result.exit_code == 0, result.output
    doc = json.loads(out_path.read_text())
    assert isinstance(doc.get("runs"), list) and len(doc["runs"]) == 1


def test_cli_smoke_multi_version(tmp_path: Path):
    # uses the same version twice to exercise A/B path
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "\n".join([
            'claim: "tariffs don\'t cause inflation"',
            "model: gpt-5",
            "prompt_version: rpl_g5_v2",
            "K: 4",
            "R: 1",
            "T: 4",
            "B: 5000",
            "max_output_tokens: 256",
        ])
    )
    out_path = tmp_path / "out.json"
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'smoke_multi.sqlite'}"}
    result = runner.invoke(app, [
        "run",
        "--config", str(cfg_path),
        "--out", str(out_path),
        "--mock",
        "--prompt-version", "rpl_g5_v2",
        "--prompt-version", "rpl_g5_v2",
    ], env=env)
    assert result.exit_code == 0, result.output
    doc = json.loads(out_path.read_text())
    assert isinstance(doc.get("runs"), list) and len(doc["runs"]) == 2


def test_cli_smoke_web_informed_mock(tmp_path: Path):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "\n".join([
            'claim: "web informed mock"',
            "model: gpt-5",
            "prompt_version: rpl_g5_v2",
            "K: 4",
            "R: 1",
            "T: 4",
            "B: 1000",
            "max_output_tokens: 128",
        ])
    )
    out_path = tmp_path / "out.json"
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'web_informed_mock.sqlite'}"}
    result = runner.invoke(app, [
        "run",
        "--config", str(cfg_path),
        "--out", str(out_path),
        "--mock",
        "--mode", "web_informed",
    ], env=env)
    assert result.exit_code == 0, result.output
    payload = json.loads(out_path.read_text())
    web_block = payload["runs"][0].get("web")
    assert web_block is not None
    assert web_block["evidence"]["n_docs"] == 0.0
    assert "replicates" not in web_block
