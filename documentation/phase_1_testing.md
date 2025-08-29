# Phase‑1 Testing Plan (Heretix RPL Harness)

Purpose: lock in the Phase‑1 behavior (sampling, caching, aggregation, CLI) using the deterministic mock provider. These tests validate operator‑visible knobs and outputs without changing frozen estimator math.

What we test
- Sampling: K/R/T planning, rotation, and per‑template counts.
- Replicate indexing: DB rows equal K×R even when K>T.
- Aggregation invariants: p in [0,1], CI ordered, widths > 0, stability in [0,1], template counts match plan.
- Cache behavior: first run (misses), second run (hits), no‑cache override.
- DB persistence: runs/samples schema, counts, diagnostics, and config/sampler JSON blobs.
- CLI UX: describe (plan), run --dry-run (no writes), run single (JSON), run batch (JSONL via claims_file).
- Prompt provenance: prompts_file overrides prompt_version; version bump logged.

How to run
- Default (new harness only):
```
uv run pytest -q
```
- Include legacy (optional):
```
uv run pytest heretix/tests legacy/tests -q
```

Key scenarios covered
1) K and T balance
   - K divisible by T → balanced counts, imbalance_ratio = 1.0
   - K not divisible by T → extra slots distributed to first (rotated) templates; expected multiset of counts
2) R effect
   - planned slot counts unchanged; total attempts multiply by R
3) Replicate indexing uniqueness
   - DB sample rows per run = K×R
4) Cache
   - First run → cache_hit_rate ~ 0.0
   - Second identical run → cache_hit_rate ~ 1.0, rows stable
   - HERETIX_RPL_NO_CACHE=1 → cache bypassed
5) CLI
   - describe prints plan (T_bank, rotation_offset, tpl_indices, seq, counts)
   - run --dry-run prints plan and writes nothing
   - run single writes compact JSON
   - run batch (claims_file + .jsonl) writes one JSON line per claim
6) Prompts
   - prompts_file overrides prompt_version and logs prompt_version_full

Notes
- All tests use the mock provider; no network calls.
- We assert ranges/structure, not exact probability numbers.
- DB location is `runs/heretix.sqlite`; tests avoid destructive cleanup.

