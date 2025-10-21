# Faster Phase 1 Plan

This maps the “Speed First” brief onto the active harness (the code that
ships today lives under `heretix/`, not `heretix_rpl/`). The goal is the
same: improve throughput and observability without touching the frozen
statistics.

---

## 1. Runtime Configuration
- Extend `heretix/config.py` with a `RuntimeSettings` dataclass that reads:
  - `HERETIX_RPL_CONCURRENCY` (default 8)
  - `HERETIX_FAST_B` (default 1000)
  - `HERETIX_FINAL_B` (default 5000)
  - `HERETIX_FAST_FINAL` (default on)
  - `HERETIX_L1_TTL`, `HERETIX_L1_MAX`, `HERETIX_CACHE_TTL`
  - `HERETIX_PRICE_IN`, `HERETIX_PRICE_OUT`
- Make the settings available inside `heretix/rpl.py` and the CLI.

## 2. Telemetry
- Add `heretix/telemetry.py` with:
  - `timed(stage, ctx)` context manager for structured timing logs.
  - `est_tokens(chars)` and `est_cost(tokens_in, tokens_out, price_in, price_out)`.
- Wrap key stages in `heretix/rpl.py` and `heretix/aggregate.py`:
  - Provider call worker
  - K×R sampling loop
  - Cache get/set
  - Bootstrap CI (fast and final)
- Emit a `run_summary` log with per-run totals (tokens, estimated cost, ms, cache hits).

## 3. Concurrency
- Refactor the deterministic work-list builder currently inside `heretix/rpl.py`
  into a helper (e.g., `heretix/sampler.build_worklist`).
- Continue to use `ThreadPoolExecutor`, but drive `max_workers` from
  `RuntimeSettings`. Keep the existing retry + sequential repair logic.
- Add telemetry around the parallel section so the speedups are visible.

## 4. Caching
- Add an in-process `TTLCache` in `heretix/cache.py`; consult it before
  hitting SQLite and populate it after successful fetches.
- For run-level reuse, add a new table via SQLite migration (e.g., `runs_cache`)
  and expose helpers in `heretix/storage.py`. If a matching run exists, short-circuit
  the provider calls and return the cached JSON immediately.
- Include cache hit/miss counts in the `run_summary` log and returned payload.

## 5. Fast-Then-Final CI
- In `heretix/rpl.py`, compute a fast bootstrap (`B=fast_B`) first.
- If `HERETIX_FAST_FINAL` is true:
  - Return immediately with a `ci_status` block: `{"phase":"fast","B_used":fast_B}`.
  - Spawn a background worker (new `heretix/finalizer.py`) that replays `aggregate_clustered`
    with `B=final_B` using the stored logits + deterministic seed.
  - Update the persisted `runs`/`executions` rows (or write a `.final.json`) when the final CI finishes.
- Ensure the finalizer never alters the point estimate, only the CI span and `aggregation.B`.

## 6. Token & Cost Tracking
- After each provider response, capture approximate input/output char counts.
- Convert to tokens via `telemetry.est_tokens`, aggregate across the run,
  estimate USD cost via `est_cost`, and log the totals in `run_summary`.
- Optionally persist these metrics on the execution row for later analysis.

## 7. CLI/API Surface
- No breaking changes. Add optional CLI flags/env overrides to tweak
  concurrency and fast/final behaviour.
- Include the optional `ci_status` block in the run JSON so clients know which CI they received.

## 8. Tests (heretix/tests/)
- Deterministic work list for fixed `(claim, model, prompt_version, K, R)`.
- Concurrency speedup with a sleeping mock provider.
- L1/L2 cache coverage (single-run and run-level reuse).
- Fast→final CI background update (mock the aggregator to confirm the second pass).
- Telemetry smoke: ensure timing and summary logs emit the expected fields.

## 9. Guardrails
- Keep `heretix/aggregate.py` untouched (no math changes).
- Honour existing seeds; concurrency must not alter aggregation results.
- Background finalizer must read/write stored logits only—no extra provider calls.
- Defaults preserve current sequential behaviour if env toggles are left unset.

With these adjustments, Phase 1 delivers lower wall time, richer instrumentation, and deterministic
fast/final CIs while staying aligned with the production harness layout.*** End Patch
