# Database Architecture Overview

We are splitting storage into two clear lanes so production traffic stays clean while research remains fast and lightweight.

## Lane A: Operational Databases

- **Local Postgres (Docker)** mirrors production. We develop, run migrations, and test against this instance so the schema and behavior match Neon exactly.
- **Neon Postgres (production + development branches)** stores real users, sessions, quotas, payments, and the RPL checks they trigger once the app is live.
- Application rule: each run writes only to the database of the environment where it occurred. No cross-writes between local and production.

### Core tables (shared schema)
- `users`: account identity, plan, status.
- `sessions`: active sessions / magic-link logins.
- `email_tokens`: pending magic-link verifications.
- `checks`: one row per RPL run. Columns mirror the Phase‑1 SQLite `runs` table (prob_true_rpl, CI fields, sampler/config JSON) plus production context such as `env`, `user_id`, and cache metadata.
- `usage_ledger`: monthly counters per user/plan (tracks allowances and resets).
- `result_cache`: stored outputs keyed by deterministic hash for reuse across identical runs.

## Lane B: Research + Analytics

- **Research harness (SQLite)** continues to power local experiments. It already fits the RPL workflow, requires zero setup, and is isolated from production concerns.
- After each research run we append the row to a partitioned Parquet file under `data/exports/local/dt=YYYY-MM-DD/`. This keeps experiments analyzable without touching Postgres.
- A CLI (`hx export checks`) will also export production runs to Parquet (e.g., nightly). Parquet files from both environments live side-by-side.
- **DuckDB catalog** reads every Parquet partition via views so analytics queries can join local and prod data with a single SQL statement.

## How Everything Fits Together

1. Developers work against local Postgres using SQLAlchemy/Alembic. Migrations run here first, then against Neon.
2. Live users interact with the Neon instance. Usage counters and caches update there.
3. Researchers run heavy experiments through the existing SQLite harness. Results stay local but are exported to Parquet for unified analysis.
4. Analytics queries target Parquet via DuckDB, never the operational databases. The `env` column makes it easy to slice by source.

This structure keeps production simple, mirrors behavior in development, and still supports high-volume local experimentation with minimal friction.
