"""
CLI Entry Point for Heretix Raw Prior Lens (RPL) Evaluator

Command-line interface for running RPL evaluations with argument parsing and validation.
Handles configuration, calls evaluation engine, and displays formatted results.
Supports JSON output and environment variable overrides for all parameters.
"""
import os                                                    # Access environment variables
import json                                                  # Write results to JSON file
import typer                                                 # Modern CLI framework
from dotenv import load_dotenv                               # Load .env file variables
from pathlib import Path                                     # Handle file paths
from heretix_rpl.rpl_eval import evaluate_rpl               # Main evaluation function
from heretix_rpl.orchestrator import auto_rpl               # Adaptive controller
from heretix_rpl.inspect import summarize_run               # Inspection utility
from heretix_rpl.monitor import run_bench, compare_to_baseline, write_jsonl  # Drift monitor
from heretix_rpl.summarize import summarize_jsonl                             # Summaries
from heretix_rpl.constants import (
    GATE_CI_WIDTH_MAX_DEFAULT,
    GATE_STABILITY_MIN_DEFAULT,
    GATE_IMBALANCE_MAX_DEFAULT,
)

app = typer.Typer(help="Heretix Raw Prior Lens (RPL) evaluator")  # Create CLI app

@app.command()                                               # Register main command
def rpl(
    claim: str = typer.Option(..., help="Canonical claim text"),                    # Required claim input
    model: str = typer.Option("gpt-5", help="Model ID (gpt-5, gpt-5-nano, gpt-4o)"), # Model selection
    k: int = typer.Option(7, help="Number of paraphrases (K)"),                     # Paraphrase slots
    r: int = typer.Option(3, help="Replicates per paraphrase (R) - for GPT-5 only"), # Replicates per slot
    seed: int = typer.Option(None, help="Optional seed (GPT-4 only)"),              # Legacy seed option
    out: Path = typer.Option(Path("runs/rpl_run.json"), help="Output JSON file"),   # Output file path
    agg: str = typer.Option("clustered", help="Aggregator: clustered | simple")     # Aggregation method
):
    load_dotenv()                                            # Load environment variables from .env
    if not os.getenv("OPENAI_API_KEY"):                      # Check for required API key
        typer.echo("ERROR: OPENAI_API_KEY not set (set in env or .env)", err=True)  # Show error message
        raise typer.Exit(1)                                  # Exit with error code

    out.parent.mkdir(parents=True, exist_ok=True)            # Create output directory if needed
    
    # Show sampling info for GPT-5
    if model.startswith("gpt-5"):                            # Check if using GPT-5
        typer.echo(f"Running GPT-5 with K={k} paraphrases × R={r} replicates = {k*r} samples")  # Show sampling plan
    
    result = evaluate_rpl(claim_text=claim, model=model, k=k, seed=seed, r=r, agg=agg)  # Run evaluation
    out.write_text(json.dumps(result, indent=2))             # Save results to JSON file
    
    # Display results based on model type
    if model.startswith("gpt-5"):                            # GPT-5 results display
        aggs = result['aggregates']                          # Get aggregated results
        typer.echo(f"Wrote {out}")                           # Confirm file written
        typer.echo(f"  p_RPL={aggs['prob_true_rpl']:.3f}  "  # Show probability estimate
                   f"CI95=[{aggs['ci95'][0]:.3f}, {aggs['ci95'][1]:.3f}]  "  # Show confidence interval
                   f"stability={aggs['stability_score']:.3f}")  # Show stability score
        if not aggs['is_stable']:                            # Check stability flag
            width = result['aggregation']['stability_width']         # Get stability threshold from config
            # Check if threshold was overridden via environment
            env_override = os.getenv("HERETIX_RPL_STABILITY_WIDTH")
            source = f" (env: HERETIX_RPL_STABILITY_WIDTH)" if env_override else " (default)"
            typer.echo(f"  ⚠️  WARNING: Estimate is UNSTABLE (CI width > {width}{source})", err=True)  # Warn if unstable
    else:                                                    # Legacy model results display
        typer.echo(f"Wrote {out}  p_RPL={result['aggregates']['prob_true_rpl']:.3f}  "  # Show probability
                   f"var(logit)={result['aggregates'].get('logit_variance', 0.0):.4f}")  # Show variance

def main():                                                  # Main entry point function
    app()                                                    # Run the typer app

if __name__ == "__main__":                                   # Direct script execution
    main()                                                   # Call main function


# Additional commands

@app.command()
def auto(
    claim: str = typer.Option(..., help="Canonical claim text"),
    model: str = typer.Option("gpt-5"),
    start_k: int = typer.Option(8, help="Initial paraphrase slots"),
    start_r: int = typer.Option(2, help="Initial replicates per paraphrase"),
    max_k: int = typer.Option(16, help="Max paraphrase slots"),
    max_r: int = typer.Option(3, help="Max replicates"),
    ci_width_max: float = typer.Option(GATE_CI_WIDTH_MAX_DEFAULT, help="Gate: max CI width (0,1]"),
    stability_min: float = typer.Option(GATE_STABILITY_MIN_DEFAULT, help="Gate: min stability score (0,1]"),
    imbalance_max: float = typer.Option(GATE_IMBALANCE_MAX_DEFAULT, help="Gate: max template imbalance ratio (≥1)"),
    out: Path = typer.Option(Path("runs/rpl_auto.json"), help="Output JSON"),
):
    """Run adaptive RPL controller with templates-first policy."""
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        typer.echo("ERROR: OPENAI_API_KEY not set", err=True)
        raise typer.Exit(1)
    out.parent.mkdir(parents=True, exist_ok=True)
    typer.echo(f"Auto-RPL: {claim}")
    result = auto_rpl(
        claim=claim,
        model=model,
        start_K=start_k,
        start_R=start_r,
        max_K=max_k,
        max_R=max_r,
        ci_width_max=ci_width_max,
        stability_min=stability_min,
        imbalance_max=imbalance_max,
        verbose=True,
    )
    out.write_text(json.dumps(result, indent=2))
    f = result["final"]
    typer.echo(
        f"Final: K={f['K']} R={f['R']}  p_RPL={f['p_RPL']:.3f}  CI95=[{f['ci95'][0]:.3f},{f['ci95'][1]:.3f}]  width={f['ci_width']:.3f}  stability={f['stability_score']:.3f} ({f['stability_band']})"
    )
    for d in result["decision_log"]:
        reason = d.get("reason", "")
        typer.echo(f"  - {d['stage_id']}: {d['action']} :: {reason}")


@app.command()
def inspect(
    run: Path = typer.Option(..., help="Path to run JSON (stage snapshot or top-level run)"),
    show_ci_signal: bool = typer.Option(False, help="Show templates farthest from trimmed center (CI signal)"),
    show_replicates: bool = typer.Option(False, help="Show per-template replicate spreads"),
    limit: int = typer.Option(3, help="Limit entries shown in optional sections"),
):
    """Pretty-print per-template summary from a run JSON.

    Add --show-ci-signal to list templates with largest |delta_logit| from 20% trimmed center,
    and --show-replicates to show replicate probabilities with stdev/range per template.
    """
    typer.echo(
        summarize_run(
            str(run),
            show_ci_signal=show_ci_signal,
            show_replicates=show_replicates,
            limit=limit,
        )
    )


@app.command()
def monitor(
    bench: Path = typer.Option(Path("bench/sentinels.json"), help="Sentinel bench JSON"),
    model: str = typer.Option("gpt-5"),
    baseline: Path = typer.Option(None, help="Optional baseline JSONL to compare"),
    out: Path = typer.Option(Path("runs/monitor/monitor.jsonl"), help="Output JSONL path"),
    quick: bool = typer.Option(False, help="Quick mode (K=5,R=1) for faster runs"),
    limit: int = typer.Option(None, help="Limit number of claims to run"),
    verbose: bool = typer.Option(True, help="Print progress per claim"),
    append: bool = typer.Option(False, help="Append to output instead of overwrite"),
):
    """Run sentinel bench and stream drift flags to JSONL (with progress)."""
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        typer.echo("ERROR: OPENAI_API_KEY not set", err=True)
        raise typer.Exit(1)

    # Determine K/R
    K, R = (5, 1) if quick else (8, 2)
    typer.echo(f"Monitor: model={model} K={K} R={R} bench={bench}")

    # Load baseline map (optional)
    base_map = {}
    if baseline and baseline.exists():
        base_rows = [json.loads(line) for line in baseline.read_text().splitlines() if line.strip()]
        base_map = {r["claim"]: r for r in base_rows}

    # Prepare output
    out.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    bench_items = json.loads(bench.read_text())
    if limit is not None:
        bench_items = bench_items[:max(0, int(limit))]
    claim_list = [x["claim"] for x in bench_items]

    from heretix_rpl.monitor import run_bench_iter, compare_row_to_baseline
    with out.open(mode) as f:
        for row in run_bench_iter(str(bench), model=model, K=K, R=R, verbose=verbose, claims=claim_list):
            flagged = compare_row_to_baseline(row, base_map)
            f.write(json.dumps(flagged) + "\n")
            f.flush()
    typer.echo(f"Wrote {out}")


@app.command()
def summarize(
    file: Path = typer.Option(..., help="Path to JSONL produced by monitor"),
):
    """Summarize a monitor JSONL: means, counts, and widest-CI claims."""
    summary = summarize_jsonl(str(file))
    typer.echo(f"File: {summary['file']}")
    typer.echo(f"Rows: {summary['n_rows']}  Models: {', '.join(summary['models'])}  Versions: {', '.join(summary['prompt_versions'])}")
    typer.echo(
        f"Means → p: {summary['mean_p']:.3f}  ci_width: {summary['mean_ci_width']:.3f}  stability: {summary['mean_stability']:.3f}"
    )
    typer.echo(
        f"Counts → high(≥0.9): {summary['count_high_ge_0_9']}  low(≤0.1): {summary['count_low_le_0_1']}  mid(0.4–0.6): {summary['count_mid_0_4_to_0_6']}"
    )
    dc = summary['drift_counts']
    typer.echo(f"Drift flags → p: {dc['p']}  stability: {dc['stability']}  ci: {dc['ci']}")
    typer.echo("Widest CIs:")
    for w in summary['widest_ci']:
        typer.echo(f"  - {w['ci_width']:.3f}  {w['claim']}")
