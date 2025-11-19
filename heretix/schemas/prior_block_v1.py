from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PriorBlockV1(BaseModel):
    """Aggregate statistics for the model-prior (RPL) lens."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prob_true: float = Field(..., ge=0.0, le=1.0)
    ci_lo: float = Field(..., ge=0.0, le=1.0)
    ci_hi: float = Field(..., ge=0.0, le=1.0)
    width: float = Field(..., ge=0.0)
    stability: float = Field(..., ge=0.0)
    compliance_rate: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_ci_bounds(self) -> "PriorBlockV1":
        if self.ci_lo > self.ci_hi:
            raise ValueError("ci_lo must be <= ci_hi")
        if not (self.ci_lo <= self.prob_true <= self.ci_hi):
            raise ValueError("prob_true must lie within [ci_lo, ci_hi]")
        return self


__all__ = ["PriorBlockV1"]
