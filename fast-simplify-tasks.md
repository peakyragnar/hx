## Fast Bias Simplification – Context & Goals

- Target: single-claim, 1–3 model bias runs returning per-model `p_true` + short explanation in ≤20s wall time.
- Preserve RPL invariants (logit aggregation, equal-by-template weighting, trimmed center, clustered bootstrap).
- Make the harness profile-driven and multi-model aware, but keep core math and SQLite schema behavior intact.
- Have one canonical `RunResult` shape that:
  - Is produced by the harness for CLI and API.
  - Is stored as JSON (SQLite and Postgres) for auditability.

### Current architecture snapshot (for future sessions)

- Harness & estimator:
  - `heretix/rpl.py:run_single_version` does prompts → sampling → aggregation → SQLite persistence → returns a single-run JSON payload.
  - `heretix/aggregate.py` contains the frozen estimator math (do not change without version bump).
  - `heretix/storage.py` owns the SQLite schema (`runs`, `samples`, `executions`, `execution_samples`, `result_cache`, `prompts`).
- Providers:
  - `heretix/provider/base.py:RPLAdapter` is the current sync provider protocol (`score_claim`).
  - GPT‑5 adapter: `heretix/provider/openai_gpt5.py`; Gemini/Grok live in `heretix/provider/gemini_google.py` and `heretix/provider/grok_xai.py`, all registered via `heretix/provider/registry.py`.
- CLI (local, uses Postgres + harness SQLite):
  - `heretix/cli.py:cmd_run` builds a `RunConfig`, loops over models/versions, and calls `heretix.pipeline.perform_run`.
  - `perform_run` calls `run_single_version` (which writes to SQLite) and also persists to Postgres `checks` via SQLAlchemy models in `heretix/db/models.py`.
  - CLI writes a compact JSON summary via `_build_run_entry`, not the raw `run_single_version` payload.
- API (FastAPI, Postgres):
  - `/api/checks/run` is implemented in `api/main.py:run_check`, taking a single model in `api/schemas.py:RunRequest`.
  - It builds a `RunConfig`, calls `perform_run`, then adds explanations and usage, returning `RunResponse`.
  - Multi-model in the UI is currently achieved by front-end looping over `/api/checks/run`; there is a `Request` parent entity in `heretix/db/models.Request`.
- Postgres schema:
  - Main run record: `heretix/db/models.Check` (lots of scalar columns; no `profile`, `models`, or `result_json` yet).
  - Result cache: `heretix/db/models.ResultCache` with JSON `payload`.
  - Alembic migrations live under `migrations/versions` and already add WEL and provider metadata.

Use this section to quickly rehydrate context in a new window.

---

## Task Checklist (small, chainable steps)

### 1. Profiles, types, and provider interfaces

- [x] Map fast-simplify spec onto current codebase (harness, CLI, API, DB)
- [x] Decide placement for shared types module (use `heretix/types.py` for dataclasses consumed by harness/CLI/API).
- [x] Define `RPLProfile` dataclass and initial profiles in `heretix/profiles.py`.
  - [x] Implement `BIAS_FAST` profile (K/R/T/B/max_output_tokens/total_sample_budget/explanation_mode).
  - [x] Implement `RPL_RESEARCH` profile with current default K/R/T/B and output token settings.
- [x] Define `ModelBiasResult` and `RunResult` dataclasses in the shared types module (`heretix/types.py`).
  - [x] Ensure `RunResult.raw_rpl_output` can hold the full current `run_single_version` payload.
  - [x] Add a `timings` field that can be populated from existing telemetry/logging.
- [x] Confirm how existing provider adapters (GPT‑5, Gemini, Grok) map into a lightweight `LLMProvider` protocol.
  - [x] Decision: keep `RPLAdapter` as the low-level `score_claim` interface and define an `LLMProvider` protocol in `heretix/provider/base.py`; later, thin wrappers can adapt registry functions into `sample_prior` that returns `{label, p_true}` without modifying provider implementations.

**What was implemented for Task 1 (reference for new contexts)**

- Created `heretix/profiles.py`:
  - Added `RPLProfile` dataclass holding `name`, `K`, `R`, `T`, `B`, `max_output_tokens`, `total_sample_budget`, and `explanation_mode`.
  - Defined `BIAS_FAST` as a speed-focused profile:
    - `K=4`, `R=1`, `T=6`, `B=0` (hot path / no final bootstrap), `max_output_tokens=192`.
    - `total_sample_budget=72` (across all models) with `explanation_mode="separate_call"` to support measurement-then-explanation.
  - Defined `RPL_RESEARCH` as a research/CLI profile:
    - `K=8`, `R=2`, `T=8`, `B=5000`, `max_output_tokens=1024`.
    - `total_sample_budget=999_999` (effectively unbounded) with `explanation_mode="inline"` to match current richer runs.
- Created `heretix/types.py`:
  - Added `ModelBiasResult` dataclass:
    - Fields: `model` (logical model name), `p_rpl` (aggregated RPL probability), `label` (e.g. “leans_true”), `explanation` (short natural language string).
    - Includes an `extras: Dict[str, Any]` field for optional diagnostics such as counts-by-template or stability bands.
  - Added `RunResult` dataclass:
    - Fields: `run_id`, `claim`, `profile` (profile name), `models: List[ModelBiasResult]`, `raw_rpl_output: Dict[str, Any]`, and `timings: Dict[str, float]`.
    - `raw_rpl_output` is explicitly intended to hold the full JSON that `heretix.rpl.run_single_version` currently returns, so we don’t lose any estimator- or template-level detail.
    - `timings` is a simple map of stage name → milliseconds to be populated later from existing telemetry/logging.
- Extended `heretix/provider/base.py`:
  - Left `RPLAdapter` unchanged as the low-level protocol (`score_claim(...) -> Dict[str, Any]`).
  - Introduced an `LLMProvider` protocol with:
    - `name: str`.
    - `sample_prior(prompt: str, max_output_tokens: int, seed: Optional[int]) -> Dict[str, Any]`.
  - The intention is to wrap existing registry functions (GPT‑5, Gemini, Grok) into this higher-level interface later, normalizing to a minimal payload like `{"label": "true" | "false", "p_true": float}` without modifying the providers themselves.

Use this block as the “what & how” summary for Task 1 when resuming work in a fresh context.

### 2. Harness profiles, sampling planner, and RunResult

- [x] Implement `derive_sampling_plan(models, profile)` in `heretix/profiles.py` (or nearby).
  - [x] Compute per-model K/R/T with respect to `profile.total_sample_budget`.
  - [x] Ensure `T` remains ≥5 when possible to preserve trimmed-center behavior.
- [x] Thread profile support into the harness:
  - [x] Add an optional `profile: RPLProfile | None` argument to the main harness entry (either `run_single_version` or a small orchestrator above it).
  - [x] When a profile is supplied, derive effective K/R/T/B per model and pass them via `RunConfig` without touching estimator math.
- [x] Split measurement vs explanation:
  - [x] Ensure sampling prompts request JSON-only outputs and enforce profile `max_output_tokens` (192 for `bias_fast`).
  - [x] After aggregation, add a new explanation step that runs once per model to populate `ModelBiasResult.explanation`.
  - [x] Build and return a `RunResult` object from the harness, preserving the existing `run_single_version` JSON as `raw_rpl_output`.

**What was implemented for Task 2 (current session)**

- Added `derive_sampling_plan` in `heretix/profiles.py` to budget K/R/T per model while preferring T ≥ 5 and shrinking K first.
- Added `heretix/bias.py:run_profiled_models` orchestrator that applies profile-derived K/R/T/B/max_tokens, infers providers, calls `run_single_version` per model, and returns a `RunResult` with per-model `ModelBiasResult` entries and raw RPL payloads.
- Introduced an explicit explanation step per model (currently deterministic/stubbed) with separate timing and honoring `explanation_mode`, so measurement and explanation are decoupled while keeping sampling JSON-only with profile token caps.

### 3. CLI wiring and SQLite behavior

- [x] Add `runs/rpl_bias_fast.yaml` config for the CLI fast profile.
  - [x] Include `claim`, `models` (or `model`), and `profile: bias_fast` plus explicit K/R/T/B fields mirroring `BIAS_FAST`.
- [x] Extend `heretix/cli.py`:
  - [x] Allow `profile` in the loaded config and add a `--profile` flag.
  - [x] When a profile is set, hydrate default K/R/T/B/max_output_tokens from `RPLProfile`, allowing explicit overrides.
  - [x] Ensure multi-model CLI runs respect `derive_sampling_plan` (sample budget) when `models` has length >1.
- [x] Verify SQLite behavior:
  - [x] Confirm `heretix/storage.py` schema remains unchanged (no new tables/columns).
  - [x] Confirm the richer `RunResult.raw_rpl_output` can be stored as JSON in existing `config_json`/related fields where needed.
  - [x] Run a mock CLI fast-bias run (`uv run heretix run --config runs/rpl_bias_fast.yaml --mock`) and note outputs (writes `runs/rpl_run.json` with profile-mode payload).

#### Task 3 completion notes
- CLI now accepts `profile` (config or `--profile`), applies profile defaults with explicit overrides, and routes profile runs through `derive_sampling_plan` + `run_profiled_models`, emitting a RunResult payload to `runs/rpl_run.json`.
- Added `runs/rpl_bias_fast.yaml` starter config (bias_fast, K/R/T/B matching BIAS_FAST, max_output_tokens=192).
- Multi-model profile smoke (live): `uv run heretix run --config runs/rpl_bias_fast.yaml --profile bias_fast --model gpt-5 --model gemini-2.5 --model grok-4` produced per-model p_rpl (gpt-5≈0.28, gemini-2.5≈0.05, grok-4≈0.16) with B=1 after clamping and gpt-5 showing schema_validation warnings.
- Tests: `uv run pytest -q` passes.

### 4. heretix_api adapter and FastAPI endpoint

- [x] Implement `run_bias_fast(claim, models, persist_to_sqlite=False) -> RunResult` in `heretix_api/bias_fast.py`.
  - [x] Uses `BIAS_FAST` profile, normalizes models, threads mock/base_config/prompt_root through to `run_profiled_models`; `persist_to_sqlite` is surfaced but harness still writes SQLite today.
- [x] Extend API request/response:
  - [x] `api/schemas.py` now accepts `models` and optional `profile` on `RunRequest`; added `BiasRunResponse`/`BiasModelResult` for multi-model bias payloads.
- [x] Update `/api/checks/run` handler in `api/main.py`:
  - [x] Branches to `run_bias_fast` when `profile=bias_fast` or any `models` provided; enforces baseline mode, usage gating, and returns `BiasRunResponse` with per-model `{name, p_rpl, label, explanation, extras}` and timings + raw payload.
  - [x] Best-effort Postgres persistence in handler: writes per-model `Check` rows from harness run payloads and conditionally sets `profile`/`models`/`result_json` if columns exist; on schema mismatch, falls back to usage-only commit without failing the request.

### 5. Postgres migration and verification

- [ ] Confirm current Postgres schema and migrations:
  - [ ] Re-read `heretix/db/models.Check` and `migrations/versions/*.py` focusing on fields related to prior/web/combined and JSON.
  - [ ] Decide where to store `RunResult.raw_rpl_output` (e.g. new `result_json` JSONB column on `checks`).
- [ ] Add minimal Alembic migration:
  - [ ] Add `profile` (TEXT) and `models` (JSON/JSONB) columns to `checks` if not present.
  - [ ] Add `result_json` JSON/JSONB to `checks` if we choose to store full harness output there.
- [ ] Apply and verify:
  - [ ] Run `uv run alembic upgrade head` locally against Postgres.
  - [ ] Verify existing CLI/API flows still work for single-model legacy runs.
  - [ ] Run end-to-end fast-bias API calls (1–3 models) and confirm:
    - [ ] Sample counts obey the profile budget.
    - [ ] Latency is within the 20s target.
    - [ ] Stored rows include `profile`, `models`, and `result_json` as expected.

---

## Progress Log

- [2025-11-21] Mapped fast-simplify spec onto current harness/CLI/API/DB and set up this checklist file.
- [2025-11-22] Added sampling planner and profile-aware harness orchestrator (RunResult/ModelBiasResult plumbing) with deterministic explanation stubs; measurement vs explanation split still open.
- [2025-11-23] Completed measurement/explanation split within the harness (profile token caps, explanation_mode-aware stub explainer, per-model timing) and marked Task 2 checklist items accordingly.
