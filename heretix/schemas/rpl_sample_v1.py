from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._helpers import coerce_string_list

_LABEL_PATTERN = r"^(very_unlikely|unlikely|uncertain|likely|very_likely)$"


class Belief(BaseModel):
    """Belief summary for a single RPL sample."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prob_true: float = Field(..., ge=0.0, le=1.0)
    label: str = Field(..., pattern=_LABEL_PATTERN)


class Flags(BaseModel):
    """Quality-control flags for the sample."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    refused: bool = False
    off_topic: bool = False


class RPLSampleV1(BaseModel):
    """Canonical representation of a Raw Prior Lens sample."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    belief: Belief
    reasons: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)
    flags: Flags = Field(default_factory=Flags)

    @field_validator("reasons", "assumptions", "uncertainties", mode="before")
    @classmethod
    def _clean_string_lists(cls, value: object) -> List[str]:
        return coerce_string_list(value)


__all__ = ["Belief", "Flags", "RPLSampleV1"]
