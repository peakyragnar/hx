from __future__ import annotations

from pathlib import Path
import json

from typer.testing import CliRunner

from heretix.cli import app


runner = CliRunner()


def test_cli_describe_outputs_plan(tmp_path: Path):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "\n".join([
            'claim: "tariffs don\'t cause inflation"',
            "model: gpt-5",
            "prompt_version: rpl_g5_v2",
            "K: 12",
            "R: 3",
            "T: 6",
            "B: 5000",
            "max_output_tokens: 256",
        ])
    )
    result = runner.invoke(app, ["describe", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert "config" in doc and "plan" in doc
    assert doc["config"]["K"] == 12
    assert doc["config"]["T"] == 6
    assert isinstance(doc["plan"]["planned_counts"], list)


def test_cli_run_dry_run(tmp_path: Path):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "\n".join([
            'claim: "tariffs don\'t cause inflation"',
            "model: gpt-5",
            "prompt_version: rpl_g5_v2",
            "K: 8",
            "R: 2",
            "T: 8",
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
        "--dry-run",
    ])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc.get("mode") == "single"
    assert "plan" in doc
    # Dry-run should not write the output file
    assert not out_path.exists()


## Batch mode removed in single-claim-only design


def test_cli_prompts_file_override(tmp_path: Path):
    # Copy prompt YAML and bump version (YAML-aware to avoid brittle string replace)
    import yaml
    src = Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml"
    custom = tmp_path / "prompt.yaml"
    y = yaml.safe_load(src.read_text())
    y["version"] = "rpl_g5_custom_2099-01-01"
    custom.write_text(yaml.safe_dump(y, sort_keys=False))

    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "\n".join([
            'claim: "tariffs don\'t cause inflation"',
            "model: gpt-5",
            f"prompts_file: {custom}",
            "K: 6",
            "R: 1",
            "T: 6",
            "B: 5000",
            "max_output_tokens: 128",
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
    assert doc["runs"][0]["prompt_version"].startswith("rpl_g5_custom_2099-01-01")
