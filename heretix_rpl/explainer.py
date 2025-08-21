"""
Heretix RPL Run Explainer

Reads a saved RPL JSON output and prints a plain-English explanation of:
- What estimator did
- Key aggregates (p_RPL, CI, stability)
- Diagnostics (template counts, imbalance, template IQR)
- Provenance (prompt_version, provider_model_id, bootstrap seed)

Usage:
  uv run heretix-rpl-explain runs/rpl_run.json
"""
from __future__ import annotations
import json
from pathlib import Path
import typer

app = typer.Typer(help="Explain a saved Heretix RPL run JSON in plain English")


def _fmt_pct(x: float) -> str:
    return f"{x:.3f}"


@app.command()
def explain(path: Path = typer.Argument(..., help="Path to RPL JSON output")) -> None:
    if not path.exists():
        typer.echo(f"ERROR: File not found: {path}", err=True)
        raise typer.Exit(1)

    data = json.loads(path.read_text())

    claim = data.get("claim")
    model = data.get("model")
    prompt_version = data.get("prompt_version")
    sampling = data.get("sampling", {})
    agg = data.get("aggregates", {})
    aggi = data.get("aggregation", {})

    p = agg.get("prob_true_rpl")
    ci = agg.get("ci95", [None, None])
    ciw = agg.get("ci_width")
    stab = agg.get("stability_score")
    stab_band = agg.get("stability_band")
    is_stable = agg.get("is_stable")

    method = aggi.get("method")
    B = aggi.get("B")
    center = aggi.get("center")
    trim = aggi.get("trim")
    seed = aggi.get("bootstrap_seed")
    n_templates = aggi.get("n_templates")
    counts = aggi.get("counts_by_template", {})
    imb = aggi.get("imbalance_ratio")
    tpl_iqr = aggi.get("template_iqr_logit")

    # Header
    typer.echo("Heretix RPL Run Explanation\n=============================")
    if claim:
        typer.echo(f"Claim: {claim}")
    if model:
        typer.echo(f"Model: {model}")
    if prompt_version:
        typer.echo(f"Prompt version: {prompt_version}")
    if sampling:
        K = sampling.get("K"); R = sampling.get("R"); N = sampling.get("N")
        typer.echo(f"Sampling: K={K}, R={R}, N={N}")

    # Aggregates
    typer.echo("\nAggregate Results:")
    if p is not None and ci[0] is not None:
        typer.echo(f"- p_RPL: {p:.3f}")
        typer.echo(f"- CI95: [{ci[0]:.3f}, {ci[1]:.3f}] (width {ciw:.3f})")
    if stab is not None:
        typer.echo(f"- Stability: {stab:.3f} (band: {stab_band}, is_stable={is_stable})")

    # Method
    typer.echo("\nEstimator & Provenance:")
    typer.echo(f"- Method: {method}")
    typer.echo(f"- Center: {center} (trim={trim})  |  Bootstrap B={B}")
    typer.echo(f"- Deterministic bootstrap_seed: {seed}")

    # Diagnostics
    typer.echo("\nDiagnostics:")
    if n_templates is not None:
        typer.echo(f"- Unique templates: {n_templates}")
    if counts:
        typer.echo(f"- Counts by template: {counts}")
    if imb is not None:
        typer.echo(f"- Imbalance ratio (max/min): {imb:.3f}")
    if tpl_iqr is not None:
        typer.echo(f"- Template IQR (logit): {tpl_iqr:.4f}")

    # Plain-English narrative
    typer.echo("\nNarrative:")
    typer.echo("- We asked the claim across multiple paraphrase templates; each template got equal weight.")
    if n_templates and n_templates >= 5 and center == "trimmed":
        typer.echo("- We dropped the most extreme two template means and averaged the middle ones (20% trimmed center).")
    else:
        typer.echo("- We averaged template means (trim did not apply due to fewer than 5 templates).")
    typer.echo("- Confidence came from resampling templates first, then replicates (cluster bootstrap in logit space).")
    if is_stable is not None:
        if is_stable:
            typer.echo("- The estimate is stable under the CI-width rule; paraphrase spread is "+("low" if (stab and stab >= 0.7) else "moderate")+".")
        else:
            typer.echo("- The estimate is NOT stable under the CI-width rule. Consider increasing K (more templates) before R.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

