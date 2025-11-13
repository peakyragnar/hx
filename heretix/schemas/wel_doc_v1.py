from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._helpers import coerce_string_list

_STANCE_PATTERN = r"^(supports|contradicts|mixed|irrelevant)$"


class WELDocV1(BaseModel):
    """Canonical structure for a single web-evidence snippet evaluation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    stance_prob_true: float = Field(..., ge=0.0, le=1.0)
    stance_label: str = Field(..., pattern=_STANCE_PATTERN)
    support_bullets: List[str] = Field(default_factory=list)
    oppose_bullets: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)

    @field_validator("support_bullets", "oppose_bullets", "notes", mode="before")
    @classmethod
    def _clean_string_lists(cls, value: object) -> List[str]:
        return coerce_string_list(value)


__all__ = ["WELDocV1"]
