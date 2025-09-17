# Database Schemas Overview

This document summarizes the schema for each storage layer in the Heretix stack.

---

## 1. SQLite (Phase‑1 RPL Harness)

Location: `runs/heretix.sqlite`

Purpose: Current production of the Phase‑1 harness; stores all run and sample data for the CLI/tests.

Schema:
- **runs**
  - `run_id TEXT PRIMARY KEY`
  - `created_at INTEGER`
  - `claim TEXT`
  - `model TEXT`
  - `prompt_version TEXT`
  - `K INTEGER`
  - `R INTEGER`
  - `T INTEGER`
  - `B INTEGER`
  - `seed INTEGER`
  - `bootstrap_seed INTEGER`
  - `prob_true_rpl REAL`
  - `ci_lo REAL`
  - `ci_hi REAL`
  - `ci_width REAL`
  - `template_iqr_logit REAL`
  - `stability_score REAL`
  - `imbalance_ratio REAL`
  - `rpl_compliance_rate REAL`
  - `cache_hit_rate REAL`
  - `config_json TEXT`
  - `sampler_json TEXT`
  - `counts_by_template_json TEXT`
  - `artifact_json_path TEXT`
  - `prompt_char_len_max INTEGER`
  - `pqs INTEGER`
  - `gate_compliance_ok INTEGER`
  - `gate_stability_ok INTEGER`
  - `gate_precision_ok INTEGER`
  - `pqs_version TEXT`
- **samples**
  - `run_id TEXT`
  - `cache_key TEXT PRIMARY KEY`
  - `prompt_sha256 TEXT`
  - `paraphrase_idx INTEGER`
  - `replicate_idx INTEGER`
  - `prob_true REAL`
  - `logit REAL`
  - `provider_model_id TEXT`
  - `response_id TEXT`
  - `created_at INTEGER`
  - `tokens_out INTEGER`
  - `latency_ms REAL`
  - `json_valid INTEGER`

---

## 2. Local Postgres (Docker @ port 5433)

Connection: `postgresql+psycopg://heretix:heretix@localhost:5433/heretix`

Purpose: Mirrors the production schema for development and integration tests. Tables created via Alembic migration `9e15719c5c3c`.

Schema (`public` schema):
- **users** (`id UUID PK`, `email TEXT UNIQUE`, `plan TEXT`, `status TEXT`, timestamps)
- **sessions** (UUID PK, FK → users, `expires_at`, `user_agent`)
- **email_tokens** (UUID PK, FK → users, `selector` unique, `verifier_hash`, `expires_at`, `consumed_at`)
- **checks** (UUID PK, `run_id` UNIQUE, `env`, optional `user_id`, `claim`, `claim_hash`, `model`, `prompt_version`, `K`, `R`, `T`, `B`, `seed`, `bootstrap_seed`, `max_output_tokens`, `prob_true_rpl`, `ci_lo`, `ci_hi`, `ci_width`, `template_iqr_logit`, `stability_score`, `imbalance_ratio`, `rpl_compliance_rate`, `cache_hit_rate`, `config_json`, `sampler_json`, `counts_by_template_json`, `artifact_json_path`, `prompt_char_len_max`, `pqs`, gate flags, `pqs_version`, `was_cached`, `provider_model_id`, `created_at`, `finished_at`; indexes on `user_id`, `env`, `claim_hash`)
- **usage_ledger** (UUID PK, FK → users, `period_start`, `period_end`, `plan`, `checks_allowed`, `checks_used`, timestamp; unique per user+period)
- **result_cache** (UUID PK, `result_key` UNIQUE, `run_id`, `env`, optional `user_id`, `payload JSONB`, timestamps)
- **alembic_version** (migration tracking)

---

## 3. Neon Postgres (Production)

Connection: `postgresql+psycopg://…?sslmode=require&channel_binding=require`

Purpose: Serverless Postgres for the deployed application. Schema identical to local Postgres.

Schema: identical to the tables listed above under Local Postgres (same columns, constraints, indexes).

---

## Notes
- SQLite remains the operational store for Phase‑1 harness runs until the new app is live.
- Local Postgres and Neon share the same migration history; Alembic migrations must be applied to both to keep them in sync.
- Analytics will read from exported Parquet files that unify data from SQLite and Postgres (`env=local` vs `env=prod`).
