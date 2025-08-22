"""
Prompt proposal system for creating and editing SYSTEM_RPL candidates.

Handles interactive editing, diff generation, and constraint validation.
"""

import difflib
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import json

from heretix_promptstudio.constraints import PromptConstraints


class PromptProposer:
    """Manages creation and editing of prompt candidates."""
    
    def __init__(self, session_dir: Path):
        """Initialize with session directory."""
        self.session_dir = session_dir
        self.constraints = PromptConstraints()
        
    def get_current_production_prompt(self) -> str:
        """Load the current production SYSTEM_RPL."""
        try:
            from heretix_rpl.rpl_prompts import SYSTEM_RPL
            return SYSTEM_RPL
        except ImportError:
            # Fallback for testing
            return "You are the Raw Prior Lens for claim evaluation."
    
    def create_candidate(
        self,
        notes: str,
        base_prompt: Optional[str] = None,
        edits: Optional[List[str]] = None
    ) -> str:
        """
        Create a new candidate prompt.
        
        Args:
            notes: Description of changes
            base_prompt: Starting prompt (uses production if None)
            edits: List of specific edits to apply
            
        Returns:
            candidate_id (e.g., "cand_001")
        """
        # Get base prompt
        if base_prompt is None:
            base_prompt = self.get_current_production_prompt()
        
        # Apply edits if provided
        modified_prompt = self._apply_edits(base_prompt, edits or [])
        
        # Ensure JSON-only is last
        modified_prompt = self.constraints.ensure_json_only_last(modified_prompt)
        
        # Validate constraints
        passes, issues = self.constraints.check_prompt(modified_prompt)
        
        # Generate candidate ID
        candidate_id = self._next_candidate_id()
        
        # Create candidate directory
        candidate_dir = self.session_dir / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        
        # Save prompt
        (candidate_dir / "prompt.txt").write_text(modified_prompt)
        
        # Generate and save diff
        diff = self.generate_diff(base_prompt, modified_prompt)
        (candidate_dir / "diff.md").write_text(diff)
        
        # Save metadata
        metadata = {
            "candidate_id": candidate_id,
            "created": datetime.now().isoformat(),
            "notes": notes,
            "edits": edits or [],
            "constraints_passed": passes,
            "constraint_issues": issues,
            "prompt_length": len(modified_prompt),
            "estimated_tokens": self.constraints.estimate_tokens(modified_prompt)
        }
        (candidate_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
        
        return candidate_id
    
    def _apply_edits(self, prompt: str, edits: List[str]) -> str:
        """
        Apply a list of edits to a prompt.
        
        Edit types:
        - "shorten:10" - Reduce by 10%
        - "remove:phrase" - Remove specific phrase
        - "add:text" - Add text
        - "replace:old:new" - Replace text
        - "tighten_json" - Make JSON instruction more explicit
        - "add_opaque" - Add opacity instruction
        """
        result = prompt
        
        for edit in edits:
            if edit.startswith("shorten:"):
                percent = int(edit.split(":")[1])
                result = self._shorten_prompt(result, percent)
            
            elif edit.startswith("remove:"):
                phrase = edit[7:]
                result = result.replace(phrase, "")
            
            elif edit.startswith("add:"):
                text = edit[4:]
                # Add before final JSON instruction
                lines = result.split('\n')
                if self._is_json_instruction(lines[-1]):
                    lines.insert(-1, text)
                else:
                    lines.append(text)
                result = '\n'.join(lines)
            
            elif edit.startswith("replace:"):
                parts = edit.split(":", 2)
                if len(parts) == 3:
                    old, new = parts[1], parts[2]
                    result = result.replace(old, new)
            
            elif edit == "tighten_json":
                result = self._tighten_json_instruction(result)
            
            elif edit == "add_opaque":
                result = self._add_opaque_instruction(result)
        
        return result.strip()
    
    def _shorten_prompt(self, prompt: str, percent: int) -> str:
        """Shorten prompt by removing verbose elements."""
        lines = prompt.split('\n')
        
        # Identify removable lines (comments, examples, redundant instructions)
        removable_indices = []
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            # Mark as removable if it's a comment or redundant
            if (line_stripped.startswith('#') or 
                line_stripped.startswith('//') or
                'for example' in line_stripped.lower() or
                'e.g.' in line_stripped.lower()):
                removable_indices.append(i)
        
        # Remove percentage of removable lines
        to_remove = int(len(removable_indices) * (percent / 100))
        for i in removable_indices[:to_remove]:
            lines[i] = None
        
        # Filter out None entries
        lines = [line for line in lines if line is not None]
        
        return '\n'.join(lines)
    
    def _tighten_json_instruction(self, prompt: str) -> str:
        """Make JSON instruction more explicit and strict."""
        lines = prompt.split('\n')
        
        for i, line in enumerate(lines):
            if 'json' in line.lower() and 'output' in line.lower():
                lines[i] = "Output ONLY valid JSON matching the schema. No other text."
                break
        
        return '\n'.join(lines)
    
    def _add_opaque_instruction(self, prompt: str) -> str:
        """Add instruction for opaque/deterministic behavior."""
        lines = prompt.split('\n')
        
        # Find rules section
        for i, line in enumerate(lines):
            if 'Rules:' in line or 'Instructions:' in line:
                # Insert after rules header
                lines.insert(i + 1, "0) Be deterministic and opaque; avoid narrative or explanation.")
                break
        
        return '\n'.join(lines)
    
    def _is_json_instruction(self, line: str) -> bool:
        """Check if a line is a JSON output instruction."""
        indicators = ['json only', 'only json', 'output json', 'return json']
        line_lower = line.lower()
        return any(ind in line_lower for ind in indicators)
    
    def _next_candidate_id(self) -> str:
        """Generate the next candidate ID."""
        existing = list(self.session_dir.glob("cand_*"))
        if not existing:
            return "cand_001"
        
        # Find highest number
        numbers = []
        for path in existing:
            try:
                num = int(path.name.split("_")[1])
                numbers.append(num)
            except (IndexError, ValueError):
                continue
        
        next_num = max(numbers) + 1 if numbers else 1
        return f"cand_{next_num:03d}"
    
    def generate_diff(self, original: str, modified: str) -> str:
        """
        Generate a readable diff between original and modified prompts.
        
        Returns markdown-formatted diff.
        """
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile="production/SYSTEM_RPL",
            tofile="candidate/SYSTEM_RPL",
            lineterm=""
        )
        
        # Format as markdown
        output = ["# Prompt Diff\n\n", "```diff\n"]
        output.extend(diff)
        output.append("\n```\n")
        
        # Add summary statistics
        output.append("\n## Summary\n\n")
        output.append(f"- Original length: {len(original)} chars\n")
        output.append(f"- Modified length: {len(modified)} chars\n")
        output.append(f"- Change: {len(modified) - len(original):+d} chars ")
        output.append(f"({100 * (len(modified) - len(original)) / len(original):+.1f}%)\n")
        
        return ''.join(output)
    
    def load_candidate(self, candidate_id: str) -> Dict[str, Any]:
        """Load a candidate's data."""
        candidate_dir = self.session_dir / candidate_id
        
        if not candidate_dir.exists():
            raise ValueError(f"Candidate {candidate_id} not found")
        
        data = {
            "prompt": (candidate_dir / "prompt.txt").read_text(),
            "diff": (candidate_dir / "diff.md").read_text() if (candidate_dir / "diff.md").exists() else None,
            "metadata": json.loads((candidate_dir / "metadata.json").read_text())
                        if (candidate_dir / "metadata.json").exists() else {}
        }
        
        return data


def create_candidate(notes: str, session_dir: str, edits: Optional[List[str]] = None) -> str:
    """
    Convenience function to create a candidate.
    
    Returns candidate_id.
    """
    session_path = Path(session_dir) if session_dir else Path("runs/promptstudio/current")
    proposer = PromptProposer(session_path)
    return proposer.create_candidate(notes, edits=edits)