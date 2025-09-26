# Production Database Migration Plan

Goal: Align the Neon production database schema with the canonical Heretix Postgres schema (as defined by Alembic head `b73c9aa4f0c3`) so that:
- API writes succeed without fallback logic.
- `checks` rows mirror the Phase‑1 harness structure (claim, aggregates, diagnostics, gate flags, etc.).
- Anonymous usage limits and user activity are persisted and auditable.
- Analytics queries can union production and local data without column mismatches.

The plan is broken into preparation, execution, and verification phases. All steps assume access to the Neon production project and the local Docker Postgres used in development.

---

## Phase 0 — Pre-flight Inventory
1. **Schema diff:**
   - Use `SELECT column_name FROM information_schema.columns` for each table (`users`, `sessions`, `email_tokens`, `checks`, `usage_ledger`, `result_cache`) in both local Postgres and Neon.
   - Record differences in column names, types, defaults, indexes.
   - Confirm `anonymous_usage` table is missing in production.
2. **Row counts & samples:**
   - Capture counts per table (`SELECT count(*)`) and a few sample rows (especially `checks`, `usage_ledger`).
   - Note existing column names such as `claim_text`, `aggregation`, `diagnostics`.
3. **Backup:**
   - Run `pg_dump` against Neon production (schema + data). Store dump in S3/secure storage with timestamp. This is the rollback checkpoint.

## Phase 1 — Migration Design
1. **Column mapping:**
   - Define mapping from legacy columns → new schema: e.g., `checks.claim_text → checks.claim`, `aggregation → config_json`, `diagnostics → counts_by_template_json`.
   - Decide how to populate new columns (gate flags, PQS). For any data not available, plan to set `NULL` with a backfill ticket.
2. **DDL strategy:**
   - Option A: Apply Alembic migrations directly after renaming legacy columns to their expected names. Requires ensuring the initial migration (`9e15719c5c3c`) matches the legacy structure.
   - Option B: Author a one-off SQL migration script that:
     - Renames columns to current names.
     - Adds missing columns with defaults.
     - Creates `anonymous_usage` table.
     - Adds indexes (`ix_checks_env_anon_token`, etc.).
   - Choose Option B (one-off SQL) for deterministic control, then bump Alembic version to `b73c9aa4f0c3` manually.
3. **Data migration scripts:**
   - For each renamed column, copy data: `ALTER TABLE checks RENAME COLUMN claim_text TO claim` (if possible) or `UPDATE checks SET claim = claim_text` followed by dropping the old column.
   - For JSON blobs currently in `aggregation`/`diagnostics`, parse them or store as-is in `config_json`/`counts_by_template_json`. (Add TODO if lossless conversion is infeasible.)

## Phase 2 — Dry Runs (Local/Staging)
1. **Clone production data to staging branch (Neon):**
   - Use Neon branching or restore backup into a staging environment.
2. **Apply migration script:**
   - Execute planned SQL on staging; ensure it finishes without errors.
3. **Run API against staging:**
   - Point a local instance at staging DB; run `/api/checks/run` and verify inserts succeed and data looks correct.
4. **Analytics smoke tests:**
   - Run queries that union local + staging (DuckDB/Parquet pipeline) to confirm compatible schemas.

## Phase 3 — Production Migration
1. **Maintenance window:**
   - Schedule a short read-only window (expected downtime ≈ 5 minutes). Inform stakeholders.
2. **Apply SQL migration:**
   - Execute the validated SQL script on production in a transaction:
     - Rename columns.
     - Add new columns and defaults.
     - Create `anonymous_usage` table and indexes.
     - Update Alembic version table to `b73c9aa4f0c3`.
3. **Deploy API revision:**
   - Redeploy the API build that removes schema-fallback logic (future commit after success).
4. **Post-migration tests:**
   - Run `/api/healthz`, `/api/me`, `/api/checks/run` (anonymous + authenticated).
   - Confirm usage is incremented in `anonymous_usage` and `usage_ledger`.
   - Check that `checks` rows contain new fields (claim, config JSON, gate flags).

## Phase 4 — Verification & Cleanup
1. **Analytics validation:**
   - Export fresh production data (via `hx export checks`); run DuckDB queries combining local and prod.
2. **Monitoring:**
   - Enable alerts for insert failures or DB errors for the next 24 hours.
3. **Documentation:**
   - Update `database-schema.md` to reflect unified schema.
   - Note the migration in `CHANGELOG`/internal release notes.
4. **Remove fallback code:**
   - Once confidence is high, delete the error-handling path in `api/main.py` that increments usage on schema failure.

## Rollback Plan
- Restore the Neon backup (pg_restore) if critical failures occur.
- Redeploy the previous API revision that tolerates schema mismatches.
- Notify stakeholders of rollback status.

## Open Questions / Follow-ups
- Do we need to backfill PQS and gate flags for historical rows? If yes, schedule a separate job to compute them from stored JSON.
- Decide whether to retain legacy columns (`aggregation`, `diagnostics`) for audit or drop them after migration.
- Ensure CI workflows include applying migrations to a Neon dev branch before production.

