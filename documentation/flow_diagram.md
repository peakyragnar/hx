# Heretix Repository Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          HERETIX REPOSITORY                        │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         ENTRY POINTS                               │
├─────────────────────────────────────────────────────────────────────┤
│  CLI Command: uv run heretix-rpl --claim "text" --k 7 --r 3       │
│                     --agg clustered                                │
│  Optional: HERETIX_RPL_SEED=42 (for reproducible runs)            │
│                              │                                      │
│                              ▼                                      │
│  pyproject.toml: [project.scripts]                                 │
│  heretix-rpl = "heretix_rpl.cli:main"                             │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        CLI COMMAND SURFACE                          │
├─────────────────────────────────────────────────────────────────────┤
│  rpl:      uv run heretix-rpl rpl --claim "…" --k K --r R           │
│            → runs core evaluator (rpl_eval) with chosen aggregator. │
│  auto:     uv run heretix-rpl auto --claim "…"                     │
│            → runs templates-first Auto‑RPL orchestrator.            │
│  inspect:  uv run heretix-rpl inspect --run runs/…json              │
│            → prints per-template means, IQR, stability, counts.     │
│  monitor:  uv run heretix-rpl monitor --bench bench/sentinels.json  │
│            → weekly sentinel snapshot; optional baseline drift.     │
│  summarize: uv run heretix-rpl summarize --file runs/…jsonl         │
│            → summarizes monitor JSONL (means, drift, widest CIs).   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CORE MODULE STRUCTURE                           │
├─────────────────────────────────────────────────────────────────────┤
│  heretix_rpl/                                                      │
│  ├── cli.py ◄─── ENTRY POINT                                      │
│  │   ├── main() → parses args (claim, k, r, model, out, agg)      │
│  │   └── calls evaluate_rpl() with aggregator choice              │
│  │                    │                                            │
│  │                    ▼                                            │
│  ├── rpl_eval.py ◄─── CORE EVALUATION ENGINE                      │
│  │   ├── evaluate_rpl() → orchestrates K×R sampling               │
│  │   │   ├── K paraphrases × R replicates                         │
│  │   │   ├── calls call_rpl_once_gpt5() for each sample           │
│  │   │   ├── builds by_template_logits dict (prompt_sha256→logits)│
│  │   │   ├── generates deterministic seed or uses env override    │
│  │   │   └── calls chosen aggregator with seeded RNG              │
│  │   │                                                             │
│  │   └── call_rpl_once_gpt5() → single API call                   │
│  │       ├── Uses OpenAI Responses API                            │
│  │       ├── Extracts JSON from output[1]                         │
│  │       └── Returns probability + metadata + prompt_sha256       │
│  │                    │                                            │
│  │                    ▼                                            │
│  ├── seed.py ◄─── DETERMINISTIC SEED GENERATION                   │
│  │   └── make_bootstrap_seed() → config-based seed                │
│  │       ├── Hashes: claim, model, prompt_version, K, R           │
│  │       ├── Includes sorted template hashes                      │
│  │       ├── Includes aggregator config (center, trim, B)         │
│  │       └── Returns 64-bit integer for numpy RNG                 │
│  │                    │                                            │
│  │                    ▼                                            │
│  ├── aggregation.py ◄─── HARDENED STATISTICAL AGGREGATION         │
│  │   ├── aggregate_clustered() → robust equal-by-template         │
│  │   │   ├── Groups samples by prompt_sha256                      │
│  │   │   ├── _trimmed_mean() → drops min/max templates (20%)      │
│  │   │   ├── Averages middle 3 templates equally                  │
│  │   │   ├── Cluster bootstrap with deterministic RNG             │
│  │   │   ├── 5000 iterations for smooth CI95                      │
│  │   │   ├── Robust IQR handling (warn+clamp tiny negatives)      │
│  │   │   └── Trim validation (must be < 0.5)                      │
│  │   │                                                             │
│  │   └── aggregate_simple() → legacy unclustered mean             │
│  │       ├── Direct mean of all logits                            │
│  │       └── Standard bootstrap for CI95 (1000 iterations)        │
│  │                    │                                            │
│  │                    ▼                                            │
│  ├── metrics.py ◄─── CALIBRATED STABILITY SCORING                 │
│  │   ├── stability_from_iqr() → 1/(1+(IQR/s)^α) formula           │
│  │   │   ├── s=0.2 (midpoint), α=1.7 (steepness)                 │
│  │   │   └── IQR=0.2 maps to stability=0.5 (medium)               │
│  │   ├── stability_band_from_iqr() → high/medium/low bands        │
│  │   └── compute_stability_calibrated() → score + raw IQR         │
│  │                    │                                            │
│  │                    ▼                                            │
│  ├── rpl_prompts.py ◄─── PROMPTING STRATEGY                       │
│  │   ├── SYSTEM_RPL → system prompt for RPL evaluation            │
│  │   ├── USER_TEMPLATE → user message template                    │
│  │   └── PARAPHRASES[] → 16 neutral templates (balanced rotation) │
│  │                    │                                            │
│  │                    ▼                                            │
│  └── rpl_schema.py ◄─── RESPONSE VALIDATION                       │
│      └── RPL_JSON_SCHEMA → OpenAI structured output schema        │
│          ├── prob_true (0-1)                                      │
│          ├── confidence_self (0-1)                                │
│          ├── reasoning_bullets[]                                  │
│          ├── contrary_considerations[]                            │
│          └── assumptions[], ambiguity_flags[]                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     EXTERNAL DEPENDENCIES                          │
├─────────────────────────────────────────────────────────────────────┤
│  OpenAI API (GPT-5)                                               │
│  ├── Responses API endpoint                                        │
│  ├── No temperature/top_p (model is inherently stochastic)        │
│  ├── Structured output with JSON schema                           │
│  └── Feature-detect reasoning param; fallback if unsupported      │
│                              │                                     │
│  Environment (.env)                                               │
│  ├── OPENAI_API_KEY=xxx (required)                                │
│  └── HERETIX_RPL_SEED=42 (optional, for reproducibility)          │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        EXECUTION FLOW                              │
├─────────────────────────────────────────────────────────────────────┤
│  1. User runs: uv run heretix-rpl --claim "tariffs cause inflation"│
│                              │                                      │
│  2. cli.py:main() parses arguments (including --agg flag)          │
│                              │                                      │
│  3. evaluate_rpl() called with K=7, R=3, agg="clustered"          │
│                              │                                      │
│  4. For each of K paraphrases:                                    │
│     ├── For each of R replicates:                                 │
│     │   └── call_rpl_once_gpt5() → API call                      │
│     └── Collect K×R = 21 probability samples                      │
│         └── Track prompt_sha256 and logits for each sample        │
│                              │                                      │
│  5. Build by_template_logits dict:                                │
│     ├── Group samples by prompt_sha256                            │
│     └── Example: {hash1: [l1,l2,l3], hash2: [l4,l5], ...}        │
│                              │                                      │
│  6. Generate deterministic seed:                                  │
│     ├── Check HERETIX_RPL_SEED env variable                       │
│     ├── If not set: make_bootstrap_seed() from config            │
│     └── Create np.random.default_rng(seed) for reproducibility    │
│                              │                                      │
│  7. Hardened clustered aggregation:                               │
│     ├── Per-template means in log-odds space                      │
│     ├── Trimmed mean (drop min/max, average middle 3)            │
│     ├── Cluster bootstrap (resample templates → replicates)       │
│     ├── 5000 iterations with deterministic RNG                    │
│     ├── Robust error handling (IQR validation, trim validation)   │
│     └── Compute imbalance_ratio and diagnostics                   │
│                              │                                      │
│  8. Calibrated stability scoring:                                 │
│     ├── Apply metrics.py formula: 1/(1+(IQR/s)^α)                │
│     ├── s=0.2, α=1.7 for business semantics alignment            │
│     └── IQR=0.2 maps to stability=0.5 (medium)                   │
│                              │                                      │
│  9. Output JSON with:                                             │
│     ├── prob_true_rpl: 0.237 (23.7%)                             │
│     ├── ci95: [0.15, 0.32]                                       │
│     ├── stability_score: 0.85 (calibrated via metrics.py)        │
│     ├── is_stable: true (based on CI width ≤ 0.20)              │
│     ├── aggregation: {                                           │
│     │   ├── method: "equal_by_template_cluster_bootstrap_trimmed" │
│     │   ├── bootstrap_seed: 12595722686829152907                  │
│     │   ├── B: 5000, center: "trimmed", trim: 0.2               │
│     │   ├── n_templates: 7                                       │
│     │   ├── counts_by_template: {hashA: 3, hashB: 3, ...}        │
│     │   ├── imbalance_ratio: 1.0                                 │
│     │   └── template_iqr_logit: 0.15                             │
│     │   }                                                         │
│     └── Full provenance data with paraphrase_results             │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          OUTPUT                                     │
├─────────────────────────────────────────────────────────────────────┤
│  runs/rpl_run.json ◄─── Detailed results with:                   │
│  ├── Deterministic seed for reproducibility                       │
│  ├── Aggregation configuration and diagnostics                    │
│  ├── Calibrated stability scoring                                 │
│  └── Terminal display of key metrics                              │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│              HARDENED AGGREGATION APPROACH (v3)                    │
├─────────────────────────────────────────────────────────────────────┤
│  Core Improvements:                                               │
│  ├── Trimmed Mean (20%): Drops outlier templates                 │
│  ├── Deterministic Seeding: Same inputs → same CIs               │
│  ├── 5000 Bootstrap Iterations: Smoother confidence intervals     │
│  ├── Configuration-Based Seed: Changes only when needed           │
│  └── Calibrated Stability: Business-aligned scoring formula       │
│                                                                     │
│  Statistical Robustness:                                          │
│  ├── Equal-by-template: Fixes paraphrase imbalance               │
│  ├── Cluster bootstrap: Correct two-level uncertainty             │
│  ├── Trimmed center: Robust to outlier templates                 │
│  ├── Log-odds averaging: Proper probability geometry              │
│  ├── Robust IQR handling: Warns on tiny negatives, fails on large│
│  └── Trim validation: Prevents trim ≥ 0.5 edge cases            │
│                                                                     │
│  Calibrated Stability Scoring:                                    │
│  ├── Formula: 1/(1+(IQR/s)^α) with s=0.2, α=1.7                 │
│  ├── Business semantics: IQR=0.2 → stability=0.5 (medium)       │
│  ├── Categorical bands: high (≤0.05), medium (≤0.30), low (>0.30)│
│  └── Separated measurement from interpretation                     │
│                                                                     │
│  Reproducibility:                                                  │
│  ├── Seed = SHA256(claim|model|templates|config)[:8]             │
│  ├── Override: HERETIX_RPL_SEED environment variable             │
│  └── Seed recorded in output JSON for audit trail                │
│                                                                     │
│  Diagnostics:                                                      │
│  ├── imbalance_ratio: max_count/min_count (ideal=1.0)            │
│  ├── counts_by_template: samples per paraphrase                   │
│  ├── template_iqr_logit: consistency across templates             │
│  ├── bootstrap_seed: exact seed used for this run                │
│  └── stability_score: calibrated stability via metrics.py        │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Flow Summary

1. **Entry**: `uv run heretix-rpl --agg clustered` → `pyproject.toml` → `cli.py:main()`
2. **Orchestration**: `evaluate_rpl()` manages K×R sampling strategy  
3. **API Calls**: `call_rpl_once_gpt5()` hits OpenAI Responses API
4. **Sample Tracking**: Each sample tagged with `prompt_sha256` for clustering
5. **Seed Generation**: `make_bootstrap_seed()` creates deterministic seed from config
6. **Aggregation**: `aggregation.py` performs hardened clustered aggregation with robust error handling
7. **Stability Scoring**: `metrics.py` applies calibrated stability formula with business semantics
8. **Prompting**: Uses structured prompts from `rpl_prompts.py`
9. **Validation**: Response schema enforced by `rpl_schema.py`
10. **Statistics**: Trimmed clustered aggregation ensures unbiased, robust estimates
11. **Output**: JSON with seed, aggregation config, calibrated stability, and reproducible results

## Aggregation Methods

### Clustered (Default) - Hardened Version
- **Equal-by-template**: Fixes paraphrase imbalance when K > templates
- **Trimmed mean (20%)**: Drops min/max templates, averages middle 3
- **Deterministic RNG**: Configuration-based seed for reproducibility
- **5000 bootstrap iterations**: Smooth, stable confidence intervals
- **Cluster bootstrap**: Respects two-level uncertainty structure
- **Robust error handling**: Validates trim < 0.5, handles negative IQR edge cases
- **Calibrated stability**: Uses metrics.py for business-aligned stability scoring

### Simple (Legacy)
- Direct mean of all logits  
- 1000 standard bootstrap iterations
- May have bias with template wraparound
- Available via `--agg simple` for comparison

## Reproducibility Features

1. **Automatic Seeding**: Seed derived from claim, model, templates, and config
2. **Environment Override**: Set `HERETIX_RPL_SEED=42` for custom seed
3. **Seed in Output**: Every run records its `bootstrap_seed` in JSON
4. **Identical Results**: Same configuration always produces same CIs

## Output Structure

The enhanced output includes:

**Aggregates Block**:
- `prob_true_rpl`: Calibrated probability estimate
- `ci95`: Bootstrap confidence interval
- `stability_score`: Calibrated stability via metrics.py formula
- `is_stable`: Boolean flag based on CI width ≤ 0.20

**Aggregation Block**:
- Method name (e.g., "equal_by_template_cluster_bootstrap_trimmed")
- Bootstrap seed for reproducibility
- Configuration (B=5000, center="trimmed", trim=0.2)
- Template statistics (counts, imbalance ratio, IQR)

**Calibrated Stability Features**:
- Separates raw IQR measurement from business interpretation
- Formula: `1/(1+(IQR/s)^α)` where s=0.2, α=1.7
- IQR=0.2 maps to stability=0.5 (medium) for business alignment
- Categorical bands: high/medium/low for business logic

This ensures complete transparency, reproducibility, and business-aligned interpretation of the statistical methodology.

## Adaptive Orchestrator

Modules
- `heretix_rpl/orchestrator.py`: `auto_rpl()` runs templates‑first stages, reuses samples, records decisions and stage snapshots.
- `heretix_rpl/sampler.py`: deterministic balanced sampler with rotation by `sha256(claim|model|PROMPT_VERSION)`.
- `heretix_rpl/inspect.py`: `summarize_run(path)` prints per‑template means, IQR(logit), stability, CI, counts, imbalance.
- `heretix_rpl/monitor.py`: sentinel bench runner and baseline comparison for model drift.

Adaptive Execution
- Run: `uv run heretix-rpl auto --claim "..."`.
- Stage 1: T=8, K=8, R=2 (balanced+rotated template order).
- Evaluate gates: CI≤0.20, stability≥0.70, imbalance≤1.50; warn if imbalance>1.25.
- If needed, Stage 2: T=16, K=16, R=2 (more templates).
- If still needed, Stage 3: T=16, K=16, R=3 (more replicates).
- Output: `controller`, `final`, `stages[]` with embedded RPL JSON, and `decision_log[]` explaining actions.

Notes
- `PROMPT_VERSION=rpl_g5_v2_2025-08-21` (16 paraphrases).
- Estimator unchanged: logit space, equal‑by‑template, 20% trimmed center, clustered bootstrap (B=5000) with deterministic seed.

┌─────────────────────────────────────────────────────────────────────┐
│                     AUTO‑RPL STAGE SWIMLANE                         │
├─────────────────────────────────────────────────────────────────────┤
│ Claim → Orchestrator (templates‑first, deterministic rotation)      │
│                                                                     │
│  Stage 1     T=8  K=8  R=2                                          │
│    │         • Balanced sampler (8 unique templates × 2 reps each)  │
│    │         • Aggregate → p, CI, stability, imbalance              │
│    │         • Gates: CI≤0.20 AND Stability≥0.70 AND Imb≤1.50       │
│    ├── pass ──▶ STOP (emit final)                                    │
│    └── fail ──▶ escalate                                             │
│                                                                     │
│  Stage 2     T=16 K=16 R=2                                          │
│    │         • Reuse prior samples; add deltas to reach plan        │
│    │         • Aggregate (same estimator)                           │
│    │         • Gates (same as above); Warn if Imb>1.25              │
│    ├── pass ──▶ STOP (emit final)                                    │
│    └── fail ──▶ escalate                                             │
│                                                                     │
│  Stage 3     T=16 K=16 R=3                                          │
│    │         • Increase replicates (templates unchanged)            │
│    │         • Aggregate (same estimator)                           │
│    ├── pass/limit ▶ STOP (emit final)                               │
│                                                                     │
│ Output: controller (policy, gates), final (p, CI, stability, etc.), │
│         stages[] (snapshots with raw_run), decision_log[]           │
└─────────────────────────────────────────────────────────────────────┘

## Output Anatomy

- Top‑level `rpl` run (single evaluation):
  - aggregates: prob_true_rpl, ci95[], ci_width, paraphrase_iqr_logit, stability_score, stability_band, is_stable
  - aggregation: method, B, center, trim, min_samples, stability_width, bootstrap_seed, n_templates, counts_by_template, imbalance_ratio, template_iqr_logit
  - sampling: K, R, N
  - decoding: max_output_tokens, reasoning_effort, verbosity
  - paraphrase_results: array of per‑call items with raw fields and meta (provider_model_id, prompt_sha256, response_id, created), plus indices
  - paraphrase_balance: equals aggregation diagnostics when clustered; `{"method": "simple_mean"}` for simple
  - raw_logits: array of per‑sample logits (for audits)
  - provenance: run_id, claim, model, prompt_version, timestamp

- Top‑level `auto` run (orchestrated evaluation):
  - controller: policy, start{K,R}, ceilings{max_K,max_R}, gates{ci_width_max, stability_min, imbalance_max, imbalance_warn}, timestamp
  - final: stage_id, K, R, p_RPL, ci95[], ci_width, stability_score, stability_band, imbalance_ratio, is_stable
  - stages[]: per‑stage snapshots containing:
    - stage_id, K, R, T, p_RPL, ci95[], ci_width, stability_score, stability_band, imbalance_ratio, is_stable
    - planned: offset, order, counts_by_template_planned[], imbalance_planned
    - raw_run: embedded single‑run structure (sampling, decoding, aggregation, aggregates, paraphrase_results, raw_logits, provenance)
  - decision_log[]: ordered actions with gates report and any `imbalance_warn`
