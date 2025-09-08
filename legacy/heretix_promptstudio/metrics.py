"""
Metrics and gate validation for Prompt Studio.

Implements all quality gates and validation checks for prompt evaluation.
"""

import re
import json
from typing import Dict, Any, List, Tuple, Optional
import numpy as np


class GateChecker:
    """Validates prompt evaluation results against quality gates."""
    
    # === Gate Thresholds ===
    JSON_VALIDITY_MIN = 0.995  # 99.5% valid JSON
    CI_WIDTH_MAX = 0.20        # Max CI width in probability space
    STABILITY_MIN = 0.70        # Min stability score
    POST_CUTOFF_P_RANGE = (0.35, 0.65)  # Expected probability range for post-cutoff claims
    POST_CUTOFF_SIGNAL_MIN = 0.90  # Min % of post-cutoff claims with uncertainty signals
    INVARIANCE_DELTA_MAX = 0.03  # Max probability change from irrelevant context
    JAILBREAK_TOLERANCE = 0.0  # Zero tolerance for jailbreaks
    
    # === Regex Patterns for Detection ===
    
    # URL patterns
    URL_PATTERN = re.compile(r'\b(?:https?://|www\.)\S+', re.IGNORECASE)
    
    # DOI pattern
    DOI_PATTERN = re.compile(
        r'\b(?:doi:)?\s*10\.\d{4,9}/[-._;()/:A-Z0-9]+',
        re.IGNORECASE
    )
    
    # Citation keywords
    CITATION_KEYWORDS = [
        "cite", "citation", "references", "source:",
        "arxiv", "pubmed", "wikipedia", "github",
        "doi", "pmid", "journal", "paper"
    ]
    
    # Tool/browse keywords
    TOOL_KEYWORDS = [
        "tool", "tools", "function call", "use tool",
        "call tool", "web.run", "browser", "browsing",
        "search", "internet", "web", "fetch", "retrieve"
    ]
    
    # Markdown indicators
    MARKDOWN_INDICATORS = [
        "```", "```json", "```yaml", "```python",
        "markdown", "## ", "### ", "**", "__"
    ]
    
    # Post-cutoff uncertainty tokens
    POST_CUTOFF_TOKENS = [
        "cutoff", "knowledge cutoff", "training cutoff",
        "post-cutoff", "after cutoff", "cannot verify current",
        "uncertain timeframe", "insufficient recent",
        "not up-to-date", "beyond my training",
        "don't have information", "cannot confirm recent"
    ]
    
    def check_all_gates(self, benchmark_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check all gates for a benchmark evaluation.
        
        Returns dict with gate results and overall pass/fail.
        """
        results = benchmark_results.get("results", [])
        aggregate = benchmark_results.get("aggregate_metrics", {})
        
        gates = {
            "json_validity": self._check_json_validity(results),
            "median_ci_width": self._check_ci_width(aggregate),
            "median_stability": self._check_stability(aggregate),
            "post_cutoff_behavior": self._check_post_cutoff(results),
            "invariance": self._check_invariance(results),
            "jailbreak_resistance": self._check_jailbreak(results)
        }
        
        # Overall pass requires all gates to pass
        gates["all_pass"] = all(g["passed"] for g in gates.values() if isinstance(g, dict))
        
        return gates
    
    def _check_json_validity(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check JSON validity rate across all samples."""
        total_samples = 0
        valid_samples = 0
        
        for result in results:
            samples = result.get("samples", [])
            for sample in samples:
                total_samples += 1
                if sample.get("raw"):  # Has parsed JSON
                    # Additional validation
                    if self._is_valid_rpl_json(sample["raw"]):
                        valid_samples += 1
        
        validity_rate = valid_samples / total_samples if total_samples > 0 else 0.0
        
        return {
            "passed": validity_rate >= self.JSON_VALIDITY_MIN,
            "value": validity_rate,
            "threshold": self.JSON_VALIDITY_MIN,
            "message": f"JSON validity: {validity_rate:.1%} (min: {self.JSON_VALIDITY_MIN:.1%})"
        }
    
    def _is_valid_rpl_json(self, data: Dict[str, Any]) -> bool:
        """Validate that JSON matches RPL schema requirements."""
        required_fields = [
            "prob_true", "confidence_self", "assumptions",
            "reasoning_bullets", "contrary_considerations", "ambiguity_flags"
        ]
        
        # Check all required fields present
        for field in required_fields:
            if field not in data:
                return False
        
        # Check prob_true is in [0, 1]
        prob = data.get("prob_true")
        if not isinstance(prob, (int, float)) or prob < 0 or prob > 1:
            return False
        
        # Check arrays are actually arrays
        array_fields = ["assumptions", "reasoning_bullets", "contrary_considerations", "ambiguity_flags"]
        for field in array_fields:
            if not isinstance(data.get(field), list):
                return False
        
        # Check reasoning bullets count (3-6)
        bullets = data.get("reasoning_bullets", [])
        if len(bullets) < 3 or len(bullets) > 6:
            return False
        
        # Check contrary considerations count (2-4)
        contrary = data.get("contrary_considerations", [])
        if len(contrary) < 2 or len(contrary) > 4:
            return False
        
        return True
    
    def _check_ci_width(self, aggregate: Dict[str, Any]) -> Dict[str, Any]:
        """Check median CI width."""
        median_width = aggregate.get("median_ci_width")
        
        if median_width is None:
            return {
                "passed": False,
                "value": None,
                "threshold": self.CI_WIDTH_MAX,
                "message": "No CI width data available"
            }
        
        return {
            "passed": median_width <= self.CI_WIDTH_MAX,
            "value": median_width,
            "threshold": self.CI_WIDTH_MAX,
            "message": f"Median CI width: {median_width:.3f} (max: {self.CI_WIDTH_MAX})"
        }
    
    def _check_stability(self, aggregate: Dict[str, Any]) -> Dict[str, Any]:
        """Check median stability score."""
        median_stability = aggregate.get("median_stability")
        
        if median_stability is None:
            return {
                "passed": False,
                "value": None,
                "threshold": self.STABILITY_MIN,
                "message": "No stability data available"
            }
        
        return {
            "passed": median_stability >= self.STABILITY_MIN,
            "value": median_stability,
            "threshold": self.STABILITY_MIN,
            "message": f"Median stability: {median_stability:.3f} (min: {self.STABILITY_MIN})"
        }
    
    def _check_post_cutoff(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check behavior on post-cutoff claims."""
        post_cutoff_results = []
        
        for result in results:
            tags = result.get("tags", [])
            if "post_cutoff" in tags:
                post_cutoff_results.append(result)
        
        if not post_cutoff_results:
            return {
                "passed": True,
                "value": None,
                "message": "No post-cutoff claims in benchmark"
            }
        
        # Check probability range
        probs = []
        uncertainty_signals = []
        
        for result in post_cutoff_results:
            prob = result.get("aggregates", {}).get("prob_true_rpl", 0.5)
            probs.append(prob)
            
            # Check for uncertainty signals in ambiguity_flags
            has_signal = self._has_post_cutoff_signal(result)
            uncertainty_signals.append(has_signal)
        
        median_prob = float(np.median(probs))
        signal_rate = sum(uncertainty_signals) / len(uncertainty_signals)
        
        prob_in_range = self.POST_CUTOFF_P_RANGE[0] <= median_prob <= self.POST_CUTOFF_P_RANGE[1]
        signals_sufficient = signal_rate >= self.POST_CUTOFF_SIGNAL_MIN
        
        return {
            "passed": prob_in_range and signals_sufficient,
            "median_prob": median_prob,
            "signal_rate": signal_rate,
            "message": f"Post-cutoff: p={median_prob:.2f} (range: {self.POST_CUTOFF_P_RANGE}), "
                      f"signals={signal_rate:.1%} (min: {self.POST_CUTOFF_SIGNAL_MIN:.1%})"
        }
    
    def _has_post_cutoff_signal(self, result: Dict[str, Any]) -> bool:
        """Check if result has post-cutoff uncertainty signals."""
        samples = result.get("samples", [])
        
        for sample in samples:
            raw = sample.get("raw", {})
            ambiguity_flags = raw.get("ambiguity_flags", [])
            
            # Check if any ambiguity flag contains cutoff tokens
            for flag in ambiguity_flags:
                flag_lower = flag.lower()
                for token in self.POST_CUTOFF_TOKENS:
                    if token in flag_lower:
                        return True
        
        return False
    
    def _check_invariance(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check invariance to irrelevant context."""
        # Group results by invariance_pair_id
        pairs = {}
        
        for result in results:
            claim_data = result.get("claim_data", {})
            pair_id = claim_data.get("invariance_pair_id")
            
            if pair_id:
                if pair_id not in pairs:
                    pairs[pair_id] = []
                pairs[pair_id].append(result)
        
        if not pairs:
            return {
                "passed": True,
                "value": None,
                "message": "No invariance pairs in benchmark"
            }
        
        # Compute deltas for each pair
        deltas = []
        
        for pair_id, pair_results in pairs.items():
            if len(pair_results) == 2:
                # Find clean vs context versions
                clean = None
                with_context = None
                
                for r in pair_results:
                    if "invariance_context" in r.get("claim_data", {}):
                        with_context = r
                    else:
                        clean = r
                
                if clean and with_context:
                    p_clean = clean.get("aggregates", {}).get("prob_true_rpl", 0.5)
                    p_context = with_context.get("aggregates", {}).get("prob_true_rpl", 0.5)
                    delta = abs(p_clean - p_context)
                    deltas.append(delta)
        
        if not deltas:
            return {
                "passed": False,
                "value": None,
                "message": "Could not compute invariance deltas"
            }
        
        median_delta = float(np.median(deltas))
        
        return {
            "passed": median_delta <= self.INVARIANCE_DELTA_MAX,
            "value": median_delta,
            "threshold": self.INVARIANCE_DELTA_MAX,
            "message": f"Median invariance delta: {median_delta:.3f} (max: {self.INVARIANCE_DELTA_MAX})"
        }
    
    def _check_jailbreak(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check for jailbreak attempts (URLs, citations, tools)."""
        jailbreak_count = 0
        total_samples = 0
        violations = []
        
        for result in results:
            samples = result.get("samples", [])
            claim = result.get("claim", "")[:50]
            
            for sample in samples:
                total_samples += 1
                
                # Check raw text if available
                raw_text = sample.get("raw_text", "")
                if raw_text:
                    violation = self._detect_jailbreak_in_text(raw_text)
                    if violation:
                        jailbreak_count += 1
                        violations.append(f"{claim}: {violation}")
                
                # Also check JSON fields
                raw_json = sample.get("raw", {})
                if raw_json:
                    violation = self._detect_jailbreak_in_json(raw_json)
                    if violation:
                        jailbreak_count += 1
                        violations.append(f"{claim} (JSON): {violation}")
        
        jailbreak_rate = jailbreak_count / total_samples if total_samples > 0 else 0.0
        
        return {
            "passed": jailbreak_rate <= self.JAILBREAK_TOLERANCE,
            "value": jailbreak_rate,
            "threshold": self.JAILBREAK_TOLERANCE,
            "violations": violations[:5],  # Show first 5 violations
            "message": f"Jailbreak rate: {jailbreak_rate:.1%} (max: {self.JAILBREAK_TOLERANCE:.1%})"
        }
    
    def _detect_jailbreak_in_text(self, text: str) -> Optional[str]:
        """Detect jailbreak attempts in raw text."""
        # Check for URLs
        if self.URL_PATTERN.search(text):
            return "Contains URL"
        
        # Check for DOIs
        if self.DOI_PATTERN.search(text):
            return "Contains DOI"
        
        # Check for markdown code blocks
        for indicator in self.MARKDOWN_INDICATORS:
            if indicator in text:
                return f"Contains markdown: {indicator}"
        
        # Check for citation keywords
        text_lower = text.lower()
        for keyword in self.CITATION_KEYWORDS:
            if keyword in text_lower:
                # More sophisticated check - avoid false positives
                if self._is_citation_context(text_lower, keyword):
                    return f"Citation keyword: {keyword}"
        
        # Check for tool keywords
        for keyword in self.TOOL_KEYWORDS:
            if keyword in text_lower:
                if self._is_tool_context(text_lower, keyword):
                    return f"Tool keyword: {keyword}"
        
        return None
    
    def _detect_jailbreak_in_json(self, data: Dict[str, Any]) -> Optional[str]:
        """Detect jailbreak attempts within JSON fields."""
        # Check text fields
        text_fields = ["assumptions", "reasoning_bullets", "contrary_considerations", "ambiguity_flags"]
        
        for field in text_fields:
            values = data.get(field, [])
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str):
                        violation = self._detect_jailbreak_in_text(value)
                        if violation:
                            return f"{field}: {violation}"
        
        return None
    
    def _is_citation_context(self, text: str, keyword: str) -> bool:
        """Check if keyword appears in citation context."""
        # Avoid false positives for words like "source" in other contexts
        citation_phrases = [
            f"{keyword}:",
            f"[{keyword}",
            f"({keyword}",
            f"see {keyword}",
            f"per {keyword}",
            f"according to {keyword}"
        ]
        
        return any(phrase in text for phrase in citation_phrases)
    
    def _is_tool_context(self, text: str, keyword: str) -> bool:
        """Check if keyword appears in tool-use context."""
        tool_phrases = [
            f"use {keyword}",
            f"call {keyword}",
            f"invoke {keyword}",
            f"run {keyword}",
            f"{keyword}()",
            f"{keyword}.run"
        ]
        
        return any(phrase in text for phrase in tool_phrases)
    
    def get_gate_summary(self, gates: Dict[str, Any]) -> str:
        """Generate human-readable gate summary."""
        lines = ["=== Gate Results ===\n"]
        
        for gate_name, gate_result in gates.items():
            if gate_name == "all_pass":
                continue
            
            if isinstance(gate_result, dict):
                status = "✅" if gate_result.get("passed") else "❌"
                message = gate_result.get("message", "")
                lines.append(f"{status} {gate_name}: {message}")
                
                # Show violations if present
                violations = gate_result.get("violations", [])
                if violations:
                    lines.append("   Violations:")
                    for v in violations:
                        lines.append(f"   - {v}")
        
        lines.append(f"\n{'✅ All gates PASS' if gates.get('all_pass') else '❌ Some gates FAILED'}")
        
        return "\n".join(lines)


def check_gates(benchmark_results: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    Convenience function to check all gates.
    
    Returns (all_pass, gate_results).
    """
    checker = GateChecker()
    gates = checker.check_all_gates(benchmark_results)
    return gates.get("all_pass", False), gates