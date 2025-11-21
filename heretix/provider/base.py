from __future__ import annotations

from typing import Protocol, Dict, Any, Optional, runtime_checkable


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


@runtime_checkable
class LLMProvider(Protocol):
    """High-level provider interface for bias runs.

    Existing RPL adapters (see `heretix/provider/registry.py`) already implement
    `score_claim`. A thin wrapper can adapt those functions into this protocol by
    composing a prompt string and extracting a minimal JSON-like payload:

        {"label": "true" | "false", "p_true": float}

    This protocol is defined ahead of wiring the fast-bias path so that both
    harness and API code can share a common type without changing provider
    implementations.
    """

    name: str

    def sample_prior(
        self,
        *,
        prompt: str,
        max_output_tokens: int,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:  # pragma: no cover - Protocol stub
        ...
