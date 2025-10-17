from __future__ import annotations

from datetime import datetime, timezone

import pytest

from heretix_wel.providers.tavily import TavilyRetriever


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):  # pragma: no cover
        pass

    def json(self):
        return self._payload


@pytest.fixture
def tavily(monkeypatch: pytest.MonkeyPatch) -> TavilyRetriever:
    monkeypatch.setenv("TAVILY_API_KEY", "dummy")
    retriever = TavilyRetriever(api_key="dummy", timeout=1.0)
    return retriever


def test_tavily_timestamp_parsing(monkeypatch: pytest.MonkeyPatch, tavily: TavilyRetriever):
    payload = {
        "results": [
            {
                "url": "https://example.com/x",
                "title": "Example",
                "content": "content",
                "published_date": "2025-10-05T12:34:56Z",
            }
        ]
    }
    monkeypatch.setattr("requests.post", lambda *_, **__: DummyResponse(payload))
    docs = tavily.search("query", k=1)
    assert len(docs) == 1
    assert docs[0].published_at == datetime(2025, 10, 5, 12, 34, 56, tzinfo=timezone.utc)


def test_tavily_handles_missing_key(monkeypatch: pytest.MonkeyPatch, tavily: TavilyRetriever):
    payload = {"results": [{"url": "https://example.com/y", "title": "Y", "content": ""}]}
    monkeypatch.setattr("requests.post", lambda *_, **__: DummyResponse(payload))
    docs = tavily.search("query", k=1)
    assert docs[0].published_at is None