# Staging Environment Plan

Goal: mirror the production stack (Neon Postgres, Render API, Render Static Site UI) on an isolated branch so we can run migrations and deployments end-to-end before touching live traffic.

## Components
- **Neon Postgres staging branch:** clone production (`fork` in Neon UI) into a branch named `staging`. Connection string saved as `DATABASE_URL_STAGING`.
- **Render staging service:** duplicate the API web service (`heretix-api-staging`) that points at the staging branch. Build from the same repo/branch as prod.
- **Render preview (optional):** use a separate Render Static Site (staging domain) pointing at the staging API. For CLI/manual tests, direct access to the API is usually enough.

## Migration/Deploy Workflow
1. **Local prep**
   - Run `uv run alembic upgrade head` against local Docker Postgres.
   - Run `uv run pytest -q` to ensure the code + migrations work locally.

2. **Apply to Neon staging**
   - Set `DATABASE_URL=$DATABASE_URL_STAGING uv run alembic upgrade head`.
   - Verify schema: `uv run python scripts/inspect_schema.py --url $DATABASE_URL_STAGING` (write helper if needed).

3. **Deploy to Render staging**
   - Trigger staging deploy (manual or CI) so `heretix-api-staging` pulls the new code.
   - Run smoke tests against staging: 
     * `/api/healthz`
     * `/api/me` (anonymous + after magic-link sign-in)
     * `/api/checks/run` (anonymous + authenticated)
   - Inspect staging DB rows (staging Neon branch) to confirm `checks`, `anonymous_usage`, `usage_ledger` updated.

4. **Roll to production** (only after staging passes)
   - Apply the same Alembic script to production: `DATABASE_URL=$DATABASE_URL_PROD uv run alembic upgrade head`.
   - Deploy production API.
   - Run the same smoke tests on production.

## Tooling & Automation
- Add `DATABASE_URL_STAGING` to `.env.example` and doc(s).
- Update GitHub Actions (or other CI) to run migrations in staging automatically for each PR/merge.
- Provide helper scripts: `bin/migrate-staging`, `bin/migrate-prod`, `bin/smoke-staging`.
- Optionally gate prod deployment until staging smoke tests succeed (CI/CD).

## Ongoing Maintenance
- Keep staging data fresh by periodically cloning prod to staging (Neon branch reset).
- Use staging for any schema change, provider change, or API-level feature before prod.
- Document the workflow in `production-database-migration.md` and DevOps runbooks.
