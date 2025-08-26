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
    result = runner.invoke(app, [
        "run",
        "--config", str(cfg_path),
        "--out", str(out_path),
        "--mock",
    ])
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
    result = runner.invoke(app, [
        "run",
        "--config", str(cfg_path),
        "--out", str(out_path),
        "--mock",
        "--prompt-version", "rpl_g5_v2",
        "--prompt-version", "rpl_g5_v2",
    ])
    assert result.exit_code == 0, result.output
    doc = json.loads(out_path.read_text())
    assert isinstance(doc.get("runs"), list) and len(doc["runs"]) == 2
