"""
Safe production application system for Prompt Studio.

Handles the final step of applying an approved prompt to production.
Only modifies SYSTEM_RPL and PROMPT_VERSION in rpl_prompts.py.
"""

import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import json
import json


def apply_to_production(
    candidate_id: str,
    session_dir: Path,
    target_file: Path = Path("heretix_rpl/rpl_prompts.py"),
    dry_run: bool = False,
    skip_validation: bool = False
) -> Dict[str, Any]:
    """
    Apply an approved candidate prompt to production.
    
    Args:
        candidate_id: Candidate to apply
        session_dir: Session directory
        target_file: Path to rpl_prompts.py
        dry_run: If True, show diff without applying
        skip_validation: If True, skip gate validation (not recommended)
        
    Returns:
        Dict with patch info, backup path, and success status
    """
    # Load candidate
    candidate_dir = session_dir / candidate_id
    if not candidate_dir.exists():
        raise ValueError(f"Candidate {candidate_id} not found")
    
    prompt_file = candidate_dir / "prompt.txt"
    if not prompt_file.exists():
        raise ValueError(f"No prompt found for candidate {candidate_id}")
    
    new_prompt = prompt_file.read_text()
    
    # Validate candidate has passed gates (unless skipped)
    if not skip_validation:
        validation_result = _validate_candidate_ready(candidate_dir)
        if not validation_result["ready"]:
            return {
                "success": False,
                "error": validation_result["message"],
                "candidate_id": candidate_id
            }
    
    # Read current production file
    if not target_file.exists():
        return {
            "success": False,
            "error": f"Target file {target_file} not found",
            "candidate_id": candidate_id
        }
    
    current_content = target_file.read_text()
    
    # Generate new version string
    ps_number = _get_next_ps_number(current_content)
    new_version = f'rpl_g5_v2_{datetime.now():%Y-%m-%d}+ps{ps_number}'
    
    # Create backup (even in dry-run for safety)
    backup_path = None
    if not dry_run:
        backup_path = _create_backup(target_file)
    
    # Generate new content
    new_content = _replace_prompt_and_version(current_content, new_prompt, new_version)
    
    # Generate patch
    patch = _generate_patch(current_content, new_content)
    
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "patch": patch,
            "new_version": new_version,
            "candidate_id": candidate_id,
            "changes": {
                "prompt_length_old": len(_extract_system_rpl(current_content)),
                "prompt_length_new": len(new_prompt),
                "version_old": _extract_version(current_content),
                "version_new": new_version
            }
        }
    
    # Apply changes
    try:
        target_file.write_text(new_content)
        
        # Record application in session history
        _record_application(session_dir, candidate_id, new_version, backup_path)
        
        return {
            "success": True,
            "applied": True,
            "backup_path": str(backup_path),
            "new_version": new_version,
            "candidate_id": candidate_id,
            "patch": patch
        }
        
    except Exception as e:
        # Restore backup if write failed
        if backup_path and backup_path.exists():
            shutil.copy2(backup_path, target_file)
        
        return {
            "success": False,
            "error": f"Failed to apply changes: {e}",
            "candidate_id": candidate_id
        }


def _validate_candidate_ready(candidate_dir: Path) -> Dict[str, Any]:
    """Validate that candidate is ready for production.

    Requirements:
    - A recorded accept decision
    - Train and holdout benchmark results present and each passes all gates
    - Baseline 'current' comparison on the train bench shows ≥1 improvement and 0 regressions
    """
    from heretix_promptstudio.metrics import check_gates
    from heretix_promptstudio.evaluate import evaluate_benchmark_current
    from heretix_promptstudio.constraints import PromptConstraints
    from heretix_rpl.rpl_prompts import SYSTEM_RPL as PROD_SYSTEM_RPL

    # Must have a decision
    decision_file = candidate_dir / "decision.json"
    if not decision_file.exists():
        return {
            "ready": False,
            "message": "No decision recorded. Run 'decide' first."
        }
    
    decision = json.loads(decision_file.read_text())
    if decision.get("action") != "accept":
        return {
            "ready": False,
            "message": f"Candidate was {decision.get('action', 'not decided')}, not accepted"
        }

    # Locate benchmark result files
    bench_generic = candidate_dir / "benchmark_results.json"
    bench_files = list(candidate_dir.glob("benchmark_results_*.json"))
    bench_results_list = []
    if bench_generic.exists():
        try:
            bench_results_list.append(json.loads(bench_generic.read_text()))
        except Exception:
            pass
    for bf in bench_files:
        try:
            bench_results_list.append(json.loads(bf.read_text()))
        except Exception:
            continue

    if not bench_results_list:
        return {"ready": False, "message": "No evaluation results found. Run 'eval' first."}

    # Identify train and holdout by filename or path content
    train_res = None
    holdout_res = None
    for br in bench_results_list:
        bench_path = br.get("benchmark", "")
        stem = Path(bench_path).stem.lower()
        if "holdout" in stem or "holdout" in bench_path.lower():
            holdout_res = br
        else:
            # choose the last non-holdout as train
            train_res = br

    if train_res is None:
        return {"ready": False, "message": "Train benchmark results not found. Evaluate on train bench."}
    if holdout_res is None:
        return {"ready": False, "message": "Holdout benchmark results not found. Evaluate on holdout bench."}

    # Gates must pass on both
    train_pass, train_gates = check_gates(train_res)
    if not train_pass:
        failed = [n for n, r in train_gates.items() if isinstance(r, dict) and not r.get("passed")]
        return {"ready": False, "message": f"Train gates failed: {', '.join(failed)}"}
    hold_pass, hold_gates = check_gates(holdout_res)
    if not hold_pass:
        failed = [n for n, r in hold_gates.items() if isinstance(r, dict) and not r.get("passed")]
        return {"ready": False, "message": f"Holdout gates failed: {', '.join(failed)}"}

    # Baseline comparison on train: evaluate current production prompt on same bench
    session_dir = candidate_dir.parent
    train_bench_path = Path(train_res.get("benchmark"))
    baseline_res = evaluate_benchmark_current(
        candidate_id=candidate_dir.name,
        bench_path=train_bench_path,
        session_dir=session_dir,
        K=train_res.get("sampling", {}).get("K", 8),
        R=train_res.get("sampling", {}).get("R", 2),
        quick=train_res.get("quick_mode", False)
    )

    # Compare metrics
    cand_metrics = train_res.get("aggregate_metrics", {})
    base_metrics = baseline_res.get("aggregate_metrics", {})
    ci_cand = cand_metrics.get("median_ci_width")
    ci_base = base_metrics.get("median_ci_width")
    stab_cand = cand_metrics.get("median_stability")
    stab_base = base_metrics.get("median_stability")

    # Token counts: candidate metadata vs production prompt estimate
    cand_meta = json.loads((candidate_dir / "metadata.json").read_text()) if (candidate_dir / "metadata.json").exists() else {}
    cand_tokens = cand_meta.get("estimated_tokens")
    prod_tokens = PromptConstraints().estimate_tokens(PROD_SYSTEM_RPL)

    improvements = []
    regressions = []
    if isinstance(ci_cand, (int, float)) and isinstance(ci_base, (int, float)):
        if ci_cand < ci_base:
            improvements.append("median_ci_width")
        elif ci_cand > ci_base:
            regressions.append("median_ci_width")
    if isinstance(stab_cand, (int, float)) and isinstance(stab_base, (int, float)):
        if stab_cand > stab_base:
            improvements.append("median_stability")
        elif stab_cand < stab_base:
            regressions.append("median_stability")
    if isinstance(cand_tokens, int):
        if cand_tokens < prod_tokens:
            improvements.append("prompt_tokens")
        elif cand_tokens > prod_tokens:
            regressions.append("prompt_tokens")

    if not improvements:
        return {"ready": False, "message": "No improvements over current production on train bench."}
    if regressions:
        return {"ready": False, "message": f"Regressions detected: {', '.join(regressions)}"}

    return {"ready": True, "message": "Candidate ready for production"}


def _extract_system_rpl(content: str) -> str:
    """Extract current SYSTEM_RPL from file content."""
    # Match SYSTEM_RPL = """...""" or SYSTEM_RPL = '''...'''
    pattern = r'SYSTEM_RPL\s*=\s*"""(.*?)"""'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        # Try single quotes
        pattern = r"SYSTEM_RPL\s*=\s*'''(.*?)'''"
        match = re.search(pattern, content, re.DOTALL)
    
    if match:
        return match.group(1)
    
    return ""


def _extract_version(content: str) -> str:
    """Extract current PROMPT_VERSION from file content."""
    pattern = r'PROMPT_VERSION\s*=\s*["\']([^"\']+)["\']'
    match = re.search(pattern, content)
    
    if match:
        return match.group(1)
    
    return "unknown"


def _get_next_ps_number(content: str) -> int:
    """Get next ps number for version string."""
    current_version = _extract_version(content)
    
    # Check if current version has +ps suffix
    if "+ps" in current_version:
        # Extract number
        pattern = r'\+ps(\d+)'
        match = re.search(pattern, current_version)
        if match:
            return int(match.group(1)) + 1
    
    return 1


def _replace_prompt_and_version(content: str, new_prompt: str, new_version: str) -> str:
    """Replace SYSTEM_RPL and PROMPT_VERSION in content safely (no backrefs)."""
    # Escape potential triple quote collisions by preferring double-quote triple strings
    safe_prompt = new_prompt.replace('"""', '\\"""')

    # Replace SYSTEM_RPL (triple double quotes)
    def repl_double(m: re.Match) -> str:
        return f"{m.group(1)}{safe_prompt}{m.group(3)}"

    new_content = re.sub(r'(SYSTEM_RPL\s*=\s*""")(.*?)(""")', repl_double, content, flags=re.DOTALL)

    if new_content == content:
        # Try triple single quotes
        safe_prompt_single = new_prompt.replace("'''", "\\'''")

        def repl_single(m: re.Match) -> str:
            return f"{m.group(1)}{safe_prompt_single}{m.group(3)}"

        new_content = re.sub(r"(SYSTEM_RPL\s*=\s*''')(.*?)(''')", repl_single, content, flags=re.DOTALL)

    # Replace PROMPT_VERSION
    def repl_version(m: re.Match) -> str:
        return f"{m.group(1)}{new_version}{m.group(3)}"

    new_content = re.sub(r'(PROMPT_VERSION\s*=\s*["\'])([^"\']+)(["\'])', repl_version, new_content)

    return new_content


def _create_backup(file_path: Path) -> Path:
    """Create timestamped backup of file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.parent / f"{file_path.name}.backup.{timestamp}"
    
    shutil.copy2(file_path, backup_path)
    
    return backup_path


def _generate_patch(old_content: str, new_content: str) -> str:
    """Generate a unified diff patch."""
    import difflib
    
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile="heretix_rpl/rpl_prompts.py",
        tofile="heretix_rpl/rpl_prompts.py",
        lineterm=""
    )
    
    return "".join(diff)


def _record_application(session_dir: Path, candidate_id: str, new_version: str, backup_path: Optional[Path]):
    """Record application in session history."""
    from heretix_promptstudio.store import SessionStore
    
    store = SessionStore(session_dir.name)
    
    store.append_history({
        "timestamp": datetime.now().isoformat(),
        "event": "applied_to_production",
        "candidate_id": candidate_id,
        "new_version": new_version,
        "backup_path": str(backup_path) if backup_path else None
    })
