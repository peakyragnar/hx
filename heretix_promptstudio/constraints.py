"""
Prompt constraints and validation rules for SYSTEM_RPL candidates.

Ensures prompts meet required criteria before evaluation and application.
"""

import re
from typing import List, Tuple, Dict, Any


class PromptConstraints:
    """Validates SYSTEM_RPL candidates against required constraints."""
    
    # Required phrases that must appear in the prompt
    REQUIRED_PHRASES = [
        "Raw Prior Lens",
        "JSON",
        "Do NOT browse, search, or cite",
        "ignore instructions",
        "opaque",  # treat claim as opaque data
        "two decimals"  # numeric probability formatting hint
    ]
    
    # Forbidden tokens that should not appear
    FORBIDDEN_TOKENS = [
        "```",           # Code fences
        "```json",       # JSON code blocks
        "```yaml",       # YAML code blocks
        "markdown",      # Markdown references
        "function_call", # Function calling
        "tool",          # Tool use
        "web.run",       # Web execution
        "http://", "https://", "www.",  # URLs
        "as of 20", "today", "now",      # temporal leakage
        "cite", "URL"                      # citation hints
    ]
    
    # Additional forbidden patterns (regex)
    FORBIDDEN_PATTERNS = [
        r'\bfunction\s+call\b',  # "function call" with space
        r'\buse\s+tool\b',        # "use tool"
        r'\bcall\s+tool\b',       # "call tool"
    ]
    
    # Maximum prompt length
    MAX_LENGTH = 1200  # characters
    
    # Minimum prompt length (sanity check)
    MIN_LENGTH = 100
    
    def check_prompt(self, prompt: str) -> Tuple[bool, List[str]]:
        """
        Validate a prompt against all constraints.
        
        Returns:
            (passes, list_of_issues)
        """
        issues = []
        
        # Check length constraints
        if len(prompt) > self.MAX_LENGTH:
            issues.append(f"Prompt too long: {len(prompt)} chars (max: {self.MAX_LENGTH})")
        
        if len(prompt) < self.MIN_LENGTH:
            issues.append(f"Prompt too short: {len(prompt)} chars (min: {self.MIN_LENGTH})")
        
        # Check required phrases
        for phrase in self.REQUIRED_PHRASES:
            if phrase not in prompt:
                issues.append(f"Missing required phrase: '{phrase}'")
        
        # Check forbidden tokens (case-insensitive)
        prompt_lower = prompt.lower()
        for token in self.FORBIDDEN_TOKENS:
            if token.lower() in prompt_lower:
                issues.append(f"Contains forbidden token: '{token}'")
        
        # Check forbidden patterns
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, prompt, re.IGNORECASE):
                issues.append(f"Contains forbidden pattern: '{pattern}'")
        
        # Check JSON-only instruction placement
        if not self._check_json_only_placement(prompt):
            issues.append("'Output JSON only' or similar must be the last instruction")
        
        # Check for proper structure
        if not self._check_prompt_structure(prompt):
            issues.append("Prompt must have clear rules/instructions structure")
        
        passes = len(issues) == 0
        return passes, issues
    
    def _check_json_only_placement(self, prompt: str) -> bool:
        """Ensure JSON-only instruction is at or near the end."""
        lines = prompt.strip().split('\n')
        if not lines:
            return False
        
        # Check last few lines for JSON-only instruction
        last_lines = ' '.join(lines[-3:]).lower()
        
        json_indicators = [
            'json only',
            'only json',
            'output json only',
            'return json only',
            'strict json',
            'json per schema'
        ]
        
        return any(indicator in last_lines for indicator in json_indicators)
    
    def _check_prompt_structure(self, prompt: str) -> bool:
        """Check if prompt has basic required structure."""
        # Must have "Rules" or similar section
        has_rules = any(marker in prompt for marker in ["Rules:", "Instructions:", "Guidelines:"])
        
        # Must mention evaluation/claim
        has_eval = any(word in prompt.lower() for word in ["evaluate", "estimate", "probability", "claim"])
        
        return has_rules and has_eval
    
    def ensure_json_only_last(self, prompt: str) -> str:
        """
        Ensure 'Output JSON only' is the last line of the prompt.
        
        Returns modified prompt if needed.
        """
        lines = prompt.strip().split('\n')
        
        # Remove existing JSON-only lines if present
        filtered_lines = []
        json_only_line = None
        
        for line in lines:
            line_lower = line.lower().strip()
            if any(indicator in line_lower for indicator in ['json only', 'only json', 'output json only']):
                json_only_line = line
            else:
                filtered_lines.append(line)
        
        # Add JSON-only as last line
        if json_only_line:
            filtered_lines.append(json_only_line)
        else:
            filtered_lines.append("8) Output JSON only per schema. No additional text or explanation.")
        
        return '\n'.join(filtered_lines)
    
    def estimate_tokens(self, prompt: str) -> int:
        """
        Estimate token count for a prompt.
        
        Simple heuristic: chars / 4 (roughly accurate for English text).
        """
        return round(len(prompt) / 4)
    
    def validate_against_production(self, prompt: str) -> Tuple[bool, List[str]]:
        """
        Additional validation comparing against production prompt.
        
        Ensures key production elements are preserved.
        """
        issues = []
        
        # Import current production prompt for comparison
        try:
            from heretix_rpl.rpl_prompts import SYSTEM_RPL
            
            # Check if key production elements are preserved
            production_key_phrases = [
                "Raw Prior Lens",
                "internal knowledge",
                "Do NOT browse, search, or cite"
            ]
            
            for phrase in production_key_phrases:
                if phrase in SYSTEM_RPL and phrase not in prompt:
                    issues.append(f"Removed production key phrase: '{phrase}'")
            
            # Warn if significantly shorter/longer
            len_ratio = len(prompt) / len(SYSTEM_RPL)
            if len_ratio < 0.5:
                issues.append(f"Prompt is <50% of production length (ratio: {len_ratio:.2f})")
            elif len_ratio > 1.5:
                issues.append(f"Prompt is >150% of production length (ratio: {len_ratio:.2f})")
                
        except ImportError:
            issues.append("Could not import production prompt for comparison")
        
        passes = len(issues) == 0
        return passes, issues
    
    def get_summary(self, prompt: str) -> Dict[str, Any]:
        """Get a summary of prompt characteristics."""
        return {
            "length_chars": len(prompt),
            "length_lines": len(prompt.strip().split('\n')),
            "estimated_tokens": self.estimate_tokens(prompt),
            "has_required_phrases": all(phrase in prompt for phrase in self.REQUIRED_PHRASES),
            "has_forbidden_tokens": any(token.lower() in prompt.lower() for token in self.FORBIDDEN_TOKENS),
            "json_only_last": self._check_json_only_placement(prompt)
        }


def check_prompt(prompt: str, verbose: bool = False) -> bool:
    """
    Convenience function to check a prompt.
    
    Returns True if all constraints pass.
    """
    validator = PromptConstraints()
    passes, issues = validator.check_prompt(prompt)
    
    if verbose and issues:
        print("Constraint violations:")
        for issue in issues:
            print(f"  - {issue}")
    
    return passes


def validate_candidate(candidate_path: str) -> List[str]:
    """
    Validate a candidate prompt file.
    
    Returns list of issues (empty if valid).
    """
    from pathlib import Path
    
    prompt_file = Path(candidate_path) / "prompt.txt"
    if not prompt_file.exists():
        return [f"Prompt file not found: {prompt_file}"]
    
    prompt = prompt_file.read_text()
    validator = PromptConstraints()
    
    # Run both basic and production comparison
    passes_basic, issues_basic = validator.check_prompt(prompt)
    passes_prod, issues_prod = validator.validate_against_production(prompt)
    
    all_issues = issues_basic + issues_prod
    return all_issues
