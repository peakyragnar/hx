import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB_PATH = Path("runs/api_test.sqlite").resolve()
TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ.setdefault("RPL_ALLOW_MOCK", "true")
os.environ.setdefault("RPL_MAX_PROMPT_CHARS", "2000")

_NOISE_VARS = [
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "XAI_API_KEY",
    "GROK_API_KEY",
    "HERETIX_GROK_MODEL",
    "HERETIX_GROK_REQUIRE_CONTEXT",
    "HERETIX_GROK_CONTEXT_MIN_ITEMS",
    "HERETIX_GROK_CONTEXT_MIN_WORDS",
    "HERETIX_GROK_MAX_ATTEMPTS",
    "HERETIX_XAI_RPS",
    "HERETIX_XAI_BURST",
    "HERETIX_ENABLE_GROK",
    "HERETIX_UI_DIRECT_PIPELINE",
]
for var in _NOISE_VARS:
    os.environ.pop(var, None)

from heretix.constants import SCHEMA_VERSION
from heretix.db.migrate import ensure_schema

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from api import usage
from api import main as api_main

from api.config import settings  # noqa: E402
from api.main import app  # noqa: E402
from api.schemas import RunResponse  # noqa: E402

settings.rpl_max_prompt_chars = 2000

ensure_schema(settings.database_url)

client = TestClient(app)


@pytest.fixture(autouse=True)
def stub_usage(monkeypatch: pytest.MonkeyPatch):
    plan = usage.UsagePlan("test", checks_allowed=5)

    def fake_state(session, user, *, anon_token=None):
        return usage.UsageState(
            plan=plan,
            checks_used=0,
            checks_allowed=plan.checks_allowed,
            remaining=plan.checks_allowed,
        )

    def fake_increment(session, user, state):
        return state.checks_used + 1

    monkeypatch.setattr(usage, "get_usage_state", fake_state)
    monkeypatch.setattr(usage, "increment_usage", fake_increment)
    monkeypatch.setattr(api_main, "get_usage_state", fake_state)
    monkeypatch.setattr(api_main, "increment_usage", fake_increment)
    yield


def test_run_check_mock_baseline_returns_runresponse():
    payload = {
        "claim": "API mock run bead",
        "mode": "baseline",
        "provider": "openai",
        "logical_model": "gpt5-default",
        "prompt_version": "rpl_g5_v2",
        "K": 4,
        "R": 1,
        "B": 200,
        "max_output_tokens": 128,
        "max_prompt_chars": 2000,
        "mock": True,
    }

    resp = client.post("/api/checks/run", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["provider"] == "openai"
    assert data["logical_model"] == "gpt5-default"
    assert data["mock"] is True
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["web"] is None
    assert pytest.approx(1.0) == data["combined"]["weight_prior"] + data["combined"]["weight_web"]

    # Ensure response conforms to RunResponse and includes required sections
    run_model = RunResponse.model_validate(data)
    assert run_model.aggregation.B == payload["B"]
    assert run_model.sampling.K == payload["K"]
    assert run_model.prior is not None
    assert run_model.combined is not None
