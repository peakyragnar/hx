from __future__ import annotations

from typing import Protocol, Dict, Any, runtime_checkable


@runtime_checkable
class RPLAdapter(Protocol):
    """Protocol for RPL provider adapters."""

    def score_claim(
        self,
        *,
        claim: str,
        system_text: str,
        user_template: str,
        paraphrase_text: str,
        model: str,
        max_output_tokens: int,
    ) -> Dict[str, Any]:  # pragma: no cover - Protocol stub
        ...
