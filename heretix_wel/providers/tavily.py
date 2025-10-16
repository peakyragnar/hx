from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Union

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

    def _parse_timestamp(self, value: Union[str, int, float, None]) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except (OverflowError, ValueError):
                return None
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if not raw:
            return None
        iso_guess = raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(iso_guess)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
        known_formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S %z",
        ]
        for fmt in known_formats:
            try:
                dt = datetime.strptime(raw, fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _extract_timestamp(self, item: dict) -> Optional[datetime]:
        def iter_candidates() -> Iterable[Union[str, int, float, None]]:
            keys = (
                "published_date",
                "published_time",
                "published",
                "date",
                "created_at",
                "updated_at",
                "time",
            )
            for key in keys:
                yield item.get(key)
            for extra_key in ("extra", "extra_info", "metadata"):
                extra = item.get(extra_key)
                if isinstance(extra, dict):
                    for key in keys:
                        yield extra.get(key)
            for key in ("published_date", "published"):
                nested = item.get("source") if isinstance(item.get("source"), dict) else None
                if isinstance(nested, dict):
                    yield nested.get(key)

        for candidate in iter_candidates():
            dt = self._parse_timestamp(candidate)
            if dt is not None:
                return dt.astimezone(timezone.utc)
        return None

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
            published_at = self._extract_timestamp(item)
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
