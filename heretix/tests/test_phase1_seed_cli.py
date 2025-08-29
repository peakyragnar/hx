from __future__ import annotations

from pathlib import Path
import json
from typer.testing import CliRunner

from heretix.cli import app


runner = CliRunner()


def test_cli_seed_from_config_file(tmp_path: Path):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "\n".join([
            'claim: "seed from file test"',
            "model: gpt-5",
            "prompt_version: rpl_g5_v2",
            "K: 4",
            "R: 1",
            "T: 4",
            "B: 1000",
            "seed: 12345",
            "max_output_tokens: 128",
        ])
    )

    # Describe should show effective bootstrap seed = 12345
    result_desc = runner.invoke(app, ["describe", "--config", str(cfg_path)])
    assert result_desc.exit_code == 0, result_desc.output
    desc = json.loads(result_desc.stdout)
    assert desc["plan"]["bootstrap_seed_effective"] == 12345

    # Run should persist same seed in aggregation
    out_path = tmp_path / "out.json"
    result_run = runner.invoke(app, [
        "run",
        "--config", str(cfg_path),
        "--out", str(out_path),
        "--mock",
    ])
    assert result_run.exit_code == 0, result_run.output
    doc = json.loads(out_path.read_text())
    assert doc["runs"][0]["aggregation"]["bootstrap_seed"] == 12345

