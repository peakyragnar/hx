# Heretix RPL — Database Schema (SQLite)

This document describes the SQLite schema used by the Heretix RPL harness. The database file lives at `runs/heretix.sqlite`.

Tables:
- `runs`: One row per unique run (identified by `run_id`). Stores the latest aggregate metrics for that run_id plus serialized config/sampler diagnostics.
- `samples`: One row per sample attempt (identified by `cache_key`). Holds per‑sample outputs and validity flags, linked to `runs` via `run_id`.
- `executions`: Immutable snapshot per invocation (identified by `execution_id`). Every run invocation appends one row, even when re‑running the same `run_id`.
- `execution_samples`: Link table mapping which cached `samples` were used by a given `execution_id` (valid/compliant only).

Primary relationships:
- `samples.run_id` → `runs.run_id` (FK)
- `executions.run_id` → `runs.run_id` (FK)
- `execution_samples.cache_key` → `samples.cache_key` (FK)
- `execution_samples.execution_id` → `executions.execution_id` (FK)

Indexes:
- `idx_runs_prompt_model` on `runs(prompt_version, model)`
- `idx_samples_run` on `samples(run_id)`
- `idx_exec_run` on `executions(run_id)`

---

## Table: runs
One row per unique `run_id` (hash of claim | model | prompt_version_full | K | R). Re‑running the same `run_id` updates this row, but a new immutable row is always added to `executions`.

Columns
- `run_id`: Stable identifier for the run (string; PRIMARY KEY).
- `created_at`: UNIX epoch seconds when this aggregate row was written.
- `claim`: Claim text for the run.
- `model`: Provider model name (e.g., `gpt-5`).
- `prompt_version`: Full prompt version string from YAML (e.g., `rpl_g5_v2_2025-08-29`).
- `K`: Number of paraphrase slots used.
- `R`: Replicates per slot.
- `T`: Number of templates included from the bank.
- `B`: Bootstrap resamples used in aggregation.
- `seed`: Configured bootstrap seed (stringified) if present.
- `bootstrap_seed`: Effective bootstrap seed used (stringified).
- `prob_true_rpl`: Aggregated probability (p_RPL) in probability space.
- `ci_lo`: Lower bound of 95% bootstrap CI (probability space).
- `ci_hi`: Upper bound of 95% bootstrap CI (probability space).
- `ci_width`: CI width (`ci_hi - ci_lo`).
- `template_iqr_logit`: Interquartile range of per‑template means (logit space).
- `stability_score`: Stability metric derived from template IQR (higher is better).
- `imbalance_ratio`: Max/min counts across selected templates.
- `rpl_compliance_rate`: Fraction of attempted samples that were strict JSON and contained no URLs/citations.
- `cache_hit_rate`: Fraction of attempted samples served from cache.
- `config_json`: JSON dump of effective `RunConfig` used (diagnostic/audit).
- `sampler_json`: JSON of sampler planning (e.g., `T_bank`, `T`, `seq`, `tpl_indices`).
- `counts_by_template_json`: JSON map of `prompt_sha256` → count from aggregation diagnostics.
- `artifact_json_path`: Path to the JSON artifact written by the CLI for this run, if any.
- `prompt_char_len_max`: Maximum composed prompt character length among selected templates (system + schema + user text).

---

## Table: samples
One row per sample attempt (PRIMARY KEY `cache_key`). Reused across executions when cache hits occur.

Columns
- `run_id`: Associated run identifier (FK to `runs.run_id`).
- `cache_key`: Deterministic sample key including claim, model, prompt_version, prompt_sha256, replicate index, and decode knobs (PRIMARY KEY).
- `prompt_sha256`: Hash of composed instructions + user text for the template occurrence.
- `paraphrase_idx`: Index of the paraphrase template in the selected set.
- `replicate_idx`: Global replicate index for that template occurrence (unique per slot × replicate).
- `prob_true`: Parsed probability from provider output for this sample (nullable if invalid).
- `logit`: Logit of `prob_true` (nullable if invalid).
- `provider_model_id`: Exact provider model id returned, if available.
- `response_id`: Provider response identifier, if available.
- `created_at`: UNIX epoch seconds when the sample row was inserted.
- `tokens_out`: Tokens generated in the response (if tracked; may be null).
- `latency_ms`: Latency of the call in milliseconds (0 if mock or unavailable).
- `json_valid`: 1 if sample passed strict JSON and no‑URL policy; 0 otherwise.

---

## Table: executions
Immutable per‑invocation summary (PRIMARY KEY `execution_id`). Each run invocation emits exactly one `executions` row and links to the valid samples used.

Columns
- `execution_id`: Unique identifier for the invocation (string; PRIMARY KEY).
- `run_id`: Logical run identifier (FK to `runs.run_id`).
- `created_at`: UNIX epoch seconds when this execution was recorded.
- `claim`: Claim text for this execution.
- `model`: Provider model name.
- `prompt_version`: Full prompt version string from YAML.
- `K`: Paraphrase slots used.
- `R`: Replicates per slot.
- `T`: Number of templates included from the bank.
- `B`: Bootstrap resamples used.
- `seed`: Configured bootstrap seed (stringified) if present.
- `bootstrap_seed`: Effective bootstrap seed used (stringified).
- `prob_true_rpl`: Aggregated probability (p_RPL) for this execution.
- `ci_lo`: Lower bound of 95% bootstrap CI.
- `ci_hi`: Upper bound of 95% bootstrap CI.
- `ci_width`: CI width (`ci_hi - ci_lo`).
- `template_iqr_logit`: Interquartile range of per‑template means (logit space).
- `stability_score`: Stability metric for this execution.
- `imbalance_ratio`: Max/min counts across selected templates.
- `rpl_compliance_rate`: Fraction of attempted samples that were strict JSON and contained no URLs/citations.
- `cache_hit_rate`: Fraction of attempted samples served from cache.
- `config_json`: JSON dump of effective `RunConfig` used.
- `sampler_json`: JSON of sampler planning (`T_bank`, `T`, `seq`, `tpl_indices`).
- `counts_by_template_json`: JSON map of `prompt_sha256` → count from aggregation diagnostics.
- `artifact_json_path`: Path to the JSON artifact written by the CLI for this run, if any.
- `prompt_char_len_max`: Maximum composed prompt character length among selected templates.

---

## Table: execution_samples
Maps an `execution_id` to the exact cached samples used for that execution (valid/compliant only). Useful for full provenance and audit.

Columns
- `execution_id`: Execution identifier (FK to `executions.execution_id`).
- `cache_key`: Sample cache key (FK to `samples.cache_key`).

---

Notes
- Schema evolution: New columns may be added via `ALTER TABLE` (e.g., `prompt_char_len_max`). Existing rows will have nulls for newly added columns until updated.
- Data retention: `executions` preserves the full run history, even when `runs` is updated for the same `run_id`.
- Provenance: Prompt identity is the YAML `version` string stored as `prompt_version`; sample identity includes `prompt_sha256` of the composed instructions + user text.


*******Runs vs Executions
Here’s the simple, practical split.

Why keep both

- runs (overwrite): Single “latest result per configuration.” Fast to query, one row per run_id. Ideal for current-state views and cohort comparisons.
- executions (append-only): Full history, one row per time you ran. Ideal for audit, time series, and debugging variance.

Use runs when

- You want the latest p_RPL, CI, stability for a specific config (claim+model+prompt_version+K/R).
- You’re doing A/B or cohort compares and need one canonical row per version.
- You’re building a “current leaderboard” of prompts (no duplicates).
- You want the artifact path and current aggregates without paging through history.

Use executions when

- You need history: how the same config performed over time (trend of CI width, stability, compliance, PQS).
- You’re auditing exactly what happened in a specific invocation (bootstrap_seed, prompt lengths).
- You need provenance to samples: join via execution_samples → samples to see which cached rows were used.
- You’re diagnosing anomalies (e.g., a bad compliance run), or comparing seeds or provider behavior changes.

Mental model

- runs = latest snapshot per config (easy, de-duplicated).
- executions = every button press (complete timeline + provenance).

You always get both on every run: we update runs for the config’s latest state and append a new executions record so your history is never lost.

********Sample:
- What a sample is: One model call for one template slot + one replicate on your claim.
- What gets cached: Each sample’s result is stored with a precise key (claim, model, prompt version text, the resolved template text, replicate index,
etc.).
- When it reuses: If you re‑run with the exact same inputs (claim, model, prompt content, K/R mapping to the same replicate index, and decode knobs), the
run reuses those cached samples — no new provider cost.
- When it doesn’t: Any change to claim, prompt text (system/user/paraphrases), prompt_version, K/R that shifts replicate indexing, or max_output_tokens →
cache miss for the changed parts only.
- Invalid samples: Still stored, but excluded from aggregation; compliance rate reflects how many passed.
- Rerun effect: Reused samples give the same p_RPL inputs; CI can shift slightly if you change the bootstrap seed, but you won’t pay for new calls when
cache hits.

Short example

- First run (K=18, R=3, T=8): ~54 samples stored.
- Second run with identical settings: reads the same ~54 from cache; only recomputes the summary stats (fast, no extra cost).


*******Templates: 
- config_json tells you the knobs (what you asked for).
- sampler_json tells you the planned/actual template selection (what was run).
- counts_by_template_json tells you realized valid counts per template (what made it into aggregation) — key for interpreting CI width and stability.