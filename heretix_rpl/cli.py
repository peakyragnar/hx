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