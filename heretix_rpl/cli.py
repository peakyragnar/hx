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
    model: str = typer.Option("gpt-4o", help="OpenAI model id"),
    k: int = typer.Option(5, help="Number of paraphrases to bag"),
    seed: int = typer.Option(42, help="Optional seed (if provider supports)"),
    out: Path = typer.Option(Path("runs/rpl_run.json"), help="Output JSON file")
):
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        typer.echo("ERROR: OPENAI_API_KEY not set (set in env or .env)", err=True)
        raise typer.Exit(1)

    out.parent.mkdir(parents=True, exist_ok=True)
    result = evaluate_rpl(claim_text=claim, model=model, k=k, seed=seed)
    out.write_text(json.dumps(result, indent=2))
    typer.echo(f"Wrote {out}  p_RPL={result['aggregates']['prob_true_rpl']:.3f}  "
               f"var(logit)={result['aggregates']['logit_variance']:.4f}")

def main():
    app()

if __name__ == "__main__":
    main()