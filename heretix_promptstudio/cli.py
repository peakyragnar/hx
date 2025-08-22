"""
Heretix Prompt Studio CLI - Main entry point for prompt optimization.

Commands:
- propose: Create new SYSTEM_RPL candidate
- eval: Evaluate candidate on benchmark
- explain: Generate scorecard and recommendations
- decide: Accept/reject candidate with feedback
- apply: Apply approved candidate to production
- list: List all candidates in session
- show: Display candidate details
- compare: Compare candidates
- precheck: Validate candidate constraints
- resume: Resume previous session
"""

import typer
from pathlib import Path
from typing import Optional
from datetime import datetime
import json
import os

app = typer.Typer(
    help="Heretix Prompt Studio (Lite) - Iterative prompt optimization for SYSTEM_RPL",
    no_args_is_help=True
)

# Global session tracking
CURRENT_SESSION = None


@app.command()
def propose(
    notes: str = typer.Option(..., help="Description of proposed changes"),
    session: Optional[str] = typer.Option(None, help="Session ID (creates new if not specified)")
):
    """Create a new SYSTEM_RPL candidate with selected edits."""
    typer.echo(f"[propose] Creating new candidate with notes: {notes}")
    typer.echo(f"Session: {session or 'new'}")
    
    # TODO: Implement actual propose logic
    from heretix_promptstudio.propose import create_candidate
    # candidate_id = create_candidate(notes, session)
    # typer.echo(f"Created candidate: {candidate_id}")
    
    typer.echo("[Not yet implemented]")


@app.command()
def eval(
    candidate: str = typer.Option(..., help="Candidate ID (e.g., cand_001)"),
    bench: Path = typer.Option(..., help="Path to benchmark YAML file"),
    quick: bool = typer.Option(False, help="Quick mode (K=5, R=1) - not for production"),
    k: Optional[int] = typer.Option(None, help="Override K (paraphrase slots)"),
    r: Optional[int] = typer.Option(None, help="Override R (replicates)")
):
    """Evaluate a candidate on a benchmark."""
    typer.echo(f"[eval] Evaluating candidate {candidate} on benchmark {bench}")
    
    if quick:
        typer.echo("⚠️  Quick mode enabled (K=5, R=1) - results not suitable for production")
        k = k or 5
        r = r or 1
    else:
        k = k or 8
        r = r or 2
    
    typer.echo(f"Parameters: K={k}, R={r}")
    
    # TODO: Implement actual evaluation logic
    from heretix_promptstudio.evaluate import run_evaluation
    # results = run_evaluation(candidate, bench, k=k, r=r)
    # typer.echo(f"Evaluation complete. Median CI width: {results['median_ci_width']:.3f}")
    
    typer.echo("[Not yet implemented]")


@app.command()
def explain(
    candidate: str = typer.Option(..., help="Candidate ID"),
    compare: Optional[str] = typer.Option("current", help="Compare against (current/another candidate)")
):
    """Generate scorecard and recommendations for a candidate."""
    typer.echo(f"[explain] Generating scorecard for {candidate}")
    
    if compare:
        typer.echo(f"Comparing against: {compare}")
    
    # TODO: Implement actual explanation logic
    from heretix_promptstudio.explain import generate_scorecard
    # scorecard = generate_scorecard(candidate, baseline=compare)
    # display_scorecard(scorecard)
    
    typer.echo("[Not yet implemented]")


@app.command()
def decide(
    candidate: str = typer.Option(..., help="Candidate ID"),
    action: str = typer.Option(..., help="Action: accept/reject"),
    feedback: Optional[str] = typer.Option(None, help="Structured feedback")
):
    """Record decision for a candidate."""
    if action not in ["accept", "reject"]:
        typer.echo("Error: action must be 'accept' or 'reject'", err=True)
        raise typer.Exit(1)
    
    typer.echo(f"[decide] Recording {action} for {candidate}")
    
    if feedback:
        typer.echo(f"Feedback: {feedback}")
    
    # TODO: Implement actual decision recording
    from heretix_promptstudio.store import record_decision
    # record_decision(candidate, action, feedback)
    
    typer.echo("[Not yet implemented]")


@app.command()
def apply(
    candidate: str = typer.Option(..., help="Candidate ID to apply"),
    dest: Path = typer.Option(Path("heretix_rpl/rpl_prompts.py"), help="Destination file"),
    dry_run: bool = typer.Option(False, help="Show diff without applying"),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation")
):
    """Apply an approved candidate to production (modifies rpl_prompts.py)."""
    typer.echo(f"[apply] Preparing to apply {candidate} to {dest}")
    
    if dry_run:
        typer.echo("DRY RUN - No changes will be made")
    
    # TODO: Implement actual apply logic
    from heretix_promptstudio.apply import apply_to_production
    # patch = apply_to_production(candidate, dest, dry_run=dry_run)
    
    if not dry_run and not yes:
        confirm = typer.confirm("This will modify production. Continue?")
        if not confirm:
            typer.echo("Aborted.")
            raise typer.Exit(0)
    
    typer.echo("[Not yet implemented]")


@app.command()
def list(
    session: Optional[str] = typer.Option(None, help="Session ID (current if not specified)"),
    verbose: bool = typer.Option(False, "-v", help="Show detailed information")
):
    """List all candidates in a session."""
    session = session or "current"
    typer.echo(f"[list] Candidates in session: {session}")
    
    # TODO: Implement actual listing logic
    from heretix_promptstudio.store import list_candidates
    # candidates = list_candidates(session)
    # for cand in candidates:
    #     display_candidate_summary(cand, verbose=verbose)
    
    typer.echo("[Not yet implemented]")


@app.command()
def show(
    candidate: str = typer.Option(..., help="Candidate ID"),
    section: Optional[str] = typer.Option(None, help="Section to show: prompt/diff/metrics/decision")
):
    """Display details of a specific candidate."""
    typer.echo(f"[show] Displaying {candidate}")
    
    if section:
        typer.echo(f"Section: {section}")
    
    # TODO: Implement actual show logic
    from heretix_promptstudio.store import load_candidate
    # data = load_candidate(candidate)
    # display_candidate_details(data, section=section)
    
    typer.echo("[Not yet implemented]")


@app.command()
def compare(
    candidate: str = typer.Option(..., help="Candidate ID"),
    bench: Path = typer.Option(..., help="Benchmark to compare on"),
    baseline: str = typer.Option("current", help="Baseline for comparison")
):
    """Compare candidate performance against baseline."""
    typer.echo(f"[compare] Comparing {candidate} vs {baseline} on {bench}")
    
    # TODO: Implement actual comparison logic
    from heretix_promptstudio.evaluate import compare_candidates
    # comparison = compare_candidates(candidate, baseline, bench)
    # display_comparison(comparison)
    
    typer.echo("[Not yet implemented]")


@app.command()
def precheck(
    candidate: str = typer.Option(..., help="Candidate ID")
):
    """Run constraint validation on a candidate."""
    typer.echo(f"[precheck] Validating constraints for {candidate}")
    
    # TODO: Implement actual precheck logic
    from heretix_promptstudio.constraints import validate_candidate
    # issues = validate_candidate(candidate)
    # if issues:
    #     typer.echo("Constraint violations found:")
    #     for issue in issues:
    #         typer.echo(f"  - {issue}")
    # else:
    #     typer.echo("✓ All constraints pass")
    
    typer.echo("[Not yet implemented]")


@app.command()
def resume(
    session: str = typer.Option(..., help="Session ID to resume")
):
    """Resume a previous session."""
    typer.echo(f"[resume] Resuming session: {session}")
    
    # TODO: Implement actual resume logic
    from heretix_promptstudio.store import resume_session
    # session_data = resume_session(session)
    # display_session_summary(session_data)
    
    global CURRENT_SESSION
    CURRENT_SESSION = session
    typer.echo(f"Session {session} is now active")
    
    typer.echo("[Not yet implemented - full functionality]")


@app.command()
def gc(
    older_than: int = typer.Option(30, help="Delete sessions older than N days"),
    dry_run: bool = typer.Option(True, help="Show what would be deleted without deleting")
):
    """Garbage collect old sessions."""
    typer.echo(f"[gc] Cleaning sessions older than {older_than} days")
    
    if dry_run:
        typer.echo("DRY RUN - No deletions will occur")
    
    # TODO: Implement actual garbage collection
    from heretix_promptstudio.store import cleanup_old_sessions
    # deleted = cleanup_old_sessions(older_than_days=older_than, dry_run=dry_run)
    # typer.echo(f"Cleaned up {len(deleted)} sessions")
    
    typer.echo("[Not yet implemented]")


def main():
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()