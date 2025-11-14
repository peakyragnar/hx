from __future__ import annotations

from pathlib import Path
import json
from typing import Iterable

from typer.testing import CliRunner

from heretix.cli import app
from heretix.constants import SCHEMA_VERSION
from heretix.schemas import CombinedBlockV1, PriorBlockV1


runner = CliRunner()


def _basic_config_lines(claim: str) -> Iterable[str]:
    return [
        f'claim: "{claim}"',
        "model: gpt-5",
        "prompt_version: rpl_g5_v2",
        "K: 4",
        "R: 1",
        "T: 4",
        "B: 500",
        "max_output_tokens: 128",
        "max_prompt_chars: 2000",
    ]


def test_cli_mock_outputs_expected_structure(tmp_path: Path):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("\n".join(_basic_config_lines("cli structure test")))
    out_path = tmp_path / "out.json"
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'structure.sqlite'}"}
    result = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(cfg_path),
            "--out",
            str(out_path),
            "--mock",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(out_path.read_text())
    assert set(payload.keys()) == {"mode", "requested_models", "runs"}
    assert payload["mode"] == "baseline"
    assert payload["requested_models"] == ["gpt-5"]
    run = payload["runs"][0]
    assert run["mock"] is True
    assert run["schema_version"] == SCHEMA_VERSION
    assert run["mode"] == "baseline"
    assert run["sampling"]["K"] == 4
    assert run["prompt_version"].startswith("rpl_g5_v2")

    # Map CLI payloads into canonical schema blocks
    prior_payload = run["prior"]
    prior_ci = list(prior_payload.get("ci95", []))
    if len(prior_ci) < 2:
        prior_ci = [prior_payload.get("p", 0.0)] * 2
    prior_model = PriorBlockV1(
        prob_true=float(prior_payload.get("p", 0.0)),
        ci_lo=float(prior_ci[0]),
        ci_hi=float(prior_ci[1]),
        width=max(0.0, float(prior_ci[1]) - float(prior_ci[0])),
        stability=float(prior_payload.get("stability", 0.0)),
        compliance_rate=float(run["aggregates"].get("rpl_compliance_rate", 0.0)),
    )
    assert 0.0 <= prior_model.prob_true <= 1.0

    combined_payload = run["combined"] or {}
    combined_model = CombinedBlockV1(
        prob_true=float(combined_payload.get("prob_true", combined_payload.get("p", 0.0))),
        ci_lo=float(combined_payload.get("ci_lo", combined_payload.get("prob_true", 0.0))),
        ci_hi=float(combined_payload.get("ci_hi", combined_payload.get("prob_true", 0.0))),
        label=str(combined_payload.get("label", "Uncertain")),
        weight_prior=float(combined_payload.get("weight_prior", 1.0)),
        weight_web=float(combined_payload.get("weight_web", 0.0)),
    )
    assert combined_model.label in {"Likely true", "Likely false", "Uncertain"}


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
            "max_prompt_chars: 2000",
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
            "max_prompt_chars: 2000",
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
            "max_prompt_chars: 2000",
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
