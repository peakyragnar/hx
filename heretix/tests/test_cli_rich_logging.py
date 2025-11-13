from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table
from typer.testing import CliRunner

from heretix.cli import app


runner = CliRunner()


def _write_basic_cfg(path: Path, claim: str) -> None:
    path.write_text(
        "\n".join(
            [
                f"claim: \"{claim}\"",
                "model: gpt-5",
                "prompt_version: rpl_g5_v2",
                "K: 6",
                "R: 2",
                "T: 6",
                "B: 5000",
                "max_output_tokens: 256",
            ]
        )
    )


def test_cli_mock_run_with_rich_logging(tmp_path: Path):
    claim = "Rich logging e2e mock claim"
    cfg_path = tmp_path / "cfg.yaml"
    _write_basic_cfg(cfg_path, claim)

    out_path = tmp_path / "rich_run.json"
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'rich.sqlite'}"}

    console = Console(record=True, width=120)
    console.rule("[bold green]Heretix CLI Mock Run[/bold green]")
    console.log({"event": "config_prepared", "claim": claim, "cfg": str(cfg_path)})

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
    run = payload["runs"][0]
    aggregates = run.get("aggregates") or {}
    combined = run.get("combined") or {}
    prior_prob = float(aggregates.get("prob_true_rpl") or 0.0)
    ci_vals = aggregates.get("ci95") or [None, None]
    combined_prob = float(combined.get("p") or prior_prob)
    sampling = run.get("sampling") or {}
    weights = run.get("weights") or {}

    table = Table(title="Heretix Mock Run (Rich Log)", expand=True)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")
    table.add_row("Claim", run.get("claim") or "<missing>")
    table.add_row("Model", run.get("model") or "<missing>")
    table.add_row("Mode", str(payload.get("mode")))
    table.add_row("Planned K×R", f"{sampling.get('K')}×{sampling.get('R')}")
    table.add_row("Prior p", f"{prior_prob:.3f}")
    table.add_row("CI95", str(ci_vals))
    table.add_row("Combined p", f"{combined_prob:.3f}")
    table.add_row("Weights", str(weights))
    console.print(table)

    console.log(
        "Functions invoked",
        "heretix.cli.cmd_run",
        "heretix.pipeline.perform_run",
        "heretix.rpl.run_single_version (mock)",
    )
    console.log(
        "Output summary",
        {
            "prior_p": f"{prior_prob:.3f}",
            "combined_p": f"{combined_prob:.3f}",
            "ci95": ci_vals,
        },
    )

    transcript = console.export_text()
    assert "Heretix CLI Mock Run" in transcript
    assert "Functions invoked" in transcript
    assert claim in transcript
    assert "combined_p" in transcript
