"""
Explanation engine for Prompt Studio - generates scorecards and recommendations.

Provides actionable insights based on evaluation results.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from heretix_promptstudio.metrics import GateChecker


class ExplainEngine:
    """Generates scorecards and recommendations for prompt candidates."""
    
    def __init__(self):
        """Initialize explanation engine."""
        self.gate_checker = GateChecker()
    
    def generate_scorecard(
        self,
        candidate_id: str,
        session_dir: Path,
        baseline: Optional[str] = "current"
    ) -> Dict[str, Any]:
        """
        Generate comprehensive scorecard for a candidate.
        
        Args:
            candidate_id: Candidate to explain
            session_dir: Session directory
            baseline: What to compare against ("current" or another candidate ID)
            
        Returns:
            Scorecard with gates, improvements, regressions, and recommendations
        """
        # Load candidate data
        candidate_dir = session_dir / candidate_id
        
        if not candidate_dir.exists():
            raise ValueError(f"Candidate {candidate_id} not found")
        
        # Load benchmark results if available
        bench_results_file = candidate_dir / "benchmark_results.json"
        if not bench_results_file.exists():
            return {
                "error": "No evaluation results found. Run 'eval' first.",
                "candidate_id": candidate_id
            }
        
        bench_results = json.loads(bench_results_file.read_text())
        
        # Check gates
        gates = self.gate_checker.check_all_gates(bench_results)
        
        # Load baseline for comparison
        baseline_metrics = None
        if baseline == "current":
            baseline_metrics = self._get_production_baseline()
        elif baseline and baseline != candidate_id:
            baseline_metrics = self._load_candidate_metrics(session_dir / baseline)
        
        # Compute improvements and regressions
        improvements = []
        regressions = []
        
        if baseline_metrics:
            current_metrics = bench_results.get("aggregate_metrics", {})
            improvements, regressions = self._compare_metrics(current_metrics, baseline_metrics)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(gates, bench_results, session_dir)
        
        # Build scorecard
        scorecard = {
            "candidate_id": candidate_id,
            "gates": gates,
            "improvements": improvements,
            "regressions": regressions,
            "recommendations": recommendations,
            "summary": self._generate_summary(gates, improvements, regressions),
            "aggregate_metrics": bench_results.get("aggregate_metrics", {}),
            "sampling": bench_results.get("sampling", {})
        }
        
        return scorecard
    
    def _get_production_baseline(self) -> Dict[str, Any]:
        """Get baseline metrics from production (estimated)."""
        # These are typical production values - could be loaded from a config
        return {
            "median_ci_width": 0.22,  # Typical production value
            "median_stability": 0.65,  # Typical production value
            "json_validity_rate": 0.98,  # Typical production value
            "estimated_tokens": 300  # Estimate for current SYSTEM_RPL
        }
    
    def _load_candidate_metrics(self, candidate_dir: Path) -> Optional[Dict[str, Any]]:
        """Load metrics from another candidate."""
        bench_file = candidate_dir / "benchmark_results.json"
        
        if bench_file.exists():
            data = json.loads(bench_file.read_text())
            return data.get("aggregate_metrics", {})
        
        return None
    
    def _compare_metrics(
        self,
        current: Dict[str, Any],
        baseline: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        """Compare current metrics against baseline."""
        improvements = []
        regressions = []
        
        # CI width comparison
        if "median_ci_width" in current and "median_ci_width" in baseline:
            current_width = current["median_ci_width"]
            baseline_width = baseline["median_ci_width"]
            
            if current_width < baseline_width:
                delta = baseline_width - current_width
                improvements.append(f"CI width reduced by {delta:.3f} ({100*delta/baseline_width:.1f}%)")
            elif current_width > baseline_width:
                delta = current_width - baseline_width
                regressions.append(f"CI width increased by {delta:.3f} ({100*delta/baseline_width:.1f}%)")
        
        # Stability comparison
        if "median_stability" in current and "median_stability" in baseline:
            current_stab = current["median_stability"]
            baseline_stab = baseline["median_stability"]
            
            if current_stab > baseline_stab:
                delta = current_stab - baseline_stab
                improvements.append(f"Stability improved by {delta:.3f} ({100*delta/baseline_stab:.1f}%)")
            elif current_stab < baseline_stab:
                delta = baseline_stab - current_stab
                regressions.append(f"Stability decreased by {delta:.3f} ({100*delta/baseline_stab:.1f}%)")
        
        # JSON validity comparison
        if "json_validity_rate" in current and "json_validity_rate" in baseline:
            current_valid = current["json_validity_rate"]
            baseline_valid = baseline["json_validity_rate"]
            
            if current_valid > baseline_valid:
                delta = current_valid - baseline_valid
                improvements.append(f"JSON validity improved by {100*delta:.1f}%")
            elif current_valid < baseline_valid:
                delta = baseline_valid - current_valid
                regressions.append(f"JSON validity decreased by {100*delta:.1f}%")
        
        return improvements, regressions
    
    def _generate_recommendations(
        self,
        gates: Dict[str, Any],
        bench_results: Dict[str, Any],
        session_dir: Path
    ) -> List[str]:
        """Generate 3-5 actionable recommendations based on gate failures."""
        recommendations = []
        
        # Check each gate and generate specific recommendations
        
        # JSON validity
        json_gate = gates.get("json_validity", {})
        if not json_gate.get("passed"):
            validity_rate = json_gate.get("value", 0)
            if validity_rate < 0.90:
                recommendations.append("Critical: Add explicit 'Output ONLY valid JSON' as last instruction")
                recommendations.append("Remove any markdown formatting instructions")
            else:
                recommendations.append("Strengthen JSON-only instruction placement and clarity")
        
        # CI width
        ci_gate = gates.get("median_ci_width", {})
        if not ci_gate.get("passed"):
            width = ci_gate.get("value", 1.0)
            if width > 0.30:
                recommendations.append("Add more precise language to reduce ambiguity")
                recommendations.append("Consider adding 'Be deterministic and opaque' instruction")
            else:
                recommendations.append("Slightly tighten instructions to reduce CI width")
        
        # Stability
        stability_gate = gates.get("median_stability", {})
        if not stability_gate.get("passed"):
            stability = stability_gate.get("value", 0)
            if stability < 0.50:
                recommendations.append("Critical: Reduce paraphrase sensitivity by using neutral language")
                recommendations.append("Remove examples or specific phrasings that bias responses")
            else:
                recommendations.append("Improve cross-paraphrase consistency with clearer rules")
        
        # Post-cutoff behavior
        post_cutoff_gate = gates.get("post_cutoff_behavior", {})
        if post_cutoff_gate and not post_cutoff_gate.get("passed"):
            signal_rate = post_cutoff_gate.get("signal_rate", 0)
            if signal_rate < 0.50:
                recommendations.append("Add instruction to flag uncertainty for unverifiable claims")
        
        # Jailbreak resistance
        jailbreak_gate = gates.get("jailbreak_resistance", {})
        if not jailbreak_gate.get("passed"):
            violations = jailbreak_gate.get("violations", [])
            if violations:
                recommendations.append("Strengthen 'Do NOT browse, search, or cite' instruction")
                recommendations.append("Add 'No URLs or external references' explicitly")
        
        # Length optimization
        candidate_id = bench_results.get("candidate_id", "")
        candidate_dir = session_dir / candidate_id if candidate_id else None
        if candidate_dir and (candidate_dir / "metadata.json").exists():
            metadata_file = candidate_dir / "metadata.json"
            if metadata_file.exists():
                metadata = json.loads(metadata_file.read_text())
                est_tokens = metadata.get("estimated_tokens", 0)
                if est_tokens > 350:
                    recommendations.append(f"Consider shortening prompt (currently ~{est_tokens} tokens)")
        
        # Limit to 5 most important
        return recommendations[:5]
    
    def _generate_summary(
        self,
        gates: Dict[str, Any],
        improvements: List[str],
        regressions: List[str]
    ) -> Dict[str, Any]:
        """Generate executive summary."""
        # Count gate passes
        gate_results = [g for k, g in gates.items() 
                       if k != "all_pass" and isinstance(g, dict)]
        gates_passed = sum(1 for g in gate_results if g.get("passed"))
        gates_total = len(gate_results)
        
        # Determine status
        if gates.get("all_pass"):
            if improvements and not regressions:
                status = "READY TO APPLY"
                recommendation = "All gates pass with improvements. Recommend adoption."
            elif improvements and regressions:
                status = "REVIEW NEEDED"
                recommendation = "Gates pass but has regressions. Review trade-offs."
            else:
                status = "MARGINAL"
                recommendation = "Gates pass but no clear improvements. Consider iterating."
        else:
            status = "NOT READY"
            recommendation = f"Failed {gates_total - gates_passed}/{gates_total} gates. Address issues and re-evaluate."
        
        return {
            "status": status,
            "gates_passed": gates_passed,
            "gates_total": gates_total,
            "has_improvements": len(improvements) > 0,
            "has_regressions": len(regressions) > 0,
            "recommendation": recommendation
        }
    
    def format_scorecard(self, scorecard: Dict[str, Any]) -> str:
        """Format scorecard for display."""
        lines = []
        
        # Header
        lines.append(f"=== SCORECARD: {scorecard['candidate_id']} ===\n")
        
        # Summary
        summary = scorecard.get("summary", {})
        lines.append(f"Status: {summary.get('status', 'UNKNOWN')}")
        lines.append(f"Gates: {summary.get('gates_passed')}/{summary.get('gates_total')} passed")
        lines.append(f"Recommendation: {summary.get('recommendation')}\n")
        
        # Gate details
        lines.append("=== Gate Results ===")
        gates = scorecard.get("gates", {})
        for gate_name, gate_result in gates.items():
            if gate_name == "all_pass":
                continue
            if isinstance(gate_result, dict):
                status = "✅" if gate_result.get("passed") else "❌"
                message = gate_result.get("message", "")
                lines.append(f"{status} {gate_name}: {message}")
        
        # Improvements and regressions
        improvements = scorecard.get("improvements", [])
        if improvements:
            lines.append("\n=== Improvements ===")
            for imp in improvements:
                lines.append(f"✅ {imp}")
        
        regressions = scorecard.get("regressions", [])
        if regressions:
            lines.append("\n=== Regressions ===")
            for reg in regressions:
                lines.append(f"⚠️  {reg}")
        
        # Recommendations
        recommendations = scorecard.get("recommendations", [])
        if recommendations:
            lines.append("\n=== Recommendations ===")
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"{i}. {rec}")
        
        # Metrics
        metrics = scorecard.get("aggregate_metrics", {})
        if metrics:
            lines.append("\n=== Metrics ===")
            lines.append(f"Median CI width: {metrics.get('median_ci_width', 'N/A'):.3f}")
            lines.append(f"Median stability: {metrics.get('median_stability', 'N/A'):.3f}")
            lines.append(f"JSON validity: {metrics.get('json_validity_rate', 'N/A'):.1%}")
        
        return "\n".join(lines)


def generate_scorecard(candidate_id: str, session_dir: str, baseline: str = "current") -> str:
    """
    Convenience function to generate and format a scorecard.
    
    Returns formatted scorecard string.
    """
    engine = ExplainEngine()
    session_path = Path(session_dir)
    
    scorecard = engine.generate_scorecard(candidate_id, session_path, baseline)
    return engine.format_scorecard(scorecard)
