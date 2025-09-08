# Heretix (New Harness) — System Flow

This document explains how the new, clean Heretix RPL harness fits together, how a run proceeds end-to-end, and where each responsibility lives. It reflects the refactor plan (uv-first, clean package, legacy quarantined).

## Overview
- Package: `heretix/` (install target). Legacy is quarantined under `legacy/` and excluded from install.
- Tooling: uv only. Setup with `uv sync`. Run with `uv run heretix ...`.
- Entry point: `heretix=heretix.cli:main`.
- Storage: SQLite at `runs/heretix.sqlite` (created on first run). JSON output written to `--out` when requested.
- Invariants: Frozen estimator (logit, equal-by-template, 20% trim, cluster bootstrap B=5000 with deterministic seed).

## Repository Structure (New Harness)
- `heretix/` — Clean harness
  - `cli.py` — Typer CLI (`run`, Phase 2 will add `view`)
  - `config.py` — `RunConfig` + loader (YAML/JSON, env overrides)
  - `prompts/` — YAML prompt versions (e.g., `rpl_g5_v2.yaml`)
  - `sampler.py` — Deterministic balanced rotation; counts/imbalance utilities
  - `provider/openai_gpt5.py` — GPT-5 Responses adapter (`score_claim()`)
  - `aggregate.py` — Frozen clustered estimator
  - `metrics.py` — Stability score + banding from IQR(logit)
  - `seed.py` — Deterministic seed derivation for bootstrap CI
  - `cache.py` — Deterministic sample cache keys, cache fetch via storage
  - `storage.py` — SQLite schema (`runs`, `samples`), insert/get helpers
  - `rpl.py` — Single-version engine (sampling, compliance, aggregation, persistence)
- `legacy/` — Archived code, not installed or imported by the new harness
- `runs/` — New harness outputs (SQLite DB, new run JSONs). Legacy artifacts moved to `legacy/runs_archive/`.

## Run Flow (Single Version)
1) CLI entry (`heretix run`)
- Loads `.env` and validates `OPENAI_API_KEY`.
- Loads `RunConfig` from `--config` (YAML/JSON). Optional `--prompt-version` list triggers multi-version A/B.

2) Load prompts (YAML)
- Reads `heretix/prompts/<prompt_version>.yaml`:
  - `version`: full version string (e.g., `rpl_g5_v2_2025-08-21`)
  - `system`: system instructions (RPL rules)
  - `user_template`: claim wrapper and schema reminder
  - `paraphrases[]`: 16 neutral templates

3) Deterministic sampling
- Compute rotation offset: `sha256(claim|model|prompt_version)`.
- Rotate the template bank once and pick `T` (subset) from the front.
- Build a length-`K` sequence with `balanced_indices_with_rotation(T, K, offset=0)` for equal counts across the chosen `T`.
- Planned counts and imbalance are recorded.

4) Per-sample loop (templates × replicates)
- For each K slot and each replicate r∈[0..R-1]:
  - Compose the full prompt (system + schema instructions, user paraphrase + template).
  - Compute `prompt_sha256` = sha256(full instructions + user_text). This keys paraphrase clusters.
  - Build cache key: sha256(`claim|model|prompt_version|prompt_sha256|replicate_idx|max_output_tokens`).
  - If cache enabled and hit, reuse. Else call provider:
    - `provider.openai_gpt5.score_claim()` calls Responses API with reasoning-effort feature detection (retry without if unsupported), parses strict JSON, captures latency.
  - Compliance/validation: require JSON-only prob_true, and “no citations/URLs” in any text fields. Mark `json_valid` accordingly; only valid/compliant samples are aggregated.

5) Aggregation (frozen)
- Deterministic seed: `HERETIX_RPL_SEED` or derived via `seed.make_bootstrap_seed(...)` from `(claim, model, prompt_version, K, R, sorted(template_hashes), center=trimmed, trim=0.2, B)`.
- Equal-by-template aggregation in logit space with 20% trimmed center; cluster bootstrap (B=5000) produces CI95.
- Convert to probability space (p, CI95). Compute IQR(logit) and stability score/band.
- Diagnostics: `counts_by_template`, `imbalance_ratio`, `template_iqr_logit`.
- Run-level metrics: `cache_hit_rate`, `rpl_compliance_rate` (valid/compliant ÷ attempted).

6) Persistence
- Samples: write `samples` rows (run_id, cache_key, prompt_sha256, paraphrase_idx, replicate_idx, prob_true, logit, provider_model_id, response_id, created_at, tokens_out?, latency_ms, json_valid).
- Run: write `runs` row (aggregates, seeds, counts/imbalance, stability, compliance/cache rates, JSON blobs for config/sampler/counts).
- Output: CLI prints compact A/B table; full result JSON written to `--out` (if provided).

## Determinism & Reproducibility
- CI bootstrap is deterministic given inputs; set `HERETIX_RPL_SEED` to reproduce CI95 exactly (model outputs remain stochastic).
- Seed derivation includes sorted unique `prompt_sha256` to be order-invariant.
- Cache keys include `prompt_version` and `prompt_sha256`; prompt edits naturally bust cache.

## CLI Usage
- Setup environment:
```
uv sync
```
- Minimal config (example):
```
cat > runs/rpl_example.yaml << 'EOF'
claim: "tariffs don't cause inflation"
model: gpt-5
prompt_version: rpl_g5_v2
K: 8
R: 2
T: 8
B: 5000
max_output_tokens: 1024
EOF
```
- Run:
```
export OPENAI_API_KEY=sk-...
uv run heretix run --config runs/rpl_example.yaml --out runs/new_rpl.json
```
- Deterministic CI (bootstrap only):
```
HERETIX_RPL_SEED=42 uv run heretix run --config runs/rpl_example.yaml
```

## Outputs (Fields)
- Aggregates: `prob_true_rpl`, `ci95`, `ci_width`, `stability_score`, `stability_band`, `rpl_compliance_rate`, `cache_hit_rate`.
- Aggregation meta: `method`, `B`, `center`, `trim`, `bootstrap_seed`, `n_templates`, `counts_by_template`, `imbalance_ratio`, `template_iqr_logit`.
- Persistence: one row in `runs`, many rows in `samples` (plus optional JSON artifact via `--out`).

## Extensibility (Next Phases)
- Phase 2: `heretix view` with `inspect|compare|weekly` modes, strict parity checks for A/B, drift summaries.
- Phase 3: Auto‑RPL preset (`uv run heretix run --preset auto`) implementing frozen stages/gates with deterministic sample reuse; provider adapter stubs for Anthropic/DeepSeek with knob normalization policies.

## File Map (New Harness)
- `heretix/cli.py` — CLI entry
- `heretix/config.py` — RunConfig + loader
- `heretix/prompts/rpl_g5_v2.yaml` — current prompt bank
- `heretix/sampler.py` — deterministic selection + counts
- `heretix/provider/openai_gpt5.py` — GPT‑5 adapter
- `heretix/aggregate.py` — frozen estimator
- `heretix/metrics.py` — stability functions
- `heretix/seed.py` — bootstrap seed derivation
- `heretix/cache.py` — cache key and fetch
- `heretix/storage.py` — SQLite schema and helpers
- `heretix/rpl.py` — single-version RPL engine
