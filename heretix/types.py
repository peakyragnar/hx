from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ModelBiasResult:
    """Per-model bias result for a single claim.

    This is the shape the harness will expose to CLI and API callers once
    the fast-bias path is wired up.
    """

    model: str
    p_rpl: float
    label: str
    explanation: str
    # Optional bag for additional diagnostics (counts, stability bands, etc.).
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """Canonical harness result for a single claim run.

    The harness will treat this as the DB-agnostic payload that:
      - CLI flows can serialize to JSON and/or log into SQLite.
      - API flows can pass to the web layer and persist into Postgres.
    """

    run_id: str
    claim: str
    profile: str
    models: List[ModelBiasResult]
    # Full RPL output JSON (prior/math-level details), including per-template
    # statistics and provenance needed for auditability.
    raw_rpl_output: Dict[str, Any]
    # Simple stage timings (e.g., sampling, aggregation, explanation) in ms.
    timings: Dict[str, float] = field(default_factory=dict)

