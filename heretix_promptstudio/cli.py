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
    from heretix_promptstudio.store import SessionStore
    from heretix_promptstudio.propose import PromptProposer
    
    typer.echo(f"[propose] Creating new candidate with notes: {notes}")
    
    # Create or load session
    store = SessionStore(session_id=session)
    typer.echo(f"Session: {store.session_id}")
    
    # Create proposer and candidate
    proposer = PromptProposer(store.session_dir)
    candidate_id = proposer.create_candidate(notes)
    
    # Load candidate info for display
    candidate_data = proposer.load_candidate(candidate_id)
    metadata = candidate_data.get("metadata", {})
    
    typer.echo(f"\n✅ Created candidate: {candidate_id}")
    typer.echo(f"   Prompt length: {metadata.get('prompt_length', 'unknown')} chars")
    typer.echo(f"   Estimated tokens: {metadata.get('estimated_tokens', 'unknown')}")
    
    if metadata.get("constraint_issues"):
        typer.echo("\n⚠️  Constraint issues:")
        for issue in metadata["constraint_issues"]:
            typer.echo(f"   - {issue}")
    else:
        typer.echo("   ✅ All constraints pass")
    
    typer.echo(f"\nNext: Run 'heretix-pstudio eval --candidate {candidate_id} --bench <benchmark.yaml>'")


@app.command()
def eval(
    candidate: str = typer.Option(..., help="Candidate ID (e.g., cand_001)"),
    bench: Path = typer.Option(..., help="Path to benchmark YAML file"),
    quick: bool = typer.Option(False, help="Quick mode (K=5, R=1) - not for production"),
    k: Optional[int] = typer.Option(None, help="Override K (paraphrase slots)"),
    r: Optional[int] = typer.Option(None, help="Override R (replicates)")
):
    """Evaluate a candidate on a benchmark."""
    from heretix_promptstudio.store import get_current_session, SessionStore
    from heretix_promptstudio.evaluate import evaluate_benchmark
    from heretix_promptstudio.metrics import check_gates
    
    typer.echo(f"[eval] Evaluating candidate {candidate} on benchmark {bench}")
    
    if quick:
        typer.echo("⚠️  Quick mode enabled (K=5, R=1) - results not suitable for production")
        k = k or 5
        r = r or 1
    else:
        k = k or 8
        r = r or 2
    
    typer.echo(f"Parameters: K={k}, R={r}")
    
    # Find session containing this candidate
    session = get_current_session()
    if not session:
        # Try to find session by candidate
        for sess_info in SessionStore.list_sessions():
            try:
                store = SessionStore(sess_info["session_id"])
                if (store.session_dir / candidate).exists():
                    session = store
                    break
            except:
                continue
    
    if not session:
        typer.echo(f"Error: Could not find candidate {candidate}", err=True)
        raise typer.Exit(1)
    
    try:
        # Run evaluation
        typer.echo(f"Using session: {session.session_id}")
        typer.echo("Starting evaluation (this may take a few minutes)...")
        
        results = evaluate_benchmark(
            candidate_id=candidate,
            bench_path=bench,
            session_dir=session.session_dir,
            K=k,
            R=r,
            quick=quick
        )
        
        # Check gates
        all_pass, gates = check_gates(results)
        
        # Display summary
        metrics = results.get("aggregate_metrics", {})
        typer.echo(f"\n✅ Evaluation complete!")
        typer.echo(f"   Claims evaluated: {metrics.get('n_claims_evaluated', 0)}")
        typer.echo(f"   Median CI width: {metrics.get('median_ci_width', 'N/A'):.3f}")
        typer.echo(f"   Median stability: {metrics.get('median_stability', 'N/A'):.3f}")
        typer.echo(f"   JSON validity: {metrics.get('json_validity_rate', 'N/A'):.1%}")
        
        if all_pass:
            typer.echo("\n✅ All gates PASS")
        else:
            typer.echo("\n❌ Some gates FAILED")
        
        typer.echo(f"\nNext: Run 'heretix-pstudio explain --candidate {candidate}' for detailed analysis")
        
    except Exception as e:
        typer.echo(f"Error during evaluation: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def explain(
    candidate: str = typer.Option(..., help="Candidate ID"),
    compare: Optional[str] = typer.Option("current", help="Compare against (current/another candidate)")
):
    """Generate scorecard and recommendations for a candidate."""
    from heretix_promptstudio.store import get_current_session, SessionStore
    from heretix_promptstudio.explain import ExplainEngine
    
    typer.echo(f"[explain] Generating scorecard for {candidate}")
    
    if compare:
        typer.echo(f"Comparing against: {compare}")
    
    # Find session containing this candidate
    session = get_current_session()
    if not session:
        for sess_info in SessionStore.list_sessions():
            try:
                store = SessionStore(sess_info["session_id"])
                if (store.session_dir / candidate).exists():
                    session = store
                    break
            except:
                continue
    
    if not session:
        typer.echo(f"Error: Could not find candidate {candidate}", err=True)
        raise typer.Exit(1)
    
    try:
        engine = ExplainEngine()
        scorecard = engine.generate_scorecard(candidate, session.session_dir, baseline=compare)
        formatted = engine.format_scorecard(scorecard)
        typer.echo(formatted)
        
    except Exception as e:
        typer.echo(f"Error generating scorecard: {e}", err=True)
        raise typer.Exit(1)


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