# Heretix RPL Refactor Plan — Simplification & Optimization

## Objective
- Build a lean, auditable RPL harness that makes variables easy to toggle, persists all inputs/outputs, enables fast A/B of prompt versions and models, and preserves the frozen estimator and RPL policy.

## Tooling (uv) & Dev Workflow
- Package manager and runner: uv (do not use venv/pip/poetry).
- Setup environment: `uv sync` (creates venv and installs deps from `pyproject.toml`/`uv.lock`).
- Run commands: always prefix with `uv run`.
  - Examples:
    - `uv run heretix run --config runs/claim.yaml`
    - `uv run heretix view --run RUN_ID --mode inspect`
    - `uv run pytest -q`
- Dependency changes: prefer `uv add <package>` (or edit `pyproject.toml` then `uv lock && uv sync`).
- Environment variables:
  - `OPENAI_API_KEY` required (use `.env` or shell export).
  - Optional: `HERETIX_RPL_SEED` (fix bootstrap CI), `HERETIX_RPL_NO_CACHE=1` (bypass cache).
- Safety rail: Do not switch tooling; all docs/CI/scripts assume `uv`.

## Guardrails (Invariants)
- Estimator (frozen): logit-space aggregation, equal-by-template weighting, 20% trimmed center (T≥5), cluster bootstrap (B=5000) with deterministic seed.
- RPL policy: no retrieval/citations; strict JSON outputs; feature-detect API quirks and fall back safely.
- Change control: any change to estimator math or Auto‑RPL stages/gates requires explicit approval and a version bump.

## Scope (This Pass)
- RPL only. MEL/HEL/SEL will reuse the harness later via adapters and retrieval policy without changing estimator math.
- Provider scope: GPT‑5‑only for Phases 1–2 to maximize speed and reproducibility; keep an adapter seam for future providers.

## Provider Strategy (GPT‑5‑Only First)
- Implement only GPT‑5 in Phases 1–2. This minimizes code paths, enforces RPL policy consistently, and simplifies deterministic caching.
- Keep `model` in RunConfig, DB rows, and cache keys from day one.
- Define a uniform adapter interface now; add Anthropic/DeepSeek stubs in Phase 3.
- When adding new models later, either lock stochastic knobs (e.g., temperature=0 if supported) or define a minimal normalization policy so runs remain comparable.

## Apply The Algorithm
- Question: keep only factors that affect p_RPL, CI, stability.
- Delete: redundant CLIs, legacy aggregators, scattered defaults.
- Simplify: one RunConfig, one sampler, one estimator, simple storage.
- Accelerate: deterministic rotation, sample caching, bounded concurrency, fast A/B.
- Automate: Auto‑RPL as a preset (cost control) and weekly sentinel summaries via a unified view.
- Integrate simple, high‑value metrics into the core: expose RPL compliance rate and cache hit rate in aggregates; enforce hard parity checks in compare mode.

## Paraphrase Iteration (First‑Class)
- Paraphrase bank in `prompts/<prompt_version>.yaml` as a flat list (editable).
- Selection control via RunConfig: explicit T subset and K with deterministic rotation.
- Provenance-safe caching: cache key includes `prompt_version` and `prompt_sha256`; paraphrase text changes produce new keys.
- Diagnostics in `view --mode inspect`: per‑template means, counts, imbalance, length metrics to identify flaky/sensitive paraphrases.

## Target Architecture
- core/config: RunConfig (claim, model, prompt_version, K/R/T, B, seed, decode knobs).
- core/prompts: system, user_template, paraphrases; versioned YAML (e.g., `prompts/rpl_g5_v2.yaml`).
- core/sampler: deterministic balanced rotation by `sha256(claim|model|prompt_version)`; explicit T subset; equal counts.
- core/provider: adapters with uniform `score_claim()` interface (OpenAI GPT‑5 now; Anthropic/DeepSeek stubs later).
  - Phases 1–2: only GPT‑5 adapter is active.
  - Phase 3: add provider stubs and wire compare UX (strict config parity required).
- core/aggregate: frozen clustered estimator (no alternatives).
- core/storage: SQLite with normalized columns + JSON blobs.
- core/cache: deterministic sample reuse keyed by `(claim|model|prompt_version|prompt_sha256|replicate_idx|max_output_tokens)`.
- cli: `run` (single), `view` (inspect/compare/weekly), `sweep` (optional, Phase 3).

## Repository Structure (New Branch)
- New package (install target): `heretix/` only.
  - `heretix/__init__.py`
  - `heretix/config.py` (RunConfig + loader)
  - `heretix/prompts/` (YAML prompt versions, e.g., `rpl_g5_v2.yaml`)
  - `heretix/sampler.py` (deterministic balanced rotation)
  - `heretix/provider/` (`openai_gpt5.py`, `__init__.py`)
  - `heretix/aggregate.py` (wraps frozen clustered estimator)
  - `heretix/cache.py` (sample cache)
  - `heretix/storage.py` (SQLite schema + JSON I/O)
  - `heretix/rpl.py` (single-run engine)
  - `heretix/auto_preset.py` (Auto‑RPL preset; Phase 3)
  - `heretix/view/` (`inspect.py`, `compare.py`, `weekly.py`)
  - `heretix/cli.py` (Typer app: `run`, `view`, later `--preset auto`)
- Legacy quarantine (not installed by default): `legacy/`
  - `legacy/heretix_rpl/`, `legacy/heretix_promptstudio/`, `legacy/tests/`
- Tests for new package: `heretix/tests/` (unit + integration), run via `uv run pytest -q`.
- Packaging (pyproject):
  - Expose only `heretix` as a package and console script `heretix=heretix.cli:app`.
  - Exclude `legacy/` from install and discovery (keeps runtime/import space clean).

Repository hygiene rules:
- New code MUST NOT import from `legacy/`.
- Keep file names and module names concise; avoid overlapping names with legacy (e.g., no `heretix_rpl` in new code).
- Document new CLI and modules in README; mark legacy as archived.

## CLI (Minimal)
- `uv run heretix run --config runs/claim.yaml [--prompt-version v1 [v2 v3]]`
  - Single run; if multiple prompt versions are provided, run each and print a compact A/B table; persist each run.
- `uv run heretix view --run RUN_ID --mode inspect|compare|weekly`
  - inspect: per‑template means (prob), CI strip, counts/imbalance, prompt lengths.
  - compare: p/CI/stability across prompt versions or models with hard parity checks (identical RunConfig except compared dimension); fail fast with a clear message if parity is violated.
  - weekly: sentinel summary and drift flags from DB/JSONL.
- `uv run heretix sweep` (optional, Phase 3)
  - Grid exploration over K/R/T/prompt_version only if needed beyond multi‑version `run`.

## Sample Cache
- Key: `sha256(f"{claim}|{model}|{prompt_version}|{prompt_sha256}|{replicate_idx}|{max_output_tokens}")`.
- Policy: manual bust only via `--no-cache` or `HERETIX_RPL_NO_CACHE=1` (no auto‑invalidation).
- Payload: store cache_key, validity flag, tokens_out, latency_ms, provider fields, and full raw JSON.
- Provenance & Metrics: log cache hits per sample and surface `cache_hit_rate` per run in aggregates and diagnostics.

## Storage Schema (Two Tables)
- runs
  - Keys: `run_id`, `created_at`, `claim`, `model`, `prompt_version`, `K`, `R`, `T`, `B`, `seed`, `bootstrap_seed`.
  - Aggregates: `prob_true_rpl`, `ci_lo`, `ci_hi`, `ci_width`, `template_iqr_logit`, `stability_score`, `imbalance_ratio`, `rpl_compliance_rate`, `cache_hit_rate`.
  - JSON: `config_json`, `sampler_json`, `counts_by_template_json`, `artifact_json_path`.
  - Indexes: `(prompt_version, model)`.
- samples
  - `run_id`, `cache_key`, `prompt_sha256`, `paraphrase_idx`, `replicate_idx`, `prob_true`, `logit`, `provider_model_id`, `response_id`, `created_at`, `tokens_out`, `latency_ms`, `json_valid`.
  - Indexes: `(run_id)`, `(cache_key)`.

## Prompts & Versions
- YAML files in `prompts/<prompt_version>.yaml` with `system`, `user_template`, `paraphrases[]`.
- Prompt length metrics (chars/tokens) computed and stored for system, user template, and paraphrases.
- Prompt testing (deferred): may add `tests: [{claim, expected:[lo,hi]}]` to YAML and a gating view mode later if needed; omitted now to keep CLI minimal.

## RPL Policy Enforcement
- No retrieval/citations: validate outputs; drop offending samples; record counts in diagnostics.
- Strict JSON parsing: fail samples on parse; require ≥3 valid samples per run; report validity rate.
 - Aggregated compliance: expose `rpl_compliance_rate` = compliant_valid_samples / total_attempted in aggregates.

## Back‑Compat & Migration
- Start fresh with the new schema; archive old artifacts; optional one‑off importer to load prior JSON into `runs`/`samples_archive`.
- CLI aliases: keep legacy verbs for one release, forwarding to `view` modes with deprecation notices.

## Error Handling & Determinism
- Retries: exponential backoff on API errors; log retry counts; mark `json_valid=0` if exhausted.
- Deterministic bootstrap: `HERETIX_RPL_SEED` for CI reproducibility; same inputs → same CI and preset decisions.

## Success Metrics (Defined Upfront)
- 10× faster iteration on prompt changes (cache + A/B in `run`).
- 70% fewer lines of operational code around the estimator.
- Single command produces prompt‑version A/B table (via `uv run heretix run ...`).
- All variables in a single config; sub‑second queries for historical runs by DB index.
- Install footprint contains only `heretix` (no `legacy` in installed package or PATH).
- No imports from `legacy/` in `heretix/` (enforced by CI grep check).

## Deletions & Decisions
- Immediate deletions: remove `aggregate_simple()`; deprecate `inspect.py`, `monitor.py`, `summarize.py` (fold into `view`).
- Auto‑RPL: keep as a preset implemented atop `run` (frozen stages/gates, deterministic reuse, decision_log). Do not delete `orchestrator.py` until preset lands; then remove separate `auto` CLI entry (pending approval).

## Phased Plan (Compressed)

### Phase 1 — Core (1 week, GPT‑5‑only)
- Deliverables:
  - RunConfig (single source of truth).
  - SQLite storage (runs/samples) + full artifact JSON; indexes in place.
  - Deterministic sample cache with provenance; manual `--no-cache` flag.
  - Single run path using frozen estimator and deterministic sampler.
- Approvals needed: DB schema; cache policy; CLI `run` contract.

### Phase 2 — Acceleration (3–4 days, GPT‑5‑only)
- Deliverables:
  - `uv run heretix view` with modes: inspect, compare, weekly; minimal plots (per‑template means, CI strip; CI vs K and IQR vs T when applicable).
  - Prompt versioning via YAML; surface in view/compare; store lengths.
  - Deprecate old commands; add aliases; migration notes.
- Approvals needed: CLI merge; deprecation plan.

### Phase 3 — Polish (3–4 days, introduce multi‑model)
- Deliverables:
  - Auto‑RPL preset under `uv run heretix run --preset auto`; deterministic sample reuse; decision_log emission.
  - Provider adapter stubs (Anthropic/DeepSeek) with uniform interface; keep decode knobs normalized for comparability.
  - Optional `uv run heretix sweep` for K/R/T/prompt_version grids if needed beyond multi‑version `run`.
  - Documentation: operator guide (run/view), stats spec, schema and migration notes.
- Approvals needed: Auto‑RPL preset adoption; optional sweep scope.

## Acceptance Criteria
- `uv run heretix run` with one or multiple `--prompt-version` persists runs, prints p/CI/stability, and emits a comparison table (GPT‑5); aggregates include `rpl_compliance_rate` and `cache_hit_rate`.
- `uv run heretix view --mode inspect|compare|weekly` replaces legacy verbs; renders minimal plots and drift summaries (GPT‑5); compare mode enforces hard parity checks.
- `pyproject.toml` publishes only `heretix` and the `heretix` console script; `legacy/` is excluded from build.
- CI check: ensure no `from legacy`/`from heretix_rpl` imports inside `heretix/`.
- Sample cache shows meaningful hit rate on repeated claims/version runs; cache provenance included (GPT‑5), and `cache_hit_rate` is shown in aggregates.
- Auto‑RPL preset reproduces frozen stages/gates with deterministic reuse and decision_log; no estimator/math changes.
- Phase 3: provider stubs added; cross‑model compare requires strict config parity and knob normalization policy.

## Appendix: RunConfig (Indicative Fields)
- claim, model, prompt_version, K, R, T, B, seed, max_output_tokens, sampler rotation offset (derived), prompt file path.

## Appendix: Outputs (Indicative)
- Aggregates: prob_true_rpl, ci95, ci_width, template_iqr_logit, stability_score, counts_by_template, imbalance_ratio, bootstrap_seed, rpl_compliance_rate, cache_hit_rate.
- Provenance: provider_model_id, prompt_sha256, prompt lengths, cache hit metrics.
