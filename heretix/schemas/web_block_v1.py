from __future__ import annotations

from typing import Any, Optional, Dict, List

from pydantic import BaseModel, ConfigDict, Field, model_validator

_STRENGTH_PATTERN = r"^(weak|moderate|strong)$"


class WebEvidenceStats(BaseModel):
    """Summary statistics describing the retrieved evidence set."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    n_docs: Optional[int] = Field(default=None, ge=0)
    n_domains: Optional[int] = Field(default=None, ge=0)
    median_age_days: Optional[float] = Field(default=None, ge=0.0)


class WebBlockV1(BaseModel):
    """Aggregated metrics for the Web-Informed Lens."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prob_true: float = Field(..., ge=0.0, le=1.0)
    ci_lo: float = Field(..., ge=0.0, le=1.0)
    ci_hi: float = Field(..., ge=0.0, le=1.0)
    evidence_strength: str = Field(..., pattern=_STRENGTH_PATTERN)
    resolved: Optional[bool] = None
    resolved_truth: Optional[bool] = None
    resolved_reason: Optional[str] = None
    resolved_citations: List[Dict[str, Any]] = Field(default_factory=list)
    support: Optional[int] = Field(default=None, ge=0)
    contradict: Optional[int] = Field(default=None, ge=0)
    domains: Optional[int] = Field(default=None, ge=0)
    evidence: Optional[WebEvidenceStats] = None
    resolved_debug_votes: Optional[Any] = None

    @model_validator(mode="after")
    def _check_ci_bounds(self) -> "WebBlockV1":
        if self.ci_lo > self.ci_hi:
            raise ValueError("ci_lo must be <= ci_hi")
        if not (self.ci_lo <= self.prob_true <= self.ci_hi):
            raise ValueError("prob_true must lie within [ci_lo, ci_hi]")
        return self


__all__ = ["WebBlockV1", "WebEvidenceStats"]
