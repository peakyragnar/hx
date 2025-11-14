from __future__ import annotations

from pydantic import BaseModel


class LLMTelemetry(BaseModel):
    """Normalized telemetry emitted alongside provider adapter results."""

    provider: str
    logical_model: str
    api_model: str | None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cache_hit: bool = False


__all__ = ["LLMTelemetry"]

