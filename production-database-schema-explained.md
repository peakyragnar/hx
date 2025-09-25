# Production Database Schema Explained

This note summarizes the structure of the production Postgres database (Neon) backing the Heretix RPL harness. It covers every table in the `public` schema, the meaning of each column, and how identifiers connect records across tables.

## Global Identifiers and Relationships
- `users.id` is the canonical user identifier. It is referenced by `checks.user_id`, `sessions.user_id`, `email_tokens.user_id`, `result_cache.user_id`, and `usage_ledger.user_id`.
- `checks.run_id` stores the human-readable/CLI run identifier (for example `heretix-rpl-5fc12dc6a9a4`). The `public.checks` table enforces uniqueness on `run_id`, and the same value is copied into `result_cache.run_id` to link cached payloads back to a specific run.
- `anonymous_usage.token` provides usage accounting for anonymous flows. When a check is performed without an authenticated user, the chosen token is written to `checks.anon_token` so consumption can be reconciled later.
- Rows that represent actions or derived data (checks, cached results, usage ledgers, sessions, tokens) record their own UUID primary key (`id`) in addition to any foreign keys.

---

## Table: `alembic_version`
**Purpose**: Tracks which schema migration revision has been applied.

| Column | Type | Meaning |
| --- | --- | --- |
| `version_num` | `varchar` | Primary key. Stores the latest Alembic revision hash that has been applied to the database. The migration tooling updates this row automatically.

---

## Table: `users`
**Purpose**: Canonical directory of authenticated users.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `uuid` | Primary key. Stable identifier for each user across the application.
| `email` | `varchar` | Unique email address used for login and communication.
| `plan` | `varchar` | Current plan tier (default `trial`). Used to determine allowances and billing logic.
| `status` | `varchar` | Lifecycle state (default `active`). Allows suspending or deactivating users without deleting the record.
| `created_at` | `timestamptz` | Timestamp when the account was created.
| `updated_at` | `timestamptz` | Timestamp of the latest account update.
| `stripe_customer_id` | `varchar` | Optional Stripe customer reference for billing.
| `stripe_subscription_id` | `varchar` | Optional Stripe subscription reference.
| `billing_anchor` | `date` | Optional anchor date for usage/billing cycles.

**Key facts**: `email` has a unique constraint. Other tables reference `users.id` to tie events to an account.

---

## Table: `sessions`
**Purpose**: Tracks active web sessions for authenticated users.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `uuid` | Primary key for the session record.
| `user_id` | `uuid` | Foreign key to `users.id`. Identifies who owns the session.
| `created_at` | `timestamptz` | When the session was created.
| `last_seen_at` | `timestamptz` | Last activity heartbeat.
| `expires_at` | `timestamptz` | When the session becomes invalid.
| `user_agent` | `varchar` | Optional user agent string for logging and security.

**Key facts**: The session uuid is unique per browser/device login. Deleting a user cascades session invalidation because of the foreign key.

---

## Table: `email_tokens`
**Purpose**: Stores magic-link / verification tokens sent via email.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `uuid` | Primary key for the token record.
| `user_id` | `uuid` | Foreign key to `users.id`. Identifies which user the token is for.
| `selector` | `varchar` | Unique short identifier included in emails to find the row quickly.
| `verifier_hash` | `varchar` | Hash of the secret verifier. The raw token is only sent to the user.
| `created_at` | `timestamptz` | When the token was issued.
| `expires_at` | `timestamptz` | When the token becomes invalid.
| `consumed_at` | `timestamptz` | When the token was redeemed (nullable while unused).

**Key facts**: `selector` is unique to support lookup without scanning. `user_id` links back to the owning account.

---

## Table: `usage_ledger`
**Purpose**: Records allowance and consumption totals per user and billing period.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `uuid` | Primary key for the ledger entry.
| `user_id` | `uuid` | Foreign key to `users.id`. Owner of the allowance bucket.
| `period_start` | `date` | Inclusive start date of the billing period.
| `period_end` | `date` | Exclusive end date of the billing period.
| `plan` | `varchar` | Plan tier snapshot used when the row was created.
| `checks_allowed` | `bigint` | Allowance of checks for the period.
| `checks_used` | `bigint` | Number of checks consumed so far (defaults to 0).
| `updated_at` | `timestamptz` | Timestamp of the last update.

**Key facts**: Unique constraint on (`user_id`, `period_start`) enforces one ledger row per user per period. Consumption logic increments `checks_used`; automated billing processes reconcile against this table.

---

## Table: `anonymous_usage`
**Purpose**: Tracks allowances for anonymous API usage when no authenticated user exists.

| Column | Type | Meaning |
| --- | --- | --- |
| `token` | `varchar` | Primary key. Token issued to an anonymous client (often stored in a cookie named `heretix_anon`).
| `checks_allowed` | `integer` | Maximum number of checks granted to the token (default 1).
| `checks_used` | `integer` | Number of checks already consumed (default 0).
| `updated_at` | `timestamptz` | Last time this token’s usage was updated.

**Key facts**: `checks.anon_token` copies the token value when an anonymous user executes a run so the allowance can be reconciled.

---

## Table: `checks`
**Purpose**: Primary audit log for every RPL run executed through the harness (mock or live).

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `uuid` | Primary key for the check record (server-generated).
| `user_id` | `uuid` | Optional foreign key to `users.id`. Null when the run was anonymous or system-initiated.
| `env` | `varchar` | Deployment environment label (e.g., `production`, `staging`).
| `run_id` | `varchar` | Unique identifier that the CLI prints and that ties together related artifacts.
| `claim_hash` | `varchar` | Deterministic hash of the claim text for deduplication/analytics.
| `claim` | `text` | Original claim evaluated by the run.
| `model` | `varchar` | Provider model string (e.g., `gpt-5`).
| `prompt_version` | `varchar` | Prompt configuration version used.
| `K` | `bigint` | Number of paraphrase slots requested.
| `R` | `bigint` | Number of replicates per slot.
| `T` | `bigint` | Number of templates sampled (nullable if not specified explicitly).
| `B` | `bigint` | Bootstrap resamples requested (nullable when defaulted).
| `max_output_tokens` | `bigint` | Output token cap applied to the model request.
| `prob_true_rpl` | `double` | Final aggregated probability the claim is true.
| `ci_lo` | `double` | Lower bound of the 95% bootstrap confidence interval.
| `ci_hi` | `double` | Upper bound of the 95% bootstrap confidence interval.
| `stability_score` | `double` | Stability metric (1/(1+IQR) in logit space).
| `imbalance_ratio` | `double` | Ratio of most-sampled to least-sampled prompt template.
| `cache_hit_rate` | `double` | Fraction of samples served from cache during the run.
| `config_json` | `text` | Full serialized run configuration at submission time.
| `counts_by_template_json` | `text` | JSON mapping of `prompt_sha256` to sample counts.
| `was_cached` | `boolean` | True when the run was satisfied entirely from cache.
| `created_at` | `timestamptz` | When the run was initiated.
| `finished_at` | `timestamptz` | When the run completed.
| `provider_model_id` | `varchar` | Raw provider model identifier returned by the API.
| `anon_token` | `varchar` | Anonymous usage token (when no `user_id` is present).
| `seed` | `numeric` | User-configured bootstrap seed (if provided).
| `bootstrap_seed` | `numeric` | Effective deterministic seed used for bootstrapping.
| `ci_width` | `double` | Width of the confidence interval (`ci_hi - ci_lo`).
| `template_iqr_logit` | `double` | Interquartile range of per-template logits.
| `rpl_compliance_rate` | `double` | Fraction of samples that returned compliant JSON with no URLs/citations.
| `sampler_json` | `text` | Snapshot of the sampler plan (typically contains `K`, `R`, `T`).
| `artifact_json_path` | `text` | Path to the persisted output artifact (usually an object store location or path supplied via CLI `--out`).
| `prompt_char_len_max` | `integer` | Maximum composed prompt length observed while composing the run.
| `pqs` | `double` | Prompt Quality Score (if the PQS gate ran).
| `gate_compliance_ok` | `boolean` | Gate flag indicating compliance threshold was met.
| `gate_stability_ok` | `boolean` | Gate flag indicating stability threshold was met.
| `gate_precision_ok` | `boolean` | Gate flag indicating precision requirements were met.
| `pqs_version` | `varchar` | Version of the PQS heuristic used to compute `pqs`.

**Key facts**: `run_id` has a unique constraint (`uq_checks_run_id`). `user_id` is nullable but, when present, enforces referential integrity back to `users`. Rows in `result_cache` piggyback on the same `run_id`.

---

## Table: `result_cache`
**Purpose**: Stores serialized check results so identical requests can return instantly.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `uuid` | Primary key for the cached entry.
| `result_key` | `varchar` | Unique cache key derived from claim/prompt/model parameters.
| `run_id` | `varchar` | Identifier of the run whose output is cached (mirrors `checks.run_id`).
| `env` | `varchar` | Environment the cache entry belongs to (e.g., `production`).
| `user_id` | `uuid` | Optional foreign key to `users.id` (set when cache is scoped per user).
| `payload` | `jsonb` | Full JSON payload returned to clients, including aggregates and diagnostics.
| `created_at` | `timestamptz` | When the cache entry was created.
| `last_used_at` | `timestamptz` | When it was last served.

**Key facts**: `result_key` is globally unique, guarding against duplicate cache rows. `run_id` links back to the check row that produced the payload. If the cache is served for an authenticated user, `user_id` is set so personal caches can be invalidated per account.

---

# Identifier Relationships at a Glance
- **User-centric flow**: `users.id` → referenced by `sessions`, `email_tokens`, `usage_ledger`, `checks`, `result_cache`. These tables all use a UUID primary key (`id`) along with the foreign key.
- **Run-centric flow**: Every CLI/SDK invocation generates a `checks.id` (UUID) and a `checks.run_id` (human-readable). When caching is enabled, the same `run_id` is stored in `result_cache.run_id`, and a deterministic `result_key` allows deduplication of identical parameter combinations.
- **Anonymous flow**: `anonymous_usage.token` enforces allowance. The token value is echoed in `checks.anon_token`, so the system can decrement `checks_used` as runs complete.
- **Billing period flow**: `usage_ledger` pairs (`user_id`, `period_start`) to track allowances. When a check completes, billing code increments `checks_used` either in `usage_ledger` (authenticated user) or `anonymous_usage` (token holder).

This schema ensures that RPL results stay auditably linked to both the user (or anonymous token) that initiated them and the deterministic run metadata capture recorded in `checks`.
