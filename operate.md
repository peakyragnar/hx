# Operate Heretix (RPL)

This guide explains how to run the Raw Prior Lens (RPL) evaluator, the adaptive Auto‑RPL controller, and the monitoring utilities. It includes prerequisites, commands, output interpretation, and weekly operations.

## 0) Prerequisites
- Python via uv (project uses uv, not venv)
- An OpenAI API key in your environment or `.env` file
  - `OPENAI_API_KEY=sk-...`
- Optional: set a deterministic bootstrap seed for reproducible confidence intervals
  - `HERETIX_RPL_SEED=42`

## 1) Core Ideas (30 seconds)
- RPL measures a model’s internal prior on a claim using many paraphrase prompts, then aggregates probabilities in logit space to produce a robust estimate with uncertainty.
- Invariants (don’t change without a version bump):
  - Aggregate in logit space; equal-by-template weighting; 20% trimmed center (T≥5)
  - Cluster bootstrap CI (B=5000) with a deterministic seed; log `prompt_version` and `provider_model_id`.
- Auto‑RPL escalates the sampling plan deterministically if quality gates fail (templates first, then replicates) and logs exactly what it did and why.

## 2) Quick Start
- Single claim (legacy, manual plan):
```
uv run heretix-rpl --claim "tariffs don't cause inflation" --k 7 --r 3 --agg clustered
```
- Adaptive controller (recommended):
```
uv run heretix-rpl auto --claim "tariffs don't cause inflation" --out runs/rpl_auto.json
```
- Inspect a run (per‑template means, IQR, stability, CI):
```
uv run heretix-rpl inspect --run runs/rpl_auto.json
```
- Weekly sentinel monitor (baseline snapshot):
```
uv run heretix-rpl monitor --bench bench/sentinels.json --out runs/monitor/$(date +%F).jsonl
```
- Summarize a monitor JSONL (means, counts, top‑3 widest CIs):
```
uv run heretix-rpl summarize --file runs/monitor/$(date +%F).jsonl
```
- Makefile shortcuts (optional):
```
make auto CLAIM="tariffs don't cause inflation"
make inspect FILE=runs/rpl_auto.json
make monitor  # writes runs/monitor/<date>.jsonl
make summarize FILE=runs/monitor/<date>.jsonl
```

## 3) Commands & Options

### A) Legacy RPL (one‑shot)
```
uv run heretix-rpl --claim "..." --model gpt-5 --k 7 --r 3 --agg clustered --out runs/rpl_run.json
```
- `--claim`: statement to evaluate
- `--model`: `gpt-5` (default) or `gpt-5-mini` if available
- `--k`: paraphrase slots (wrap‑over available templates)
- `--r`: replicates per slot (decode stochasticity)
- `--agg`: `clustered` (robust) or `simple` (legacy mean)
- Output: JSON with `aggregates` (p_RPL, CI, stability), `aggregation` diagnostics, `paraphrase_results`, `raw_logits`.

### B) Auto‑RPL (adaptive, templates‑first)
```
uv run heretix-rpl auto --claim "..." \
  --start-k 8 --start-r 2 --max-k 16 --max-r 3 \
  --ci-width-max 0.20 --stability-min 0.70 --imbalance-max 1.50 \
  --out runs/rpl_auto.json
```
- Stage plan (frozen):
  1. T=8, K=8, R=2 → 2. T=16, K=16, R=2 → 3. T=16, K=16, R=3
- Gates:
  - Hard: CI width ≤ 0.20; Stability ≥ 0.70 (1/(1+IQR_logit)); Imbalance ≤ 1.50
  - Warn (non‑blocking): Imbalance > 1.25
- Behavior:
  - Deterministic balanced sampler with rotation: avoids favoring low indices
  - Reuses samples across stages (adds only deltas)
  - Emits a decision log and saves stage snapshots (full RPL JSON) for audit
- Output (top‑level): `controller`, `final`, `stages[]`, `decision_log[]`

### C) Inspect (explain a run)
```
uv run heretix-rpl inspect --run runs/rpl_auto.json
```
- Accepts:
  - A plain RPL run JSON
  - An Auto‑RPL top‑level JSON (reads `final` stage’s embedded `raw_run`)
  - A stage snapshot object (with `raw_run`)
- Prints: per‑template means (prob & logit), IQR(logit), stability, CI, counts, imbalance.

### D) Monitor (sentinel bench, drift snapshot)
```
uv run heretix-rpl monitor \
  --bench bench/sentinels.json \
  --out runs/monitor/$(date +%F).jsonl \
  [--baseline runs/monitor/<prior>.jsonl] [--quick] [--limit N] [--append]
```
- Fixed settings by default: `K=8`, `R=2`, `B=5000` (CI and stability still robust)
- Streams progress and writes one JSON line per claim with: `p_RPL`, `ci95`, `ci_width`, `stability`, `model`, `prompt_version`, and optional drift flags if a baseline is provided.
- Options:
  - `--baseline`: flags drift per claim (`drift_p`, `drift_stability`, `drift_ci`)
  - `--quick`: `K=5`, `R=1` for smoke tests
  - `--limit N`: only first N bench entries
  - `--append`: append to existing JSONL

### E) Summarize (monitor JSONL)
```
uv run heretix-rpl summarize --file runs/monitor/<date>.jsonl
```
- Shows: row count, models/versions, mean p/CI width/stability, counts of high/low/mid p, drift flags totals, and top‑3 widest CIs.

## 4) Output Interpretation (key fields)
- `aggregates.prob_true_rpl` (p_RPL): robust aggregated prior probability
- `aggregates.ci95` / `ci_width`: cluster bootstrap CI (in probability space)
- `aggregates.stability_score`: 1/(1+IQR(logit)) on per‑template means (higher = better)
- `aggregation.method`: `equal_by_template_cluster_bootstrap_trimmed`
- `aggregation.bootstrap_seed`: deterministic seed used for CI reproducibility
- `aggregation.counts_by_template`, `imbalance_ratio`, `template_iqr_logit`: diagnostics
- Auto‑RPL extras: `stages[]` with embedded `raw_run`, and `decision_log[]` explaining gates and actions

## 5) Determinism & Provenance
- Deterministic RNG for bootstrap: report `bootstrap_seed`; override with `HERETIX_RPL_SEED` if needed
- Prompts: `PROMPT_VERSION=rpl_g5_v2_2025-08-21` (16 paraphrases); logged in outputs
- Sampler rotation depends on `(claim|model|prompt_version)` to keep ordering fair and auditable

## 6) Operating Recipes
- One claim (fast, adaptive):
  - `uv run heretix-rpl auto --claim "..." --out runs/rpl_auto.json`
  - `uv run heretix-rpl inspect --run runs/rpl_auto.json`
- Weekly snapshot:
  - `uv run heretix-rpl monitor --bench bench/sentinels.json --out runs/monitor/$(date +%F).jsonl`
  - `uv run heretix-rpl summarize --file runs/monitor/$(date +%F).jsonl`
- Drift vs baseline:
  - `uv run heretix-rpl monitor --bench bench/sentinels.json --baseline runs/monitor/<prior>.jsonl --out runs/monitor/$(date +%F).jsonl`

## 7) Performance Notes
- Auto‑RPL Stage 1 does 16 calls (8 templates × R=2). With typical API latencies, budget ~30–60s per stage.
- Monitor default is 12 claims × (8×2) ≈ 192 calls → several minutes. Use `--quick --limit N` to smoke‑test.

## 8) Troubleshooting
- “No progress” feeling during Auto:
  - Stage messages are printed (added `verbose=True`). Each stage collects many samples; wait for metrics line.
- `inspect` shows `K=?, R=?, T=0`:
  - Use the updated `inspect` (supports Auto‑RPL top‑level) and point to the auto JSON (`--run runs/rpl_auto.json`).
- CI is very wide or stability low:
  - Auto escalates templates first; if still failing, consider whether the claim is underspecified.
- Imbalance warning (>1.25):
  - Non‑blocking; indicates parsing drops. Check parser logs or re‑run.

## 9) Safety Rails (do not change unless you know why)
- Estimator: logit aggregation, equal-by-template, 20% trimmed center, cluster bootstrap with deterministic seed
- Gates (Auto‑RPL): CI≤0.20, Stability≥0.70, Imbalance≤1.50 (warn at >1.25)
- Template bank: 16 neutral paraphrases; `PROMPT_VERSION` controls provenance

---
If you need a one‑liner to fix CI determinism for a paper or audit:
```
HERETIX_RPL_SEED=42 uv run heretix-rpl auto --claim "..."
```
