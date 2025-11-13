# Heretix — Raw Prior Lens (RPL)

![Estimator](https://img.shields.io/badge/Estimator-Frozen-green)
![Auto–RPL](https://img.shields.io/badge/Auto–RPL-Enabled-blue)
![Prompt%20Version](https://img.shields.io/badge/PROMPT__VERSION-rpl__g5__v2__2025--08--21-purple)

Heretix measures a model’s internal prior over claims and rewards durable belief movement. This repository now contains a clean RPL harness (`heretix/`) and quarantined legacy code under `legacy/`.

- Estimator (frozen): logit-space aggregation, equal-by-template weighting, 20% trimmed center (T≥5), cluster bootstrap (B=5000) with deterministic seed.
- Prompts: `PROMPT_VERSION=rpl_g5_v2_2025-08-21` with 16 paraphrases.

## Quick Start (New Harness)

- Setup environment (uv):
```
uv sync
```

- Create a minimal run config (example):
```
cat > runs/rpl_example.yaml << 'EOF'
claim: "tariffs don't cause inflation"
model: gpt-5
prompt_version: rpl_g5_v2
K: 8
R: 2
T: 8
B: 5000
seed: 42
max_prompt_chars: 1200
max_output_tokens: 1024
EOF
```

- Run the same claim across multiple models by either listing them in the config or overriding via CLI:
  - Config snippet:
    ```yaml
    models:
      - gpt-5
      - grok-4
      - deepseek-r1
    ```
  - CLI override (takes precedence and can be repeated):
    ```
    uv run heretix run --config runs/rpl_example.yaml --model gpt-5 --model grok-4 --mock
    ```
  The CLI executes every `(model, prompt_version)` combination sequentially and writes a single JSON summary with `requested_models` plus one `runs[]` entry per model.

- Run RPL (single or multi-version):
```
export OPENAI_API_KEY=sk-...
uv run heretix run --config runs/rpl_example.yaml --out runs/new_rpl.json
```

- Smoke test (no network):
```
uv run heretix run --config runs/rpl_example.yaml --out runs/smoke.json --mock
```

- Describe plan (no network):
```
uv run heretix describe --config runs/rpl_example.yaml
```

- Output includes: p_RPL, CI95, stability, cache_hit_rate, rpl_compliance_rate. Each run also
  emits stage-level telemetry (timings, tokens, cache hits) and a `run_summary` line with wall
  time and estimated cost.

Legacy CLI is available under `legacy/` for reference but is not installed by default.

## Local Postgres (App Data)
- Start the development database:
  - `docker compose up -d postgres`
- Use the local connection string in your shell: `DATABASE_URL=postgresql+psycopg://heretix:heretix@localhost:5433/heretix`
- Apply migrations after changes: `alembic upgrade head`
- Stop services when done: `docker compose down`
- Production deployments point at the Neon connection string saved as `DATABASE_URL_PROD`.

### Local API Scaffold
- Install dependencies: `uv sync`
- Start Postgres (`docker compose up -d postgres`) and run migrations (`uv run alembic upgrade head`).
- Launch the API locally: `uv run uvicorn api.main:app --reload`
- Smoke test (mock provider):
  ```bash
  curl -s http://127.0.0.1:8000/api/checks/run \
    -H 'content-type: application/json' \
    -d '{"claim": "Tariffs cause inflation", "mock": true}' | jq
  ```

### Magic-Link Sign-in (local flow)
- Request link:
  ```bash
  curl -s -X POST http://127.0.0.1:8000/api/auth/magic-links \
    -H 'content-type: application/json' \
    -d '{"email": "you@example.com"}' -o /dev/null -w "%{http_code}\n"
  ```
- Check server logs (or Postmark/MailHog) for the printed URL. Visit it in a browser or with curl to store the cookie:
  ```bash
  curl -s '<MAGIC_LINK_URL>' -c cookies.txt | jq
  ```
- Verify session:
  ```bash
  curl -s http://127.0.0.1:8000/api/me -b cookies.txt -c cookies.txt | jq
  ```
- Limits (local defaults):
  - Anonymous: 1 run → subsequent requests return HTTP 402 with `{"reason":"require_signin"}`.
  - Signed-in trial: total of 3 runs → HTTP 402 with `{"reason":"require_subscription"}` afterward.
  - Subscribers: placeholder caps (Starter/Core/Pro) to be wired in during Stripe integration.

### Stripe Checkout (development)
- Set test env vars (see `api/config.py` for keys such as `STRIPE_SECRET`, `STRIPE_PRICE_STARTER`, etc.).
- Run Stripe CLI to forward webhooks:
  ```bash
  stripe listen --forward-to http://127.0.0.1:8000/api/stripe/webhook
  ```
- Create a checkout session (signed-in user required):
  ```bash
  curl -s -X POST http://127.0.0.1:8000/api/billing/checkout \
    -H 'content-type: application/json' -b cookies.txt \
    -d '{"plan": "starter"}' | jq
  ```
- Visit the returned `checkout_url`, complete payment with Stripe test card, and Stripe will invoke the webhook to promote the account plan.

## Deploying to Production

### 1. Provision infrastructure
- **Database:** Create a Neon Postgres project (production branch). Keep the connection string handy (`DATABASE_URL_PROD`).
- **API host:** Create a Render Web Service from this repository, select the Dockerfile, and use at least the 1 GB instance size. Set the start command to `/app/.venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8080`.
- **Frontend:** Deploy `ui/` to your static host (e.g., Vercel). Set `NEXT_PUBLIC_API_URL` (or equivalent) to the Render service URL (update to your custom domain once DNS is in place).

### 2. Apply migrations to Neon
```bash
DATABASE_URL="<NEON_CONNECTION>" uv run alembic upgrade head
```

### 3. Configure secrets (Render)
Add the required environment variables in **Render → Dashboard → Service → Environment** or via `render.yaml`:

```
OPENAI_API_KEY=...
DATABASE_URL="<NEON_CONNECTION>"
EMAIL_SENDER_ADDRESS=team@heretix.ai
POSTMARK_TOKEN=...
STRIPE_SECRET=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER=price_live_starter
STRIPE_PRICE_CORE=price_live_core
STRIPE_PRICE_PRO=price_live_pro
STRIPE_PORTAL_CONFIG=bpc_...
MAGIC_LINK_TTL_MINUTES=15
SESSION_TTL_DAYS=30
SESSION_COOKIE_DOMAIN=.heretix.ai
SESSION_COOKIE_SECURE=true
ANON_COOKIE_NAME=heretix_anon
APP_ENV=production
APP_URL=https://heretix.ai
API_URL=https://<your-api>.onrender.com
```

### 4. Deploy the API
- Render will build and deploy automatically after you connect the repository. Use the Render dashboard to trigger redeploys as needed.
- `/healthz` remains available for platform checks.

### 5. Wire DNS/TLS
- Point `api.heretix.<domain>` to the Render service (CNAME) and `app.heretix.<domain>` to the frontend host.
- Render/Vercel issue TLS certificates automatically once DNS is active.

### 6. Verify production
- Request a magic link (should deliver via Postmark) and complete the callback.
- Run a claim (deducts usage and persists to Neon).
- Trigger a real checkout with Stripe live mode (use $0 coupon or test card if on staging) and verify the webhook updates the plan.

## Faster Runs (Concurrency, Fast CI, Caching)

- Concurrency (default 8 workers): set `HERETIX_RPL_CONCURRENCY` to control the thread pool used for
  provider calls. Leave it unset to use 8 workers or tune per run with the env var.
- Fast-first CI: the harness returns a fast bootstrap (`HERETIX_FAST_B`, default 1000) immediately and
  recomputes the final `B` (`HERETIX_FINAL_B`, default 5000) in the background. Disable with
  `HERETIX_FAST_FINAL=0` if you want to block until the full CI is ready.
- Run-level cache: sample caching is always on. Set `HERETIX_CACHE_TTL` to a positive number to reuse
  identical runs; leave it unset (0) during development to ensure every run pulls fresh samples.
- CLI example:
  - `HERETIX_CONCURRENCY=8 uv run heretix run --config runs/rpl_example.yaml --out runs/faster.json`
- UI (opt‑in):
  - `HERETIX_CONCURRENCY=8 UI_PORT=7799 uv run python ui/serve.py` then open `http://127.0.0.1:7799`
- Notes:
  - Concurrency parallelizes provider calls only; estimator/DB/identities unchanged.
  - For long claims, prefer `max_output_tokens: 768–1200` to avoid truncated JSON under parallel load.
  - Start with 6–8 workers; reduce if your provider rate‑limits.
  - See `faster-processing.md` for details.

## Single-Claim Workflow
- Use `claim:` in your config and run with `heretix run` as above. Outputs persist to SQLite and a single JSON file for easy inspection.
- See the detailed step‑by‑step guide in `documentation/how-to-run.md` (includes the HTML report and opening it in Chrome).

## Tests
- New harness (default): `uv run pytest -q`
- Include legacy (optional): `uv run pytest heretix/tests legacy/tests -q`

## Determinism
- Set a bootstrap seed in the config (`seed: 42`) to fix CI draws.
- Precedence: config `seed` > `HERETIX_RPL_SEED` env > derived deterministic value.
- The effective `bootstrap_seed` is shown in outputs and persisted in the DB.

## One‑Liner (Deterministic CI)
```
HERETIX_RPL_SEED=42 uv run heretix run --config runs/rpl_example.yaml
```

## Docs
- New harness design: see `refactor.md` (Tooling with uv, repo structure, phases)
- Estimator and stats: `documentation/aggregation.md`, `documentation/STATS_SPEC.md`
- Smoke tests: `documentation/smoke_tests.md`
- Legacy docs remain in `documentation/` and are referenced by the archived code under `legacy/`.

## Determinism & Provenance
- Same inputs → same decisions and CIs.
- Outputs include `bootstrap_seed`, `prompt_version`, `counts_by_template`, and stability diagnostics.

## Invariants (do not break without version bump)
- Aggregate in logit space; equal-by-template before global center; 20% trim when T≥5; cluster bootstrap with deterministic seed.
