from __future__ import annotations

import pytest

from heretix.provider.telemetry import LLMTelemetry
from heretix_wel import evaluate_wel
from heretix_wel.evaluate_wel import _chunk_docs
from heretix_wel.scoring import WELSchemaError


class FakeRetriever:
    def __init__(self, docs):
        self._docs = docs

    def search(self, query: str, k: int, recency_days=None):  # pragma: no cover - simple fake
        return self._docs[:k]


class FakeDoc:
    def __init__(self, url: str, title: str):
        self.url = url
        self.title = title
        self.snippet = "snippet"
        self.domain = "example.com"
        self.published_at = None
        self.published_method = None
        self.published_confidence = 0.0
        self.page_text = None


@pytest.fixture(autouse=True)
def _patch_retriever(monkeypatch: pytest.MonkeyPatch):
    docs = [FakeDoc(url=f"https://example.com/doc{i}", title=f"Doc {i}") for i in range(4)]
    monkeypatch.setattr(
        "heretix_wel.evaluate_wel.make_retriever", lambda provider: FakeRetriever(docs)
    )
    monkeypatch.setattr("heretix_wel.evaluate_wel.enrich_docs_with_publish_dates", lambda docs, **_: None)
    monkeypatch.setenv("WEL_MAX_CHARS", "1000")
    yield


@pytest.fixture
def _patch_call(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "stance_prob_true": 0.6,
        "stance_label": "supports",
        "support_bullets": ["support"],
        "oppose_bullets": ["oppose"],
        "notes": ["note"],
    }
    warnings = ["json_repaired_simple"]
    telemetry = LLMTelemetry(provider="openai", logical_model="gpt-5", api_model="gpt-5")
    monkeypatch.setattr(
        "heretix_wel.evaluate_wel.call_wel_once",
        lambda bundle, model=None: (payload, warnings, "hash", telemetry),
    )
    return payload


def test_evaluate_wel_basic(_patch_call):
    result = evaluate_wel.evaluate_wel(claim="test claim", k_docs=2, replicates=1, seed=1)
    assert "p" in result
    assert result["metrics"]["n_docs"] == 2
    assert len(result["replicates"]) == 1
    rep = result["replicates"][0]
    assert rep.p_web == 0.6
    assert rep.support_bullets == ["support"]
    assert rep.stance_label == "supports"
    assert result["warning_counts"]["json_repaired_simple"] == 1
    assert len(result["telemetry"]) == 1
    assert result["telemetry"][0]["provider"] == "openai"


def test_evaluate_wel_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "heretix_wel.evaluate_wel.call_wel_once",
        lambda bundle, model=None: (_ for _ in ()).throw(WELSchemaError(["schema_validation_failed"])),
    )
    result = evaluate_wel.evaluate_wel(claim="test claim", k_docs=1, replicates=1, seed=2)
    rep = result["replicates"][0]
    assert rep.p_web == 0.5  # fallback probability on error
    assert rep.json_valid is False
    assert result["warning_counts"]["schema_validation_failed"] == 1
    assert result.get("telemetry") == []


def test_chunk_docs_balances_remainder():
    docs = [FakeDoc(url=f"https://example.com/{i}", title=f"Doc {i}") for i in range(5)]
    chunks = _chunk_docs(docs, replicates=3)
    seen = {doc.url for chunk in chunks for doc in chunk}
    assert seen == {f"https://example.com/{i}" for i in range(5)}


def test_tavily_rate_limiter_invoked(monkeypatch: pytest.MonkeyPatch, _patch_call):
    called = {"count": 0}

    def fake_acquire():
        called["count"] += 1

    monkeypatch.setattr("heretix_wel.evaluate_wel._TAVILY_RATE_LIMITER.acquire", fake_acquire)
    evaluate_wel.evaluate_wel(claim="rate limit test", k_docs=2, replicates=1, seed=4)
    assert called["count"] == 1
