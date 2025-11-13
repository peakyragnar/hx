from __future__ import annotations

import json
import sqlite3
from io import StringIO
from pathlib import Path
from typing import Sequence
from unittest import mock

import heretix.cli as cli_module
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typer.testing import CliRunner

from heretix.cli import app


runner = CliRunner()


def _build_console(title: str) -> Console:
    console = Console(file=StringIO(), record=True, width=120)
    console.rule(f"[bold cyan]{title}[/bold cyan]")
    return console


def _emit_inputs(console: Console, cfg_path: Path, command: Sequence[str], env: dict[str, str], out_path: Path) -> None:
    cfg_preview = cfg_path.read_text().strip()
    console.print(Panel.fit(cfg_preview, title="Inputs", subtitle=str(cfg_path)))
    console.print(Panel.fit("\n".join(command), title="CLI Invocation"))
    env_table = Table(title="Environment" )
    env_table.add_column("Key")
    env_table.add_column("Value")
    for key, value in env.items():
        env_table.add_row(key, value)
    console.print(env_table)
    console.print(Panel.fit(str(out_path), title="Output artifact path"))


def _run_cli_with_logging(
    *,
    label: str,
    cfg_path: Path,
    command: Sequence[str],
    env: dict[str, str],
    expected_perform_calls: int,
) -> Console:
    console = _build_console(label)
    _emit_inputs(console, cfg_path, command, env, Path(command[-1]))
    with mock.patch("heretix.cli.perform_run", wraps=cli_module.perform_run) as perform_spy:
        result = runner.invoke(app, list(command), env=env)
    console.print(
        Panel.fit(
            result.stdout or "(no stdout)",
            title="CLI stdout",
            subtitle=f"exit_code={result.exit_code}",
        )
    )
    assert result.exit_code == 0, result.stderr or result.stdout
    func_lines = [
        "typer entrypoint → heretix.cli.cmd_run",
        f"heretix.cli.cmd_run → heretix.cli.perform_run (calls={perform_spy.call_count})",
    ]
    console.print(Panel.fit("\n".join(func_lines), title="Functions Called", subtitle="call flow"))
    assert perform_spy.call_count == expected_perform_calls
    return console


def _fetch_checks(db_path: Path) -> list[sqlite3.Row]:
    assert db_path.exists(), f"database missing at {db_path}"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT claim, model, mode, prompt_version FROM checks ORDER BY created_at DESC"
        ).fetchall()
    assert rows, "expected at least one check row"
    return rows


def _log_results(console: Console, payload: dict, db_rows: list[sqlite3.Row]) -> None:
    run_entry = payload["runs"][0]
    combined = run_entry.get("combined") or run_entry.get("prior") or {}
    snapshot = {
        "mode": payload.get("mode"),
        "requested_models": payload.get("requested_models"),
        "claim": run_entry.get("claim"),
        "model": run_entry.get("model"),
        "prob_true": combined.get("p") or combined.get("prob_true"),
        "ci95": combined.get("ci95"),
    }
    console.print(Panel.fit(json.dumps(snapshot, indent=2), title="Result snapshot", subtitle="aggregates"))
    table = Table(title="DB Checks")
    table.add_column("Claim")
    table.add_column("Model")
    table.add_column("Mode")
    table.add_column("Prompt")
    for row in db_rows:
        table.add_row(row["claim"][:36], row["model"], row["mode"], row["prompt_version"])
    console.print(table)


def test_phase1_mock_run_with_rich_logging(tmp_path: Path) -> None:
    cfg_path = tmp_path / "rich_baseline.yaml"
    cfg_path.write_text(
        "\n".join([
            'claim: "Rich logging baseline claim"',
            "model: gpt-5",
            "prompt_version: rpl_g5_v2",
            "K: 4",
            "R: 1",
            "T: 4",
            "B: 64",
            "max_output_tokens: 256",
        ])
    )
    out_path = tmp_path / "rich_baseline.json"
    db_path = tmp_path / "rich_baseline.sqlite"
    env = {"DATABASE_URL": f"sqlite:///{db_path}"}
    command = [
        "run",
        "--config",
        str(cfg_path),
        "--mock",
        "--out",
        str(out_path),
    ]

    console = _run_cli_with_logging(
        label="Phase-1 baseline mock run",
        cfg_path=cfg_path,
        command=command,
        env=env,
        expected_perform_calls=1,
    )

    assert out_path.exists(), "CLI did not write the JSON artifact"
    payload = json.loads(out_path.read_text())
    db_rows = _fetch_checks(db_path)
    _log_results(console, payload, db_rows)
    log_dump = console.export_text()
    assert "Functions Called" in log_dump
    assert "Result snapshot" in log_dump
    assert "DB Checks" in log_dump
    assert payload.get("mode") == "baseline"
    assert db_rows[0]["mode"] == "baseline"


def test_phase1_web_mode_with_rich_logging(tmp_path: Path) -> None:
    cfg_path = tmp_path / "rich_web.yaml"
    cfg_path.write_text(
        "\n".join([
            'claim: "Rich logging web claim"',
            "model: gpt-5",
            "prompt_version: rpl_g5_v2",
            "K: 8",
            "R: 2",
            "T: 8",
            "B: 5000",
            "max_output_tokens: 512",
        ])
    )
    out_path = tmp_path / "rich_web.json"
    db_path = tmp_path / "rich_web.sqlite"
    env = {
        "DATABASE_URL": f"sqlite:///{db_path}",
        "HERETIX_RPL_SEED": "123",
    }
    command = [
        "run",
        "--config",
        str(cfg_path),
        "--mock",
        "--mode",
        "web_informed",
        "--out",
        str(out_path),
    ]

    console = _run_cli_with_logging(
        label="Phase-1 web_informed mock run",
        cfg_path=cfg_path,
        command=command,
        env=env,
        expected_perform_calls=1,
    )

    payload = json.loads(out_path.read_text())
    db_rows = _fetch_checks(db_path)
    _log_results(console, payload, db_rows)
    run_entry = payload["runs"][0]
    log_dump = console.export_text()
    assert "web_informed" in log_dump
    assert run_entry.get("simple_expl"), "web_informed run missing simple explanation"
    assert any(row["mode"] == "web_informed" for row in db_rows)
