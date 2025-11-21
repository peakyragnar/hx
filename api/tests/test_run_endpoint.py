import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.exc import IntegrityError

TEST_DB_PATH = Path("runs/api_test.sqlite").resolve()
TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

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

_ENV_PATCH = MonkeyPatch()
_ENV_PATCH.setenv("DATABASE_URL", f"sqlite:///{TEST_DB_PATH}")
_ENV_PATCH.setenv("RPL_ALLOW_MOCK", "true")
_ENV_PATCH.setenv("RPL_MAX_PROMPT_CHARS", "2000")
for var in _NOISE_VARS:
    _ENV_PATCH.delenv(var, raising=False)

from heretix.constants import SCHEMA_VERSION
from heretix.db.migrate import ensure_schema

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from api import usage
from api import main as api_main

from api.config import settings  # noqa: E402
from api.database import session_scope  # noqa: E402
from api.main import app  # noqa: E402
from api.schemas import RunResponse  # noqa: E402
from heretix.db.models import Request as RequestModel  # noqa: E402

settings.rpl_max_prompt_chars = 2000

ensure_schema(settings.database_url)

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _restore_env_patch():
    yield
    _ENV_PATCH.undo()


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


def _make_payload(mode: str, *, provider: str = "openai", logical_model: str = "gpt5-default") -> dict:
    base = {
        "claim": f"API mock run bead ({mode})",
        "mode": mode,
        "provider": provider,
        "logical_model": logical_model,
        "prompt_version": "rpl_g5_v2",
        "K": 4,
        "R": 1,
        "B": 200,
        "max_output_tokens": 128,
        "max_prompt_chars": 2000,
        "mock": True,
    }
    return base


def test_run_check_mock_baseline_returns_runresponse():
    payload = {
        **_make_payload("baseline"),
    }

    resp = client.post("/api/checks/run", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["provider"] == "openai"
    assert data["logical_model"] == "gpt5-default"
    assert data["mock"] is True
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["web"] is None
    cache_rate = data["aggregates"]["cache_hit_rate"]
    cost = data["cost_usd"]
    if cache_rate < 0.999:
        assert data["tokens_in"] > 0
        assert data["tokens_out"] > 0
        assert cost is not None and cost > 0
    else:
        assert data["tokens_in"] == 0
        assert data["tokens_out"] == 0
        assert cost == 0
    assert data["simple_expl"] is not None
    assert pytest.approx(1.0) == data["combined"]["weight_prior"] + data["combined"]["weight_web"]

    # Ensure response conforms to RunResponse and includes required sections
    run_model = RunResponse.model_validate(data)
    assert run_model.aggregation.B == payload["B"]
    assert run_model.sampling.K == payload["K"]
    assert run_model.prior is not None and run_model.prior.compliance_rate is not None
    assert run_model.combined is not None
    assert run_model.simple_expl is not None


def test_run_check_mock_web_mode_includes_web_block():
    payload = {**_make_payload("web_informed")}
    resp = client.post("/api/checks/run", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["provider"] == "openai"
    assert data["logical_model"] == "gpt5-default"
    assert data["mode"] == "web_informed"
    assert data["web"] is not None
    assert data["weights"]["w_web"] == pytest.approx(0.0)
    assert data["combined"]["weight_web"] == pytest.approx(0.0)
    assert data["simple_expl"] is not None

    run_model = RunResponse.model_validate(data)
    assert run_model.web is not None
    assert run_model.weights is not None
    assert run_model.prior is not None


def test_run_check_respects_custom_provider_and_logical_model():
    payload = {
        **_make_payload("baseline", provider="xai", logical_model="grok-4"),
    }
    resp = client.post("/api/checks/run", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["provider"] == "xai"
    assert data["logical_model"] == "grok-4"
    assert data["resolved_logical_model"] == "grok-4"
    assert data["prior"] is not None
    assert data["combined"] is not None

    run_model = RunResponse.model_validate(data)
    assert run_model.provider == "xai"
    assert run_model.logical_model == "grok-4"
    assert run_model.resolved_logical_model == "grok-4"


def test_run_check_reports_resolved_logical_model_for_override():
    payload = {
        **_make_payload("baseline", provider="openai", logical_model="grok-4"),
    }
    resp = client.post("/api/checks/run", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["provider"] == "openai"
    assert data["logical_model"] == "grok-4"
    assert data["resolved_logical_model"] != data["logical_model"]
    run_model = RunResponse.model_validate(data)
    assert run_model.logical_model == "grok-4"
    assert run_model.resolved_logical_model != run_model.logical_model


def test_run_check_infers_provider_from_logical_model():
    payload = {
        **_make_payload("baseline", provider="openai", logical_model="grok-4"),
    }
    payload.pop("provider", None)

    resp = client.post("/api/checks/run", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["provider"] == "xai"
    assert data["logical_model"] == "grok-4"


def test_run_check_allows_case_insensitive_mode():
    payload = {
        **_make_payload("baseline"),
        "mode": "WEB_INFORMED",
    }
    resp = client.post("/api/checks/run", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "web_informed"


def test_run_check_invalid_provider_returns_400():
    payload = {
        **_make_payload("baseline"),
        "provider": "unknown-provider",
    }
    resp = client.post("/api/checks/run", json=payload)
    assert resp.status_code == 400
    detail = resp.json().get("detail")
    assert "unknown-provider" in detail


def test_get_or_create_request_retries_on_duplicate(monkeypatch: pytest.MonkeyPatch):
    request_id = uuid.uuid4()

    with session_scope() as session:
        real_flush = session.flush

        def fake_flush(*args, **kwargs):
            # Simulate another worker inserting the same request record first.
            with session_scope() as other_session:
                other_session.add(
                    RequestModel(
                        id=request_id,
                        claim="concurrent insert",
                        mode="baseline",
                        env=settings.app_env,
                        anon_token=None,
                        user_agent=None,
                        client_ip=None,
                    )
                )
            raise IntegrityError("duplicate key", params=None, orig=Exception("duplicate"))

        monkeypatch.setattr(session, "flush", fake_flush)

        req = api_main.get_or_create_request(
            session,
            request_id=str(request_id),
            claim="primary request",
            mode="baseline",
            env=settings.app_env,
            user=None,
            anon_token=None,
            user_agent=None,
            client_ip=None,
        )

        # Restore the real flush so session_scope can commit cleanly.
        monkeypatch.setattr(session, "flush", real_flush)

        assert str(req.id) == str(request_id)

    with session_scope() as session:
        rows = session.query(RequestModel).filter(RequestModel.id == request_id).all()
        assert len(rows) == 1
