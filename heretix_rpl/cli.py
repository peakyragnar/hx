import os
import json
import typer
from dotenv import load_dotenv
from pathlib import Path
from heretix_rpl.rpl_eval import evaluate_rpl

app = typer.Typer(help="Heretix Raw Prior Lens (RPL) evaluator")

@app.command()
def rpl(
    claim: str = typer.Option(..., help="Canonical claim text"),
    model: str = typer.Option("gpt-5", help="Model ID (gpt-5, gpt-5-nano, gpt-4o)"),
    k: int = typer.Option(7, help="Number of paraphrases (K)"),
    r: int = typer.Option(3, help="Replicates per paraphrase (R) - for GPT-5 only"),
    seed: int = typer.Option(None, help="Optional seed (GPT-4 only)"),
    out: Path = typer.Option(Path("runs/rpl_run.json"), help="Output JSON file")
):
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        typer.echo("ERROR: OPENAI_API_KEY not set (set in env or .env)", err=True)
        raise typer.Exit(1)

    out.parent.mkdir(parents=True, exist_ok=True)
    
    # Show sampling info for GPT-5
    if model.startswith("gpt-5"):
        typer.echo(f"Running GPT-5 with K={k} paraphrases × R={r} replicates = {k*r} samples")
    
    result = evaluate_rpl(claim_text=claim, model=model, k=k, seed=seed, r=r)
    out.write_text(json.dumps(result, indent=2))
    
    # Display results based on model type
    if model.startswith("gpt-5"):
        aggs = result['aggregates']
        typer.echo(f"Wrote {out}")
        typer.echo(f"  p_RPL={aggs['prob_true_rpl']:.3f}  "
                   f"CI95=[{aggs['ci95'][0]:.3f}, {aggs['ci95'][1]:.3f}]  "
                   f"stability={aggs['stability_score']:.3f}")
        if not aggs['is_stable']:
            typer.echo("  ⚠️  WARNING: Estimate is UNSTABLE (CI width > 0.2)", err=True)
    else:
        typer.echo(f"Wrote {out}  p_RPL={result['aggregates']['prob_true_rpl']:.3f}  "
                   f"var(logit)={result['aggregates'].get('logit_variance', 0.0):.4f}")

def main():
    app()

if __name__ == "__main__":
    main()