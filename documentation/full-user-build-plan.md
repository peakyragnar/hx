# Full User Build Plan

This document outlines the end-to-end rollout for converting the existing RPL harness into a gated, subscription-backed product. Each phase builds on the previous one; the plan assumes the database foundation (local Docker Postgres + Neon) is already in place.

---

## Phase 1 – API Wrapper
- Scaffold a FastAPI service in `api/`.
- Implement `POST /api/checks/run` that:
  - Accepts a claim payload.
  - Calls `evaluate_rpl(...)` (reuse existing harness logic).
  - Persists result rows into Postgres `checks` (with `env='dev'` for local).
  - Returns the RPL JSON result to the caller.
- Add shared config/env loader and SQLAlchemy session helpers.
- Local run: `uv run uvicorn api.main:app --reload` with Docker Postgres running.

## Phase 2 – Magic-Link Auth
- Implement passwordless sign-in with email tokens.
  - `POST /api/auth/magic-links`: create token, store in `email_tokens`, send via Postmark (or MailHog locally).
  - `GET /api/auth/callback`: verify token, create `sessions` row, set HttpOnly cookie.
- Add `GET /api/me`: return user identity and current plan/usage (stub values initially).
- Utilities for token hashing and cookie management.

## Phase 3 – Gatekeeper & Usage Tracking
- Build usage ledger logic (stored in `usage_ledger`).
  - Anonymous: 1 free run.
  - Signed-in trial: total of 3 runs.
  - Subscribers: Starter 20 / Core 100 / Unlimited 750 checks per billing cycle.
- Enforce rules in `POST /api/checks/run`:
  - Allow or reject with 402 responses carrying `reason` (`require_signin`, `require_subscription`, `limit_reached`).
  - Log/record check with user context, decrement usage, and optionally serve cached results without decrementing.
- Update `GET /api/me` to return real usage counts and remaining allowances.

## Phase 4 – Stripe Integration
- Configure Stripe products/prices; store IDs in env.
- Endpoints:
  - `POST /api/billing/checkout`: create Stripe Checkout session for selected tier (Starter/Core/Unlimited).
  - `POST /api/stripe/webhook`: handle subscription events (`checkout.session.completed`, `customer.subscription.*`), update `users.plan`, `users.billing_anchor`, and initialize/reset usage ledger.
- Store Stripe customer IDs on `users`.
- Local testing via Stripe CLI webhook forwarding.

## Phase 5 – Frontend Integration
- Update existing landing page/UI to consume the new API.
  - Run claim → call `/api/checks/run`.
  - On 402 `require_signin`: open email modal → call `/api/auth/magic-links`.
  - On 402 `require_subscription`: open plan modal → call `/api/billing/checkout`.
  - Show usage meter using `/api/me`.
- Ensure fetch requests include credentials (cookies) and handle redirects/success messages gracefully.

## Phase 6 – Deployment
- API on Render
  - Create a Docker-based Web Service from this repo, set the start command to `/app/.venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8080`, and choose at least the 1 GB instance.
  - Configure environment variables (OpenAI, Neon DB URL, Postmark, Stripe, session settings) via the Render dashboard.
- Database
  - Apply Alembic migrations to Neon production branch.
- Frontend
  - Deploy static assets to Vercel (or current host) with `NEXT_PUBLIC_API_URL` set to the Render endpoint.
- DNS & TLS
  - Configure Cloudflare (or provider) to route `api.heretix.* → Render`, `app.heretix.* → Vercel`.
- Postmark
  - Verify sending domain, set live token.
- Stripe
  - Switch to live keys, configure webhook endpoint (`https://api.heretix…/api/stripe/webhook`).

## Phase 7 – Observability & Admin Utilities
- Add structured logging for key events (`check_run`, `signin_requested`, `signin_success`, `checkout_created`, `subscription_active`, `limit_hit`).
- Provide simple admin scripts (e.g., adjust plan tier, grant extra checks) using DB models.
- Implement analytics export CLI to dump `checks` into Parquet for DuckDB (combines SQLite + Postgres data).

## Phase 8 – Optional Enhancements
- Stripe customer portal integration (self-service cancellations/upgrades).
- Multi-claim/batch upload workflows.
- Advanced caching (object storage for RPL outputs shared across users).
- Admin dashboard (FastAPI admin, Streamlit, or custom UI).
- Additional pricing tiers or enterprise plans.

---

## Launch Milestones
1. **MVP ready:** Phases 1–3 (API + auth + gating) running locally.
2. **Closed beta:** Phase 4 (payments) working; invite-only testers.
3. **Public launch:** Phase 5 + Phase 6 complete (UI integrated, deployed with DNS, live payment + email).
4. **Post-launch hardening:** Phases 7–8 as needed.

This plan keeps the existing RPL math untouched while wrapping it in the minimal infrastructure needed for sign-in and subscription gating.
