from __future__ import annotations

from typing import List, Optional

from .types import Doc


class Retriever:
    """Minimal retrieval interface."""

    def search(self, query: str, k: int, recency_days: Optional[int] = None) -> List[Doc]:
        raise NotImplementedError


def make_retriever(provider: str, **kwargs) -> Retriever:
    name = (provider or "").lower()
    if name == "tavily":
        from .providers.tavily import TavilyRetriever

        return TavilyRetriever(**kwargs)
    raise ValueError(f"Unknown retrieval provider: {provider}")
