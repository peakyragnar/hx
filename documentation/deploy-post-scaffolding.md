# Deploy Post-Scaffolding Checklist

This checklist covers the remaining operational steps to take the Heretix service live after completing the Phase-6 scaffolding.

---

## 1. Configure Environment Secrets
- [ ] **OpenAI**: `OPENAI_API_KEY`
- [ ] **Database**: `DATABASE_URL` (local), `DATABASE_URL_PROD` (Neon connection string)
- [ ] **Auth Email**: `EMAIL_SENDER_ADDRESS`, `POSTMARK_TOKEN` (or keep console logging if not ready)
- [ ] **Magic-link / Session**: `MAGIC_LINK_TTL_MINUTES`, `SESSION_TTL_DAYS`, `SESSION_COOKIE_DOMAIN` (if custom domain), `SESSION_COOKIE_SECURE=true` in production
- [ ] **Stripe**:
  - `STRIPE_SECRET` (live)
  - `STRIPE_WEBHOOK_SECRET`
  - `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_CORE`, `STRIPE_PRICE_PRO` (live price IDs)
  - Optional: `STRIPE_SUCCESS_PATH`, `STRIPE_CANCEL_PATH`
- [ ] **App/API URLs**: set `API_URL`, `APP_URL` to the production domains for the backend and frontend

## 2. Prepare Neon Postgres
- [ ] Create a Neon project (production branch)
- [ ] Run migrations against production:
  ```bash
  DATABASE_URL="<neon-production-url>" uv run alembic upgrade head
  ```
- [ ] Optionally create a staging branch and apply migrations for pre-prod testing

## 3. Deploy API to Render
1. Create a Docker-based Web Service pointed at this repository/branch.
2. Instance type: choose at least the 1 GB RAM plan.
3. Start command: `/app/.venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8080`.
4. Add environment variables in the Render dashboard (`OPENAI_API_KEY`, `DATABASE_URL`, Postmark, Stripe, session settings, `APP_URL`, `API_URL`, etc.).
5. Trigger the initial deploy from the dashboard and wait for the health check to pass (`/healthz`).

## 4. Deploy Frontend
- [ ] Create a Render Static Site (root `ui`) and set `NEXT_PUBLIC_API_URL=https://api.heretix.<domain>` (or configure the existing meta tag).
- [ ] Attach `heretix.<domain>` / `www.heretix.<domain>` custom domains to the site and deploy.

## 5. DNS & TLS
- [ ] Add records via Cloudflare (or DNS provider):
  - `api.heretix.<domain>` → Render API (CNAME to the service hostname)
  - `heretix.<domain>` → ALIAS/ANAME to the Render static site; `www.heretix.<domain>` → CNAME to the static site
- [ ] Verify certificates (Render will auto-provision once DNS resolves)

## 6. Email & Webhook Verification
- [ ] Postmark: verify sending domain, ensure production server is active
- [ ] Stripe: configure webhook endpoint `https://api.heretix.<domain>/api/stripe/webhook`
- [ ] Use Stripe live mode or test mode (for staging) with `stripe listen` to confirm events flow

## 7. Final Smoke Tests
1. Request a magic link in production; confirm email delivery and cookie is set
2. Run a claim (should decrement usage and persist to Neon)
3. Trigger a live checkout (Coupon/test card if needed) and confirm plan updates via `/api/me`
4. Watch Render logs for webhook handling and error signals

## 8. Observability & Monitoring (Optional Next Steps)
- [ ] Add Sentry/Honeycomb (or preferred APM) to the FastAPI app
- [ ] Create a cron or workflow to rotate logs/perform nightly exports (Phase 7)
- [ ] Add a simple admin CLI/script to inspect usage or adjust plans

---

When these items are checked off, the Heretix service is production-ready with live email, billing, and a shareable UI. Document any environment-specific tweaks in your deployment runbook for future updates.
