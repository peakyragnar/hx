from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CombinedBlockV1(BaseModel):
    """Final verdict that blends prior and web-informed signals."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prob_true: float = Field(..., ge=0.0, le=1.0)
    ci_lo: float = Field(..., ge=0.0, le=1.0)
    ci_hi: float = Field(..., ge=0.0, le=1.0)
    ci95: List[float] = Field(default_factory=list)
    label: str
    weight_prior: float = Field(..., ge=0.0, le=1.0)
    weight_web: float = Field(..., ge=0.0, le=1.0)
    resolved: Optional[bool] = None
    resolved_truth: Optional[bool] = None
    resolved_reason: Optional[str] = None
    resolved_citations: List[Dict[str, Any]] = Field(default_factory=list)
    support: Optional[float] = Field(default=None, ge=0.0)
    contradict: Optional[float] = Field(default=None, ge=0.0)
    domains: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_consistency(self) -> "CombinedBlockV1":
        if self.ci_lo > self.ci_hi:
            raise ValueError("ci_lo must be <= ci_hi")
        if not (self.ci_lo <= self.prob_true <= self.ci_hi):
            raise ValueError("prob_true must lie within [ci_lo, ci_hi]")
        if not math.isclose(self.weight_prior + self.weight_web, 1.0, rel_tol=1e-6, abs_tol=1e-6):
            raise ValueError("weight_prior + weight_web must sum to 1.0")
        object.__setattr__(self, "ci95", [self.ci_lo, self.ci_hi])
        return self


__all__ = ["CombinedBlockV1"]
