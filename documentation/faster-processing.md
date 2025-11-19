# Faster Processing — Minimal, Reversible, Aligned With Simplicity

This note documents simple, low‑risk ways to reduce wall‑time for RPL runs without changing the estimator, policy, or outputs. It follows a “best part is no part” approach: remove waste first, prefer small toggles over big changes, and keep reversibility cheap.

## Truths and Constraints

- Estimator and policy are frozen (do not change):
  - Logit‑space aggregation, equal‑by‑template, 20% trim when T≥5, cluster bootstrap.
  - JSON‑only; exclude URLs/citations; invalid samples don’t contribute.
- No change to DB schema, CLI contract, or prompt semantics required for the speedups below.

## Summary (Fastest Wins First)

1) Lower `max_output_tokens` for RPL runs to 256.
   - Zero code change. 20–40% latency reduction per call is common.
2) Add bounded concurrency for provider calls (env‑gated, default off).
   - Stdlib only, ~60 LOC. 3–5× wall‑time reduction for T=16, K=16, R=2.
3) Progressive bootstrap in the UI (optional UX only).
   - Show B=1000 immediately, recompute B=5000 in the background using the same samples.
4) Keep cache hygiene tight.
   - Stable prompt/version/token cap → high cache hit rate on re‑runs.
5) Explainer call remains optional.
   - Or summarize reasons from the run’s own JSON fields to avoid the extra call.

## 1) Trim Decode Tokens (No Code)

- Set in your config(s):
  - `max_output_tokens: 256`
- Why it works: RPL outputs are short (probability + a few bullets). Smaller decode caps cut latency without harming compliance.
- Rollback: change a single number; no code.

## 2) Concurrency (Stdlib, Env‑Gated)

Goal: parallelize only the slow part — provider calls — while keeping sampling, replicate indexing, and aggregation identical.

- Approach:
  - In `heretix/rpl.py`, wrap the provider call loop in a `ThreadPoolExecutor` with a bounded pool (e.g., 8–12 workers).
  - Compute the exact same `prompt_sha256`, `replicate_idx`, and cache key for each (template, replicate) before dispatch.
  - Each worker returns a fully formed sample row (in memory). After all complete, insert with a single call to `insert_samples(...)` and proceed to aggregation.
  - Seed/estimator/aggregation unchanged.

- Toggle:
  - `HERETIX_CONCURRENCY=8` (default: disabled). When unset, code paths behave exactly as today.

- Why it’s safe:
  - Determinism: replicate labels and cache keys are derived before dispatch; order of completion doesn’t affect identities.
  - DB access: writes happen after collection (single thread); no locking games.
  - Reversibility: remove one block or unset one env var.

- Notes:
  - Respect provider rate limits; keep pool modest (8–12). Add small jittered backoff on transient errors.
  - Log a one‑line summary: pool size, successes, retries.

## 3) Progressive Bootstrap (UI‑Only, Optional)

- What changes: display an interim result with `B=1000` immediately (CPU‑only), then recompute `B=5000` in the background using the same valid logits and swap it in.
- Why it’s safe: center and width converge; final numbers match the current design (B=5000). No changes to sampling or estimator — only the UI’s rendering order.
- Rollback: disable the background recompute; always show only the final numbers.

## 4) Cache Hygiene

- Keep these fixed for re‑runs to maximize cache hits:
  - `prompt_version`, `max_output_tokens`, claim string (exact), model.
  - Use “top‑up” runs (e.g., first `K=8`, then `K=16` with the same T/R/seed) — the second run reuses the first half of samples.
- With v5 paraphrases deduplicated, cluster identities are stable and imbalance spikes are less likely.

## 5) Explainer Call Is Optional

- Current UI makes one post‑run explainer call. If preferred, you can:
  - Make it async (doesn’t block headline).
  - Or remove it and summarize from existing fields: `reasons`, `assumptions`, `uncertainties`, `flags` (already in run JSON).
- This keeps the core RPL cost unchanged.

## Rollout Plan (Minimal Risk)

- Phase A (now, zero code):
  - Set `max_output_tokens: 256` in the default config used by UI.
  - Reinforce cache hygiene in docs and examples.

- Phase B (biggest win, small patch):
  - Add concurrency behind `HERETIX_CONCURRENCY`. Default off. Test with 8.
  - Verify: identical `run_id`, identical sample identities, identical aggregates.

- Phase C (optional UX):
  - Progressive UI bootstrap. If it causes confusion, disable — final numbers remain.

## Validation Checklist

- Determinism: same inputs (and seed) → same p/CI/stability as before.
- Identity: sample cache keys unchanged; DB row counts match K×R attempts.
- Provider: no elevated error rates; backoff works; no throttling.
- Perf: wall‑time per claim drops significantly on first run; re‑runs near‑instant.

## Example Settings

```
# Config (UI + CLI)
max_output_tokens: 256

# Env (enable concurrency)
HERETIX_CONCURRENCY=8
```

## FAQ

- Q: Does concurrency change the math?
  - A: No. We only parallelize provider calls; aggregation is unchanged and uses the same valid samples.

- Q: Could concurrency break SQLite?
  - A: We only write after all futures complete, from the main thread. No concurrent writes.

- Q: Why not lower B?
  - A: B affects only bootstrap precision. We can show B=1000 early for UX, but we keep B=5000 for final results as per the frozen spec.

- Q: Any risk to compliance?
  - A: Lower decode caps typically reduce JSON breakage; policy checks remain the same.

---

This plan keeps the estimator and policy fixed, removes duplication, uses stdlib concurrency behind a single toggle, and makes reversibility trivial — faster without unnecessary complexity.
