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
│  │   │   └── 5000 iterations for smooth CI95                      │
│  │   │                                                             │
│  │   └── aggregate_simple() → legacy unclustered mean             │
│  │       ├── Direct mean of all logits                            │
│  │       └── Standard bootstrap for CI95 (1000 iterations)        │
│  │                    │                                            │
│  │                    ▼                                            │
│  ├── rpl_prompts.py ◄─── PROMPTING STRATEGY                       │
│  │   ├── SYSTEM_RPL → system prompt for RPL evaluation            │
│  │   ├── USER_TEMPLATE → user message template                    │
│  │   └── PARAPHRASES[] → 5 different ways to ask                  │
│  │                    │                                            │
│  │                    ▼                                            │
│  └── rpl_schema.py ◄─── RESPONSE VALIDATION                       │
│      └── RPL_SCHEMA → OpenAI structured output schema             │
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
│  └── Structured output with JSON schema                           │
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
│     └── Compute imbalance_ratio and diagnostics                   │
│                              │                                      │
│  8. Output JSON with:                                             │
│     ├── prob_true_rpl: 0.237 (23.7%)                             │
│     ├── ci95: [0.15, 0.32]                                       │
│     ├── stability_score: 0.85                                    │
│     ├── aggregation: {                                           │
│     │   ├── method: "equal_by_template_cluster_bootstrap_trimmed" │
│     │   ├── bootstrap_seed: 12595722686829152907                  │
│     │   ├── B: 5000, center: "trimmed", trim: 0.2               │
│     │   ├── n_templates: 5                                       │
│     │   ├── counts_by_template: {hash1: 6, hash2: 6, ...}       │
│     │   ├── imbalance_ratio: 2.0                                 │
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
│  └── Terminal display of key metrics                              │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│              HARDENED AGGREGATION APPROACH (v2)                    │
├─────────────────────────────────────────────────────────────────────┤
│  Core Improvements:                                               │
│  ├── Trimmed Mean (20%): Drops outlier templates                 │
│  ├── Deterministic Seeding: Same inputs → same CIs               │
│  ├── 5000 Bootstrap Iterations: Smoother confidence intervals     │
│  └── Configuration-Based Seed: Changes only when needed           │
│                                                                     │
│  Statistical Robustness:                                          │
│  ├── Equal-by-template: Fixes paraphrase imbalance               │
│  ├── Cluster bootstrap: Correct two-level uncertainty             │
│  ├── Trimmed center: Robust to outlier templates                 │
│  └── Log-odds averaging: Proper probability geometry              │
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
│  └── bootstrap_seed: exact seed used for this run                │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Flow Summary

1. **Entry**: `uv run heretix-rpl --agg clustered` → `pyproject.toml` → `cli.py:main()`
2. **Orchestration**: `evaluate_rpl()` manages K×R sampling strategy  
3. **API Calls**: `call_rpl_once_gpt5()` hits OpenAI Responses API
4. **Sample Tracking**: Each sample tagged with `prompt_sha256` for clustering
5. **Seed Generation**: `make_bootstrap_seed()` creates deterministic seed from config
6. **Aggregation**: `aggregation.py` performs hardened clustered aggregation
7. **Prompting**: Uses structured prompts from `rpl_prompts.py`
8. **Validation**: Response schema enforced by `rpl_schema.py`
9. **Statistics**: Trimmed clustered aggregation ensures unbiased, robust estimates
10. **Output**: JSON with seed, aggregation config, and reproducible results

## Aggregation Methods

### Clustered (Default) - Hardened Version
- **Equal-by-template**: Fixes paraphrase imbalance when K > templates
- **Trimmed mean (20%)**: Drops min/max templates, averages middle 3
- **Deterministic RNG**: Configuration-based seed for reproducibility
- **5000 bootstrap iterations**: Smooth, stable confidence intervals
- **Cluster bootstrap**: Respects two-level uncertainty structure

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

The enhanced output includes an `aggregation` block with:
- Method name (e.g., "equal_by_template_cluster_bootstrap_trimmed")
- Bootstrap seed for reproducibility
- Configuration (B=5000, center="trimmed", trim=0.2)
- Template statistics (counts, imbalance ratio, IQR)

This ensures complete transparency and reproducibility of the statistical methodology.