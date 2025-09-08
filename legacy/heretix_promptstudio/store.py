"""
Session store for Prompt Studio - manages persistence and history.

Handles session lifecycle, candidate storage, and decision tracking.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import hashlib


class SessionStore:
    """Manages prompt optimization sessions and persistence."""
    
    BASE_DIR = Path("runs/promptstudio")
    
    def __init__(self, session_id: Optional[str] = None):
        """
        Initialize session store.
        
        Args:
            session_id: Existing session ID or None to create new
        """
        self.BASE_DIR.mkdir(parents=True, exist_ok=True)
        
        if session_id:
            self.session_dir = self.BASE_DIR / session_id
            if not self.session_dir.exists():
                raise ValueError(f"Session {session_id} not found")
        else:
            self.session_dir = self._create_new_session()
        
        self.session_id = self.session_dir.name
        self.history_file = self.session_dir / "history.jsonl"
        self.config_file = self.session_dir / "config.json"
        
        # Load or create session config
        self.config = self._load_or_create_config()
        
    def _create_new_session(self) -> Path:
        """Create a new session directory with timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = f"session-{timestamp}"
        session_dir = self.BASE_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir
    
    def _load_or_create_config(self) -> Dict[str, Any]:
        """Load existing config or create new one."""
        if self.config_file.exists():
            return json.loads(self.config_file.read_text())
        
        # Create new config
        config = {
            "session_id": self.session_id,
            "created": datetime.now().isoformat(),
            "seed": self._get_or_create_seed(),
            "model": "gpt-5",
            "prompt_version": self._get_current_prompt_version(),
            "candidates_created": 0,
            "evaluations_run": 0,
            "status": "active"
        }
        
        self.config_file.write_text(json.dumps(config, indent=2))
        return config
    
    def _get_or_create_seed(self) -> int:
        """Get seed from environment or create deterministic one."""
        env_seed = os.getenv("HERETIX_RPL_SEED")
        if env_seed:
            return int(env_seed)
        
        # Create deterministic seed from session ID
        seed_bytes = hashlib.sha256(self.session_id.encode()).digest()
        return int.from_bytes(seed_bytes[:8], 'big') % (2**32)
    
    def _get_current_prompt_version(self) -> str:
        """Get current production prompt version."""
        try:
            from heretix_rpl.rpl_prompts import PROMPT_VERSION
            return PROMPT_VERSION
        except ImportError:
            return "unknown"
    
    def new_candidate(self) -> str:
        """
        Generate next candidate ID.
        
        Returns:
            candidate_id (e.g., "cand_001")
        """
        self.config["candidates_created"] += 1
        self._save_config()
        
        candidate_num = self.config["candidates_created"]
        return f"cand_{candidate_num:03d}"
    
    def save_candidate(self, candidate_id: str, data: Dict[str, Any]):
        """Save candidate data to its directory."""
        candidate_dir = self.session_dir / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        
        # Save different components
        if "prompt" in data:
            (candidate_dir / "prompt.txt").write_text(data["prompt"])
        
        if "diff" in data:
            (candidate_dir / "diff.md").write_text(data["diff"])
        
        if "metrics" in data:
            (candidate_dir / "metrics.json").write_text(
                json.dumps(data["metrics"], indent=2)
            )
        
        if "decision" in data:
            (candidate_dir / "decision.json").write_text(
                json.dumps(data["decision"], indent=2)
            )
        
        # Append to history
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "candidate_saved",
            "candidate_id": candidate_id,
            "data_keys": list(data.keys())
        }
        self.append_history(history_entry)
    
    def load_candidate(self, candidate_id: str) -> Dict[str, Any]:
        """Load all data for a candidate."""
        candidate_dir = self.session_dir / candidate_id
        
        if not candidate_dir.exists():
            raise ValueError(f"Candidate {candidate_id} not found in session {self.session_id}")
        
        data = {"candidate_id": candidate_id}
        
        # Load all available files
        if (candidate_dir / "prompt.txt").exists():
            data["prompt"] = (candidate_dir / "prompt.txt").read_text()
        
        if (candidate_dir / "diff.md").exists():
            data["diff"] = (candidate_dir / "diff.md").read_text()
        
        if (candidate_dir / "metrics.json").exists():
            data["metrics"] = json.loads((candidate_dir / "metrics.json").read_text())
        
        if (candidate_dir / "decision.json").exists():
            data["decision"] = json.loads((candidate_dir / "decision.json").read_text())
        
        if (candidate_dir / "metadata.json").exists():
            data["metadata"] = json.loads((candidate_dir / "metadata.json").read_text())
        
        # Load evaluation results if present
        eval_dir = candidate_dir / "eval"
        if eval_dir.exists():
            data["evaluations"] = {}
            for eval_file in eval_dir.glob("*.json"):
                claim_name = eval_file.stem
                data["evaluations"][claim_name] = json.loads(eval_file.read_text())
        
        return data
    
    def append_history(self, entry: Dict[str, Any]):
        """Append entry to session history (append-only log)."""
        with self.history_file.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Load full session history."""
        if not self.history_file.exists():
            return []
        
        history = []
        with self.history_file.open() as f:
            for line in f:
                if line.strip():
                    history.append(json.loads(line))
        
        return history
    
    def record_decision(self, candidate_id: str, action: str, feedback: Optional[str] = None):
        """Record accept/reject decision for a candidate."""
        decision = {
            "candidate_id": candidate_id,
            "action": action,
            "feedback": feedback,
            "timestamp": datetime.now().isoformat(),
            "decided_by": os.getenv("USER", "unknown")
        }
        
        # Save to candidate directory
        candidate_dir = self.session_dir / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        (candidate_dir / "decision.json").write_text(json.dumps(decision, indent=2))
        
        # Append to history
        self.append_history({
            "timestamp": decision["timestamp"],
            "event": "decision_recorded",
            "candidate_id": candidate_id,
            "action": action
        })
        
        return decision
    
    def list_candidates(self) -> List[Dict[str, Any]]:
        """List all candidates in session with summary info."""
        candidates = []
        
        for candidate_dir in sorted(self.session_dir.glob("cand_*")):
            candidate_id = candidate_dir.name
            
            summary = {
                "candidate_id": candidate_id,
                "created": None,
                "has_evaluation": (candidate_dir / "metrics.json").exists(),
                "has_decision": (candidate_dir / "decision.json").exists(),
                "decision": None
            }
            
            # Get metadata if available
            if (candidate_dir / "metadata.json").exists():
                metadata = json.loads((candidate_dir / "metadata.json").read_text())
                summary["created"] = metadata.get("created")
                summary["notes"] = metadata.get("notes")
            
            # Get decision if available
            if (candidate_dir / "decision.json").exists():
                decision = json.loads((candidate_dir / "decision.json").read_text())
                summary["decision"] = decision.get("action")
            
            candidates.append(summary)
        
        return candidates
    
    def get_accepted_candidates(self) -> List[str]:
        """Get list of accepted candidate IDs."""
        accepted = []
        
        for candidate in self.list_candidates():
            if candidate.get("decision") == "accept":
                accepted.append(candidate["candidate_id"])
        
        return accepted
    
    def _save_config(self):
        """Save updated config to file."""
        self.config_file.write_text(json.dumps(self.config, indent=2))
    
    @classmethod
    def list_sessions(cls) -> List[Dict[str, Any]]:
        """List all available sessions."""
        sessions = []
        
        if not cls.BASE_DIR.exists():
            return sessions
        
        for session_dir in sorted(cls.BASE_DIR.glob("session-*")):
            config_file = session_dir / "config.json"
            
            if config_file.exists():
                config = json.loads(config_file.read_text())
                sessions.append({
                    "session_id": session_dir.name,
                    "created": config.get("created"),
                    "status": config.get("status", "unknown"),
                    "candidates": config.get("candidates_created", 0),
                    "evaluations": config.get("evaluations_run", 0)
                })
        
        return sessions
    
    @classmethod
    def cleanup_old_sessions(cls, older_than_days: int = 30, dry_run: bool = True) -> List[str]:
        """
        Clean up sessions older than specified days.
        
        Returns list of deleted session IDs.
        """
        import shutil
        
        deleted = []
        cutoff = datetime.now() - timedelta(days=older_than_days)
        
        for session_dir in cls.BASE_DIR.glob("session-*"):
            config_file = session_dir / "config.json"
            
            if config_file.exists():
                config = json.loads(config_file.read_text())
                created = datetime.fromisoformat(config.get("created", datetime.now().isoformat()))
                
                if created < cutoff:
                    if not dry_run:
                        shutil.rmtree(session_dir)
                    deleted.append(session_dir.name)
        
        return deleted


def resume_session(session_id: str) -> SessionStore:
    """Resume an existing session."""
    return SessionStore(session_id=session_id)


def get_current_session() -> Optional[SessionStore]:
    """Get the most recent active session if exists."""
    sessions = SessionStore.list_sessions()
    
    # Find most recent active session
    active_sessions = [s for s in sessions if s.get("status") == "active"]
    
    if active_sessions:
        # Sort by created date
        active_sessions.sort(key=lambda s: s.get("created", ""), reverse=True)
        return SessionStore(session_id=active_sessions[0]["session_id"])
    
    return None