from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional

import requests
import tldextract

from ..snippets import normalize_snippet_text
from ..types import Doc


class TavilyRetriever:
    """Adapter for the Tavily API."""

    def __init__(self, api_key: Optional[str] = None, timeout: float = 15.0):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY is required for Tavily retrieval")
        self.timeout = timeout

    def _domain(self, url: str) -> str:
        parts = tldextract.extract(url or "")
        return ".".join(filter(None, (parts.domain, parts.suffix)))

    def search(self, query: str, k: int, recency_days: Optional[int] = None) -> List[Doc]:
        payload = {"query": query, "max_results": int(k), "api_key": self.api_key}
        if recency_days is not None:
            payload["days"] = max(1, int(recency_days))
            payload["search_depth"] = "advanced"
        response = requests.post("https://api.tavily.com/search", json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get("results", [])[:k]:
            url = item.get("url") or ""
            title = (item.get("title") or "").strip()
            snippet_raw = item.get("content") or item.get("snippet") or ""
            snippet = normalize_snippet_text(snippet_raw)[:1200]
            published_at = None
            published = item.get("published_date")
            if published:
                try:
                    published_at = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(timezone.utc)
                except ValueError:
                    published_at = None
            results.append(
                Doc(
                    url=url,
                    title=title[:300],
                    snippet=snippet,
                    domain=self._domain(url),
                    published_at=published_at,
                )
            )
        return results
