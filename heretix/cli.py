from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import json
import os

import typer
from dotenv import load_dotenv

from .config import load_run_config, RunConfig
from .rpl import run_single_version


app = typer.Typer(help="Heretix (new) RPL harness")


@app.callback()
def _root_callback():
    """Heretix CLI root."""
    # No root options; subcommands handle actions.
    pass


@app.command("run")
def cmd_run(
    config: Path = typer.Option(..., exists=True, dir_okay=False, help="Path to run config YAML/JSON"),
    prompt_version: List[str] = typer.Option(None, help="Override prompt versions to run (one or many)"),
    out: Path = typer.Option(Path("runs/rpl_run.json"), help="Output JSON file (A/B summary)"),
):
    """Run single or multiple prompt versions and print compact A/B results."""
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        typer.echo("ERROR: OPENAI_API_KEY not set (set in env or .env)", err=True)
        raise typer.Exit(1)

    cfg = load_run_config(str(config))
    versions = prompt_version if prompt_version else [cfg.prompt_version]

    results = []
    for v in versions:
        local_cfg = RunConfig(**{**cfg.__dict__})
        local_cfg.prompt_version = v
        prompt_file = local_cfg.prompt_file_path or (Path(__file__).parent / "prompts" / f"{v}.yaml")
        typer.echo(f"Running {local_cfg.model}  K={local_cfg.K} R={local_cfg.R}  version={v}")
        res = run_single_version(local_cfg, prompt_file=str(prompt_file))
        results.append(res)

    # A/B table summary to stdout
    for r in results:
        a = r["aggregates"]
        typer.echo(
            f"v={r['prompt_version']}  p={a['prob_true_rpl']:.3f}  CI95=[{a['ci95'][0]:.3f},{a['ci95'][1]:.3f}]  width={a['ci_width']:.3f}  stab={a['stability_score']:.3f}  compl={a['rpl_compliance_rate']:.2f}  cache={a['cache_hit_rate']:.2f}"
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"runs": results}, indent=2))
    typer.echo(f"Wrote {out}")


if __name__ == "__main__":
    # Allow module execution via: python -m heretix.cli
    app()
