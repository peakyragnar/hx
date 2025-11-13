from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from rich.console import Console
from rich.table import Table
from typer.testing import CliRunner

from heretix.cli import app

runner = CliRunner()


def _write_config(path: Path, lines: Iterable[str]) -> None:
    path.write_text("\n".join(lines))


def _rich_cli_run(tmp_path: Path, *, cfg_lines: List[str], extra_args: List[str], log_stub: str) -> tuple[dict, Path]:
    cfg_path = tmp_path / f"{log_stub}.yaml"
    out_path = tmp_path / f"{log_stub}.json"
    db_path = tmp_path / f"{log_stub}.sqlite"
    log_path = tmp_path / f"{log_stub}_rich.log"

    _write_config(cfg_path, cfg_lines)

    console = Console(record=True, width=120)
    console.rule(f"[bold green]Heretix CLI E2E :: {log_stub}")
    command = [
        "run",
        "--config",
        str(cfg_path),
        "--out",
        str(out_path),
        "--mock",
    ] + extra_args
    console.log("Function", "heretix.cli.cmd_run")
    console.log("Command", " ".join(command))
    console.log("Output artifact", out_path)
    env = {
        "DATABASE_URL": f"sqlite:///{db_path}",
        "HERETIX_RPL_SEED": "42",
    }

    result = runner.invoke(app, command, env=env)
    console.log("Exit code", result.exit_code)
    console.log("CLI stdout", result.output)
    assert result.exit_code == 0, console.export_text()

    payload = json.loads(out_path.read_text())
    console.log("Payload keys", sorted(payload.keys()))

    table = Table(title="Combined verdict summary", show_footer=False)
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Model", style="bold")
    table.add_column("Mode")
    table.add_column("Combined p", justify="right")
    table.add_column("CI95", justify="right")
    table.add_column("Weights (web/prior)", justify="right")

    for idx, run in enumerate(payload.get("runs", []), start=1):
        combined = run.get("combined") or {}
        weights = run.get("weights") or {}
        ci = combined.get("ci95") or [None, None]
        ci_text = f"[{ci[0]:.3f},{ci[1]:.3f}]" if ci[0] is not None and ci[1] is not None else "n/a"
        w_web = weights.get("w_web")
        w_prior = 1.0 - w_web if isinstance(w_web, (int, float)) else None
        weight_text = (
            f"web={w_web:.2f} prior={w_prior:.2f}"
            if isinstance(w_web, (int, float)) and isinstance(w_prior, float)
            else "n/a"
        )
        table.add_row(
            str(idx),
            str(run.get("model")),
            str(run.get("mode")),
            f"{combined.get('p', 0.0):.3f}",
            ci_text,
            weight_text,
        )
    console.print(table)

    log_path.write_text(console.export_text())
    return payload, log_path


def test_rich_cli_logging_multi_model_baseline(tmp_path: Path):
    payload, log_path = _rich_cli_run(
        tmp_path,
        cfg_lines=[
            'claim: "Rich baseline multi-model claim"',
            "models:",
            "  - gpt-5",
            "  - grok-4",
            "prompt_version: rpl_g5_v2",
            "K: 4",
            "R: 1",
            "T: 4",
            "B: 100",
            "max_output_tokens: 256",
        ],
        extra_args=[
            "--mode",
            "baseline",
        ],
        log_stub="rich_baseline",
    )
    assert payload.get("requested_models") == ["gpt-5", "grok-4"]
    runs = payload.get("runs") or []
    assert [run["model"] for run in runs] == ["gpt-5", "grok-4"]
    for run in runs:
        combined = run.get("combined") or {}
        weights = run.get("weights") or {}
        assert "weight_web" in combined or weights.get("w_web") == 0.0
        assert combined.get("label") in {"Likely true", "Likely false", "Uncertain"}
    log_text = log_path.read_text()
    assert "Heretix CLI E2E :: rich_baseline" in log_text
    assert "Function" in log_text


def test_rich_cli_logging_web_informed(tmp_path: Path):
    payload, log_path = _rich_cli_run(
        tmp_path,
        cfg_lines=[
            'claim: "Rich web-informed claim"',
            "model: gpt-5",
            "prompt_version: rpl_g5_v2",
            "K: 4",
            "R: 1",
            "T: 4",
            "B: 100",
            "max_output_tokens: 256",
        ],
        extra_args=[
            "--mode",
            "web_informed",
        ],
        log_stub="rich_web",
    )
    runs = payload.get("runs") or []
    assert len(runs) == 1
    run = runs[0]
    assert run.get("mode") == "web_informed"
    assert run.get("web") is not None, "web block missing in web_informed run"
    combined = run.get("combined") or {}
    assert combined.get("weight_web") is not None
    assert combined.get("weight_prior") is not None
    log_text = log_path.read_text()
    assert "Heretix CLI E2E :: rich_web" in log_text
    assert "web_informed" in log_text
