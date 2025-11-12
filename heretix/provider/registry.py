from __future__ import annotations

from typing import Callable


_GROK_ALIASES = {
    "grok",
    "grok4",
    "grok-4",
    "grok-4-fast-reasoning",
    "grok-4-fast-non-reasoning",
    "grok-4-0709",
    "grok-beta",
    "grok-2-latest",
    "grok-3",
    "grok-3-mini",
    "grok-5",
    "grok5",
}


def get_scorer(model: str, use_mock: bool) -> Callable:
    """Return a provider-specific score_claim function for the given model.

    This indirection lets the RPL harness remain provider-agnostic while
    we add additional adapters (e.g., Grok, Gemini) without touching the
    estimator or pipeline logic.
    """
    if use_mock:
        from .mock import score_claim_mock as _score

        return _score

    # Normalize common aliases
    m = (model or "").strip().lower()
    if m in _GROK_ALIASES:
        from .grok_xai import score_claim as _score

        return _score

    # Default to OpenAI GPT-5 adapter
    from .openai_gpt5 import score_claim as _score

    return _score
