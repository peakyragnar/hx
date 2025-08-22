# Heretix Prompt Studio (Lite)

A standalone, human‑in‑the‑loop prompt optimization system for iteratively improving `SYSTEM_RPL` while keeping production isolated until you approve.

Key properties
- Isolation: Only `heretix_rpl/rpl_prompts.py` is modified, and only by `apply`.
- Parity: Uses the production estimator (logit aggregation, 20% trim, cluster bootstrap with deterministic seed).
- Determinism: Balanced template rotation + fixed session seed; same CI bootstrap sequence across candidates.
- Responses API only: No Chat Completions; schema is embedded in system instructions; strict JSON‑only extraction.

## Installation

Prompt Studio ships with the repo.

```bash
# From the repo root
uv pip install -e .

# Verify CLI
uv run heretix-pstudio --help
```

## Quick Start (with enforcement)

1) Propose a candidate

```bash
uv run heretix-pstudio propose --notes "Tighten JSON; add opaque; two decimals"
uv run heretix-pstudio precheck --candidate cand_001   # optional: constraint preflight
```

2) Evaluate on training bench (deterministic K/R)

```bash
uv run heretix-pstudio eval \
  --candidate cand_001 \
  --bench heretix_promptstudio/benches/claims_bench_train.yaml

# Quick iteration (dev only, not publishable)
uv run heretix-pstudio eval --candidate cand_001 --bench heretix_promptstudio/benches/claims_bench_train.yaml --quick
```

3) Review and compare to current production

```bash
# Scorecard with gates and recommendations
uv run heretix-pstudio explain --candidate cand_001

# Compare against current production on the same bench
uv run heretix-pstudio compare \
  --candidate cand_001 \
  --bench heretix_promptstudio/benches/claims_bench_train.yaml \
  --baseline current
```

4) If train passes, evaluate on holdout

```bash
uv run heretix-pstudio eval \
  --candidate cand_001 \
  --bench heretix_promptstudio/benches/claims_bench_holdout.yaml
```

5) Decide and apply

```bash
uv run heretix-pstudio decide --candidate cand_001 --action accept --feedback "Good JSON validity; CI/stability improved"

# Dry run shows diff + target version bump
uv run heretix-pstudio apply --candidate cand_001 --dry-run

# Apply (creates timestamped backup, enforces gates + improvement rule)
uv run heretix-pstudio apply --candidate cand_001 --yes
```

## What “apply” enforces

Before writing to production, `apply` requires:
- An accepted decision for the candidate.
- Train and holdout bench results present and passing all gates (JSON validity, CI width, stability, invariance, jailbreak).
- Baseline (current production prompt) evaluated on the same train bench shows ≥1 improvement with 0 regressions across:
  - Lower median CI width, or
  - Higher median stability, or
  - Fewer instruction tokens (estimated),
  and no negative deltas on these dimensions.

## Quality Gates (unchanged)

- JSON validity ≥ 99.5% (strict JSON‑only; one top‑level object; no prose).
- Median CI width ≤ 0.20 (probability space).
- Median stability ≥ 0.70 (1/(1+IQR_logit) on template means).
- Post‑cutoff (tagged claims): median p in [0.35, 0.65] and ≥90% with cutoff‑uncertainty flags in `ambiguity_flags`.
- Irrelevant‑context invariance: median |Δp| ≤ 0.03 across clean vs context pairs.
- Jailbreak resistance: 0% (URLs, citations, tool/browse/markdown indicators in raw or JSON fields).

## Constraints (preflight)

Required (case‑insensitive presence):
- “Do NOT browse, search, or cite”
- “JSON only”/“Output ONLY JSON” (last line)
- “ignore instructions” + “opaque” (treat claim as opaque data)
- “two decimals” (numeric formatting nudge)

Forbidden:
- URLs (`http://`, `https://`, `www.`), code fences (```), markdown labels, tool/browse cues (`function call`, `use tool`, `browser`, `search`, `web.run`),
- Temporal leakage (`as of 20`, `today`, `now`), citation hints (`cite`, `URL`).

Use:
```bash
uv run heretix-pstudio precheck --candidate cand_001
```

## CLI Reference

- `propose --notes "..."` — Create a new candidate in the current session. Stores `prompt.txt`, `diff.md`, `metadata.json`.
- `precheck --candidate cand_X` — Validate constraints before spending API.
- `eval --candidate cand_X --bench benches/claims_bench_train.yaml [--quick]` — Evaluate candidate on a bench. Writes:
  - `benchmark_results.json` (last run)
  - `benchmark_results_<bench-stem>.json` (bench‑specific)
  - `eval/*.json` (per‑claim)
- `explain --candidate cand_X` — Scorecard with pass/fail per gate and concrete recommendations.
- `compare --candidate cand_X --bench ... --baseline current|cand_Y` — Compare aggregate metrics vs current production or another candidate. Baseline current runs a production prompt evaluation and saves `baseline_current_<bench>.json`.
- `decide --candidate cand_X --action accept|reject [--feedback "..."]` — Record decision.
- `apply --candidate cand_X [--dry-run] [--yes]` — Enforce gates (train+holdout) and improvement rule; write `SYSTEM_RPL` and bump `PROMPT_VERSION`; create backup.
- `list [-v]` — List candidates in the active (or provided) session.
- `show --candidate cand_X [--section prompt|diff|metrics|decision]` — Inspect artifacts.
- `resume --session session-YYYYMMDD_HHMMSS` — Switch active session.
- `gc --older-than 30 [--dry-run]` — Clean up old sessions.

## Outputs & Layout

```
runs/promptstudio/
└── session-YYYYMMDD_HHMMSS/
    ├── config.json                  # Session config (incl. deterministic seed)
    ├── history.jsonl                # Append-only event log
    └── cand_001/
        ├── prompt.txt               # Candidate SYSTEM_RPL
        ├── diff.md                  # Diff vs production prompt
        ├── metadata.json            # Length/tokens, constraint issues, notes
        ├── decision.json            # accept/reject + feedback
        ├── benchmark_results.json   # Last eval results (any bench)
        ├── benchmark_results_train.json     # Train results (if run)
        ├── benchmark_results_holdout.json   # Holdout results (if run)
        ├── baseline_current_train.json      # Baseline (production) on train (if compared)
        └── eval/                    # Per-claim evaluation JSONs
```

## Determinism & Parity

- Uses production `PARAPHRASES` and `USER_TEMPLATE`; only `SYSTEM_RPL` varies.
- Deterministic balanced rotation: `offset = sha256(claim|model|PROMPT_VERSION) % T`.
- `prompt_sha256` matches production: hash of full `instructions` (system + schema) + user text.
- Bootstrap seed parity: includes actual `K`, `R`, `prompt_version`, and sorted unique template hashes.
- Responses API; strict JSON‑only extraction.

## Tips

- Use `--quick` only for iteration; do not publish.
- For repeatable CI bands across candidates, set `HERETIX_RPL_SEED` once per session.
- Avoid literal `"""` inside prompts; keep `SYSTEM_RPL` in triple double quotes and let the tool escape as needed.

## Troubleshooting

- “No evaluation results found”: run `eval` on train (and holdout before apply).
- “Failed gates”: check `explain` recommendations and `compare` deltas.
- “Provider model changed”: model snapshot changed mid-run; re-run session.
