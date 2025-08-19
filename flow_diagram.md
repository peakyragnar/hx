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
│  │   │   └── calls chosen aggregator (clustered/simple)           │
│  │   │                                                             │
│  │   └── call_rpl_once_gpt5() → single API call                   │
│  │       ├── Uses OpenAI Responses API                            │
│  │       ├── Extracts JSON from output[1]                         │
│  │       └── Returns probability + metadata + prompt_sha256       │
│  │                    │                                            │
│  │                    ▼                                            │
│  ├── aggregation.py ◄─── STATISTICAL AGGREGATION MODULE           │
│  │   ├── aggregate_clustered() → equal-by-template aggregation    │
│  │   │   ├── Groups samples by prompt_sha256                      │
│  │   │   ├── Computes per-template mean logits                    │
│  │   │   ├── Averages template means equally                      │
│  │   │   └── Cluster bootstrap for CI95 (2000 iterations)         │
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
│  └── OPENAI_API_KEY=xxx                                           │
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
│         └── Track prompt_sha256 for each sample                   │
│                              │                                      │
│  5. Build by_template_logits dict:                                │
│     ├── Group samples by prompt_sha256                            │
│     └── Example: {hash1: [l1,l2,l3], hash2: [l4,l5], ...}        │
│                              │                                      │
│  6. Clustered aggregation (default):                              │
│     ├── Per-template means in log-odds space                      │
│     ├── Equal weighting across templates                          │
│     ├── Cluster bootstrap (resample templates → replicates)       │
│     └── Compute imbalance_ratio and diagnostics                   │
│                              │                                      │
│  7. Output JSON with:                                             │
│     ├── prob_true_rpl: 0.237 (23.7%)                             │
│     ├── ci95: [0.15, 0.32]                                       │
│     ├── stability_score: 0.85                                    │
│     ├── paraphrase_balance: {                                    │
│     │   ├── n_templates: 5                                       │
│     │   ├── counts_by_template: {hash1: 6, hash2: 6, ...}       │
│     │   ├── imbalance_ratio: 2.0                                 │
│     │   └── template_iqr_logit: 0.15                             │
│     │   }                                                         │
│     └── Full provenance data                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          OUTPUT                                     │
├─────────────────────────────────────────────────────────────────────┤
│  runs/rpl_run.json ◄─── Detailed results with balance diagnostics │
│  └── Terminal display of key metrics                              │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                   CLUSTERED AGGREGATION APPROACH                   │
├─────────────────────────────────────────────────────────────────────┤
│  Problem Solved:                                                  │
│  ├── K=7 with 5 templates → templates 0,1 get double weight       │
│  └── Creates bias in final estimate                               │
│                                                                     │
│  Solution: Equal-by-Template Aggregation                          │
│  ├── Group by prompt_sha256 (unique paraphrase hash)              │
│  ├── Average replicates within each template                      │
│  ├── Weight templates equally (regardless of count)               │
│  └── Cluster bootstrap preserves hierarchical structure           │
│                                                                     │
│  Diagnostics:                                                      │
│  ├── imbalance_ratio: max_count/min_count (ideal=1.0)            │
│  ├── counts_by_template: samples per paraphrase                   │
│  └── template_iqr_logit: consistency across templates             │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Flow Summary

1. **Entry**: `uv run heretix-rpl --agg clustered` → `pyproject.toml` → `cli.py:main()`
2. **Orchestration**: `evaluate_rpl()` manages K×R sampling strategy  
3. **API Calls**: `call_rpl_once_gpt5()` hits OpenAI Responses API
4. **Sample Tracking**: Each sample tagged with `prompt_sha256` for clustering
5. **Aggregation**: `aggregation.py` module handles clustered or simple aggregation
6. **Prompting**: Uses structured prompts from `rpl_prompts.py`
7. **Validation**: Response schema enforced by `rpl_schema.py`
8. **Statistics**: Clustered aggregation ensures unbiased estimates
9. **Output**: JSON results with confidence intervals, balance diagnostics, and provenance

## Aggregation Methods

- **Clustered** (default): Equal-by-template aggregation with cluster bootstrap
  - Fixes paraphrase imbalance when K > number of templates
  - Groups samples by prompt hash, weights templates equally
  - 2000 bootstrap iterations respecting hierarchical structure

- **Simple** (legacy): Direct mean of all logits  
  - Original behavior, may have bias with template wraparound
  - 1000 standard bootstrap iterations
  - Available via `--agg simple` for comparison