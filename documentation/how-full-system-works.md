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

## 2. Application & Delivery Architecture

### API Service (Render)
- Hosted as a Render "Web Service" that builds directly from the repository `Dockerfile`.
- Runs `uvicorn api.main:app` inside the container built by `uv sync --frozen --no-dev`.
- Key environment variables (managed in Render):
  - `DATABASE_URL` (Neon Postgres connection).
  - RPL defaults (`RPL_MODEL`, `RPL_PROMPT_VERSION`, `RPL_K`, etc.).
  - Stripe credentials (`STRIPE_SECRET`, `STRIPE_PRICE_*`, `STRIPE_WEBHOOK_SECRET`).
  - URLs for cross-service coordination (`API_URL`, `APP_URL`).
- FastAPI installs `CORSMiddleware` so the browser UI at `https://heretix.ai` (and previews on `vercel.app`) can call the API with cookies.
- `/healthz` is Render's readiness probe before shifting traffic to a new deploy.

### Frontend (Vercel)
- Deployed from the `ui/` directory with the "Other" preset and root path `ui`.
- Production domain: `https://heretix.ai`; preview domain: `https://heretix-ui.vercel.app`.
- The HTML embeds `<meta name="heretix-api-base" content="https://api.heretix.ai">` and JS fallbacks for local development and preview hosts.
- Client-side JS handles claim submission, magic-link sign-in, usage meter updates, and redirects to Stripe Checkout.

### Networking & DNS
- `api.heretix.ai` → CNAME to Render (`heretix-api.onrender.com`).
- `heretix.ai` → A record `76.76.21.21` (Vercel) and `www.heretix.ai` → CNAME `cname.vercel-dns.com`.
- Vercel and Render automatically issue TLS certificates once records resolve.

### Secrets & Configuration
- Local `.env` is for development; production secrets live in Render/Vercel dashboards.
- Render environment changes require a redeploy to take effect.
- Stripe webhook signing secret is stored in `STRIPE_WEBHOOK_SECRET` so events are verified.

### Observability & Logs
- Render console provides build/runtime logs (`stripe_webhook`, magic-link requests, run executions).
- Stripe dashboard records webhook deliveries; the CLI (`stripe listen`) is used for testing.
- Neon gives visibility into `users`, `usage_ledger`, and `checks` for debugging plan/usage issues.

---

## 3. FastAPI Integration

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

### Deployment Stack
- `Dockerfile` builds the FastAPI service (uvicorn) and is consumed directly by Render’s Web Service deployment.
- `.dockerignore` keeps build context lean.
- `/healthz` exposes a simple health check for platform probes (Render, local, etc.).
- Neon hosts the managed Postgres instance; apply Alembic migrations via `DATABASE_URL=<neon> uv run alembic upgrade head` before deploying.

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
- Additional providers (Claude, Grok, DeepSeek) can be surfaced once the harness plugs in alternate adapters.
- Usage exports (Parquet + DuckDB) will enable analytics across SQLite + Neon datasets.
- Stripe Customer Portal integration would allow self-serve plan management and invoicing.

---

## 4. End-to-End Flows

### Claim Evaluation
1. A visitor loads `https://heretix.ai` (Vercel) and submits a claim through the form.
2. JS posts to `https://api.heretix.ai/api/checks/run` with cookies (if signed in) and optional mock flag.
3. FastAPI executes the RPL harness, stores the result in Neon (`checks`, `usage_ledger`), and returns aggregates (probability, CI, stability).
4. The UI renders the response and updates the usage meter by calling `/api/me`.

### Magic-Link Sign-in
1. The "Sign in" navigation item opens the modal and posts an email to `/api/auth/magic-links`.
2. The API records a token (`email_tokens`) and asks Postmark to send the link.
3. Visiting the link hits `/api/auth/callback`, verifies the token, creates a `sessions` row, and sets an HttpOnly cookie.
4. Future requests include the cookie; `/api/me` reflects plan + remaining checks.

### Billing & Plan Changes
1. Signed-in users choose a plan; `/api/billing/checkout` creates a Stripe Checkout Session using the plan’s `STRIPE_PRICE_*` ID.
2. On successful payment, Stripe redirects to `APP_URL+STRIPE_SUCCESS_PATH`.
3. Stripe sends webhook events (`checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`).
4. `/api/stripe/webhook` verifies the signature, updates `users.plan`, stores Stripe IDs, and resets the usage ledger to the allowance (Starter 20, Core 100, Pro 750 checks).

### Deployment Workflow
1. Changes land on `full-feature` (includes Dockerfile, uv.lock, API/UI updates).
2. Render builds the Docker image and health-checks `/healthz` before routing traffic.
3. Vercel builds the `ui/` directory and publishes to `heretix.ai`.
4. After verification, merge `full-feature` → `main` to sync the default branch.

---

## 5. Summary
- SQLite remains the research/store for CLI experiments; Neon Postgres is the authoritative production database for users, runs, and ledgers.
- Render hosts the FastAPI service (CORS-enabled, Stripe-integrated) while Vercel serves the static UI that calls the API.
- DNS (`heretix.ai`, `api.heretix.ai`), Stripe Checkout, and webhooks glue the experience together so subscription plans automatically align with usage limits.
