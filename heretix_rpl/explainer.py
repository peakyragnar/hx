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
from __future__ import annotations                           # Enable forward type references
import json                                                  # JSON parsing for run files
from pathlib import Path                                     # Path handling
import typer                                                 # CLI framework

app = typer.Typer(help="Explain a saved Heretix RPL run JSON in plain English")  # CLI application instance


def _fmt_pct(x: float) -> str:
    """Format float as 3-decimal percentage string."""          # Function purpose
    return f"{x:.3f}"                                           # Return formatted string


@app.command()                                                  # CLI command decorator
def explain(path: Path = typer.Argument(..., help="Path to RPL JSON output")) -> None:
    """Main command to explain an RPL run from JSON file."""   # Function purpose
    if not path.exists():                                       # Check file existence
        typer.echo(f"ERROR: File not found: {path}", err=True)  # Print error message
        raise typer.Exit(1)                                     # Exit with error code

    data = json.loads(path.read_text())                         # Load JSON data from file

    claim = data.get("claim")                                   # Extract claim text
    model = data.get("model")                                   # Extract model name
    prompt_version = data.get("prompt_version")                 # Extract prompt version
    sampling = data.get("sampling", {})                         # Extract sampling parameters
    agg = data.get("aggregates", {})                           # Extract aggregate results
    aggi = data.get("aggregation", {})                         # Extract aggregation metadata

    p = agg.get("prob_true_rpl")                               # Get RPL probability estimate
    ci = agg.get("ci95", [None, None])                         # Get 95% confidence interval
    ciw = agg.get("ci_width")                                  # Get CI width
    stab = agg.get("stability_score")                          # Get stability score
    stab_band = agg.get("stability_band")                      # Get stability band label
    is_stable = agg.get("is_stable")                           # Get stability boolean flag

    method = aggi.get("method")                                # Get aggregation method name
    B = aggi.get("B")                                          # Get bootstrap iterations
    center = aggi.get("center")                                # Get center method (trimmed/mean)
    trim = aggi.get("trim")                                    # Get trim percentage
    seed = aggi.get("bootstrap_seed")                          # Get deterministic seed
    n_templates = aggi.get("n_templates")                      # Get number of unique templates
    counts = aggi.get("counts_by_template", {})                # Get sample counts per template
    imb = aggi.get("imbalance_ratio")                          # Get template imbalance ratio
    tpl_iqr = aggi.get("template_iqr_logit")                   # Get template IQR in logit space

    # Header
    typer.echo("Heretix RPL Run Explanation\n=============================")  # Print explanation header
    if claim:                                                   # If claim exists
        typer.echo(f"Claim: {claim}")                          # Print claim text
    if model:                                                   # If model exists
        typer.echo(f"Model: {model}")                          # Print model name
    if prompt_version:                                          # If prompt version exists
        typer.echo(f"Prompt version: {prompt_version}")        # Print prompt version
    if sampling:                                                # If sampling parameters exist
        K = sampling.get("K"); R = sampling.get("R"); N = sampling.get("N")  # Extract K, R, N values
        typer.echo(f"Sampling: K={K}, R={R}, N={N}")          # Print sampling configuration

    # Aggregates
    typer.echo("\nAggregate Results:")                         # Print aggregates section header
    if p is not None and ci[0] is not None:                    # If probability and CI exist
        typer.echo(f"- p_RPL: {p:.3f}")                       # Print RPL probability estimate
        typer.echo(f"- CI95: [{ci[0]:.3f}, {ci[1]:.3f}] (width {ciw:.3f})")  # Print confidence interval
    if stab is not None:                                        # If stability score exists
        typer.echo(f"- Stability: {stab:.3f} (band: {stab_band}, is_stable={is_stable})")  # Print stability info

    # Method
    typer.echo("\nEstimator & Provenance:")                   # Print method section header
    typer.echo(f"- Method: {method}")                         # Print aggregation method
    typer.echo(f"- Center: {center} (trim={trim})  |  Bootstrap B={B}")  # Print center method and bootstrap info
    typer.echo(f"- Deterministic bootstrap_seed: {seed}")     # Print bootstrap seed for reproducibility

    # Diagnostics
    typer.echo("\nDiagnostics:")                              # Print diagnostics section header
    if n_templates is not None:                                # If template count exists
        typer.echo(f"- Unique templates: {n_templates}")      # Print number of templates
    if counts:                                                  # If template counts exist
        typer.echo(f"- Counts by template: {counts}")         # Print samples per template
    if imb is not None:                                         # If imbalance ratio exists
        typer.echo(f"- Imbalance ratio (max/min): {imb:.3f}") # Print template imbalance
    if tpl_iqr is not None:                                     # If template IQR exists
        typer.echo(f"- Template IQR (logit): {tpl_iqr:.4f}")  # Print template spread in logit space

    # Plain-English narrative
    typer.echo("\nNarrative:")                                # Print narrative section header
    typer.echo("- We asked the claim across multiple paraphrase templates; each template got equal weight.")  # Explain paraphrase weighting
    if n_templates and n_templates >= 5 and center == "trimmed":  # If enough templates for trimming
        typer.echo("- We dropped the most extreme two template means and averaged the middle ones (20% trimmed center).")  # Explain trimming
    else:                                                       # If fewer than 5 templates
        typer.echo("- We averaged template means (trim did not apply due to fewer than 5 templates).")  # Explain no trimming
    typer.echo("- Confidence came from resampling templates first, then replicates (cluster bootstrap in logit space).")  # Explain bootstrap method
    if is_stable is not None:                                   # If stability flag exists
        if is_stable:                                          # If estimate is stable
            typer.echo("- The estimate is stable under the CI-width rule; paraphrase spread is "+("low" if (stab and stab >= 0.7) else "moderate")+".")  # Explain stable result
        else:                                                   # If estimate is not stable
            typer.echo("- The estimate is NOT stable under the CI-width rule. Consider increasing K (more templates) before R.")  # Suggest improvements


def main() -> None:
    """Entry point function for CLI application."""            # Function purpose
    app()                                                       # Run typer CLI app


if __name__ == "__main__":                                     # If run as script
    main()                                                      # Call main function

