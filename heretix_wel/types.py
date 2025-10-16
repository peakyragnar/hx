from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple


@dataclass
class Doc:
    """Represents a retrieved document snippet."""

    url: str
    title: str
    snippet: str
    domain: str
    published_at: Optional[datetime]


@dataclass
class WELReplicate:
    """Single Web-Informed replicate evaluation."""

    replicate_idx: int
    docs: List[Doc]
    p_web: float
    support_bullets: List[str]
    oppose_bullets: List[str]
    notes: List[str]
    json_valid: bool


@dataclass
class WELResult:
    """Aggregated Web-Informed result including provenance."""

    p: float
    ci95: Tuple[float, float]
    replicates: List[WELReplicate]
    metrics: Dict[str, float]
    provenance: Dict[str, object]
