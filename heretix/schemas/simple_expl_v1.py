from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._helpers import coerce_string_list


class SimpleExplV1(BaseModel):
    """Narrative summary shown in the UI."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    title: str
    body_paragraphs: List[str] = Field(default_factory=list)
    bullets: List[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _ensure_title(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("title must be a non-empty string")
        return value.strip()

    @field_validator("body_paragraphs", mode="before")
    @classmethod
    def _clean_paragraphs(cls, value: object) -> List[str]:
        cleaned = coerce_string_list(value, allow_empty=False)
        if not cleaned:
            raise ValueError("body_paragraphs must include at least one entry")
        return cleaned

    @field_validator("bullets", mode="before")
    @classmethod
    def _clean_bullets(cls, value: object) -> List[str]:
        return coerce_string_list(value)


__all__ = ["SimpleExplV1"]
