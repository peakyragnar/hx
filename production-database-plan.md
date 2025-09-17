# Production Database Plan

1. Neon Production DB — Complete
   - Neon project "Heretix" created (Postgres 16, us-east-1); production connection string saved to `.env` (`DATABASE_URL_PROD`).
   - No further action until deployment.

2. Local Postgres Environment
   - Add `docker-compose.yml` with Postgres 16 (`heretix` user/password/db).
   - Document local env var `DATABASE_URL=postgresql+psycopg://heretix:heretix@localhost:5432/heretix` in `.env.example`.
   - Verify the container starts and accepts connections.

3. Dependencies & Tooling
   - Add `sqlalchemy`, `psycopg[binary]`, and `alembic` to `pyproject.toml`; run `uv sync`.
   - Initialize Alembic (`alembic init migrations`) using the local `DATABASE_URL`.

4. Schema Design & Initial Migration
   - Define tables: `users`, `sessions`, `email_tokens`, `checks` (with `env` column), `usage_ledger`, `result_cache`.
   - Generate and apply the first Alembic migration to local Postgres (`alembic upgrade head`).

5. Research Lane Integration
   - Keep the existing SQLite harness for experiments.
   - Add a post-run hook that appends each research run to `data/exports/local/dt=YYYY-MM-DD/checks.parquet`.
   - Implement CLI command `hx export checks` for exporting from SQLite/Postgres to partitioned Parquet.
   - Ship sample analytics queries in `analytics/queries.sql`.

6. App Integration
   - Point backend services at Postgres via `DATABASE_URL`.
   - Layer in auth/quota/payment features once the schema is available (future tasks).

7. Neon Migration & Deploy Prep
   - Configure secrets manager with `DATABASE_URL_PROD` when ready to deploy.
   - Run Alembic migrations against Neon (production branch first, development branch for staging).
   - Schedule recurring `hx export` for prod data (cron/GitHub Actions pulling to Parquet or object storage).

8. Docs & Tooling
   - Update README/AGENTS with instructions: start local Postgres, apply migrations, export analytics, run DuckDB.
   - Provide helper scripts (`bin/dev_db_reset`, `bin/export_local`, etc.) for reproducible workflows.
