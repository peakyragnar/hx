# How the Full System Works

This document captures the current architecture after adding the Postgres schema and the FastAPI wrapper around the existing RPL harness.

---

## 1. Storage Architecture

### SQLite (Phase‑1 Harness)
- Location: `runs/heretix.sqlite` (or `runs/heretix_mock.sqlite` when running the mock provider).
- Purpose: Original data store for the RPL CLI and test suite.
- Tables:
  - `runs`: one row per execution with aggregates, seeds, sampler JSON, PQS/gate flags, etc.
  - `samples`: cached per-template/replicate outputs (used to avoid duplicate provider calls).
- This schema remains untouched, ensuring backward compatibility and keeping the test harness stable.

### Postgres (Local Docker + Neon)
- The new operational schema for user-facing features lives here.
- Local development: Docker Compose Postgres on port 5433.
- Production: Neon serverless Postgres (same schema, migrations managed via Alembic).
- Tables:
  - `users`: account identity (email, plan tier, status, timestamps).
  - `sessions`: active sessions/magic-link logins (FK → users, expiry info).
  - `email_tokens`: magic-link tokens (selector + hashed verifier + TTL).
  - `checks`: canonical run record mirroring the SQLite `runs` columns plus production context (`env`, `user_id`, `was_cached`, etc.).
  - `usage_ledger`: per-user monthly counters for plan enforcement (plan, checks_allowed, checks_used, period bounds).
  - `result_cache`: stored RPL outputs keyed by deterministic hash for reuse across identical runs.
  - `alembic_version`: tracks migration state.
- Migrations are generated/applied via Alembic; both Docker and Neon run the same migration history.

### Analytics Plan
- Research runs continue to use SQLite.
- Production runs land in Postgres (`checks`).
- Future work will export both datasets to Parquet so DuckDB can join them via a shared schema (`run_id`, aggregates, provenance).

---

## 2. FastAPI Integration

### Overview
- Location: `api/` package.
- Purpose: expose the RPL meter as an HTTP service and persist results in Postgres.
- Main files:
  - `api/config.py`: loads env settings (DB URL, RPL defaults, prompt path).
  - `api/database.py`: SQLAlchemy engine + session management (dependency for FastAPI).
  - `api/schemas.py`: Pydantic models describing request/response payloads.
  - `api/main.py`: FastAPI app with endpoints for runs, magic-link sign-in, and session introspection.

### Request Flow (POST /api/checks/run)
1. Client sends JSON `{ "claim": "...", ...optional overrides... }`.
2. FastAPI constructs a `RunConfig` using defaults plus overrides (e.g., mock mode).
3. Calls `heretix.rpl.run_single_version`, which performs the K×R GPT-5 sampling and aggregation.
4. Upserts a row in Postgres `checks` with the returned metrics (prob_true_rpl, CI, stability, gate flags, etc.) and environment tag (`env`).
5. Responds with structured JSON (sampling info, aggregation diagnostics, main aggregates).

### Magic-Link Flow
1. `POST /api/auth/magic-links` stores a selector/verifier hash for the user and sends the link via Postmark (or logs it locally).
2. Visiting `/api/auth/callback?token=selector:verifier` validates the token, marks it consumed, creates a session row, and sets an HttpOnly cookie.
3. `GET /api/me` returns whether the current cookie maps to an active session (email, plan, placeholders for usage).

### Usage & Gating
- `api/usage.py` defines plan tiers (anon, trial, starter, core, pro) and interacts with `usage_ledger` to track monthly allowance.
- `/api/checks/run` consults the usage state before executing:
  - Anonymous clients receive one free run.
  - Signed-in trial users receive three lifetime runs.
  - Subscribers use their plan allowance (Starter 20, Core 100, Pro 750) per period.
- When an allowance is exhausted the endpoint responds with HTTP 402 and a structured reason (`require_signin`, `require_subscription`, or `limit_reached`).
- Successful runs update the ledger and return usage metadata (plan, checks_used, remaining) to drive the frontend meter.

### Stripe Integration
- `api/billing.py` wraps Stripe Checkout and subscription webhooks.
  - `POST /api/billing/checkout` creates a subscription checkout session for the requested plan, ensuring a Stripe customer is registered.
  - `POST /api/stripe/webhook` handles `checkout.session.completed` and subscription lifecycle events to update `users.plan`, store Stripe IDs, and reset usage ledgers.
- Plan IDs/keys are configured via environment variables (`STRIPE_SECRET`, `STRIPE_PRICE_STARTER`, etc.).
- Local development uses the Stripe CLI (`stripe listen --forward-to http://127.0.0.1:8000/api/stripe/webhook`) alongside test price IDs.

### Mock Mode & Defaults
- The run endpoint honors the `mock` flag for local testing.
- Prompt files resolve via `settings.prompt_file()` (uses `RPL_PROMPT_VERSION` and optional `RPL_PROMPTS_DIR`).
- DB writes currently assume `env=settings.app_env` (default `local`).

### Local Usage
1. Start Postgres: `docker compose up -d postgres`.
2. Apply migrations: `uv run alembic upgrade head`.
3. Run API: `uv run uvicorn api.main:app --reload`.
4. Smoke test (mock provider):
   ```bash
   curl -s http://127.0.0.1:8000/api/checks/run \
     -H 'content-type: application/json' \
     -d '{"claim": "Tariffs cause inflation", "mock": true}' | jq
   ```

### Future Extensions
- Phases 2–4 will add authentication (magic links), gating/usage counters, and Stripe billing around this endpoint.
- Frontend will call this API and react to gateway responses (e.g., 402 require_signin/require_subscription).

---

## 3. Summary
- SQLite remains the research/stats store; Postgres hosts production-ready tables for runs, users, sessions, and subscriptions.
- FastAPI now provides a clean API surface to trigger RPL runs and persist them in Postgres.
- This foundation enables subsequent phases (auth, gating, payments) without touching the estimator math.
