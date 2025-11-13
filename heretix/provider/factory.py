from __future__ import annotations

from typing import Dict, Any

from .base import RPLAdapter
from . import mock as _mock
from .registry import get_score_fn as _get_score_fn


class _LiveAdapter:
    name = "LIVE"

    def __init__(self, model: str) -> None:
        self._model = model

    def score_claim(
        self,
        *,
        claim: str,
        system_text: str,
        user_template: str,
        paraphrase_text: str,
        model: str,
        max_output_tokens: int,
    ) -> Dict[str, Any]:
        scorer = _get_score_fn(self._model or model)
        return scorer(
            claim=claim,
            system_text=system_text,
            user_template=user_template,
            paraphrase_text=paraphrase_text,
            model=model,
            max_output_tokens=max_output_tokens,
        )


class _MockAdapter:
    name = "MOCK"

    def score_claim(
        self,
        *,
        claim: str,
        system_text: str,
        user_template: str,
        paraphrase_text: str,
        model: str,
        max_output_tokens: int,
    ) -> Dict[str, Any]:
        return _mock.score_claim_mock(
            claim=claim,
            system_text=system_text,
            user_template=user_template,
            paraphrase_text=paraphrase_text,
            model=model,
            max_output_tokens=max_output_tokens,
        )


def get_rpl_adapter(*, provider_mode: str, model: str) -> RPLAdapter:
    """Return an adapter for the requested provider mode."""

    if (provider_mode or "").upper() == "MOCK":
        return _MockAdapter()  # type: ignore[return-value]
    return _LiveAdapter(model=model)  # type: ignore[return-value]
