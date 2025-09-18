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

## 3. Deploy API to Fly.io
1. Authenticate: `fly auth login`
2. Create app: `fly launch --no-deploy` (uses `fly.toml` + Dockerfile)
3. Set secrets:
   ```bash
   flyctl secrets set OPENAI_API_KEY=... DATABASE_URL=... \
       EMAIL_SENDER_ADDRESS=... POSTMARK_TOKEN=... \
       STRIPE_SECRET=... STRIPE_WEBHOOK_SECRET=... \
       STRIPE_PRICE_STARTER=... STRIPE_PRICE_CORE=... STRIPE_PRICE_PRO=...
   ```
4. Deploy: `flyctl deploy`
5. Check logs/health: `flyctl logs tail` (ensure `/healthz` responds with `{"status":"ok"}`)

## 4. Deploy Frontend
- [ ] Configure your static host (e.g. Vercel) to point at `NEXT_PUBLIC_API_URL=https://api.heretix.<domain>`
- [ ] Deploy the existing UI (or import the repo if using Vercel)

## 5. DNS & TLS
- [ ] Add records via Cloudflare (or DNS provider):
  - `api.heretix.<domain>` → Fly (CNAME or A record per Fly instructions)
  - `app.heretix.<domain>` → frontend host (CNAME)
- [ ] Verify certificates (Fly/Vercel will auto-provision once DNS resolves)

## 6. Email & Webhook Verification
- [ ] Postmark: verify sending domain, ensure production server is active
- [ ] Stripe: configure webhook endpoint `https://api.heretix.<domain>/api/stripe/webhook`
- [ ] Use Stripe live mode or test mode (for staging) with `stripe listen` to confirm events flow

## 7. Final Smoke Tests
1. Request a magic link in production; confirm email delivery and cookie is set
2. Run a claim (should decrement usage and persist to Neon)
3. Trigger a live checkout (Coupon/test card if needed) and confirm plan updates via `/api/me`
4. Watch Fly logs for webhook handling and error signals

## 8. Observability & Monitoring (Optional Next Steps)
- [ ] Add Sentry/Honeycomb (or preferred APM) to the FastAPI app
- [ ] Create a cron or workflow to rotate logs/perform nightly exports (Phase 7)
- [ ] Add a simple admin CLI/script to inspect usage or adjust plans

---

When these items are checked off, the Heretix service is production-ready with live email, billing, and a shareable UI. Document any environment-specific tweaks in your deployment runbook for future updates.
