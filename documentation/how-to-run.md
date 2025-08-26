Complete Guide: Running Heretix RPL System

  Prerequisites

  1. Setup Environment
  # Clone repository
  git clone https://github.com/peakyragnar/hx.git
  cd Heretix

  # Install dependencies using uv
  uv sync

  # Set up environment variables
  echo "OPENAI_API_KEY=your-api-key-here" > .env

  Running Evaluations: Three Approaches

  1️⃣ Single Evaluation (Basic RPL)

  For a simple one-shot evaluation with manual parameters:

  # Basic run with defaults (K=7, R=3)
  uv run heretix-rpl rpl --claim "tariffs don't cause inflation" --out runs/my_claim.json

  # Custom sampling parameters
  uv run heretix-rpl rpl --claim "AI will surpass human intelligence by 2030" \
    --k 10 --r 5 --out runs/ai_claim.json

  # Check the results
  cat runs/my_claim.json | jq '.aggregates'

  What happens:
  - Sends claim to GPT-5 with K different paraphrase templates
  - Each template is evaluated R times (replicates)
  - Aggregates results using clustered method (equal template weighting, trimmed mean, bootstrap CI)
  - Outputs probability estimate with confidence interval and stability metrics

  2️⃣ Auto-RPL (Adaptive, Recommended)

  The intelligent way - automatically escalates sampling until quality gates pass:

  # Run Auto-RPL with adaptive sampling
  uv run heretix-rpl auto --claim "nuclear energy is safer than fossil fuels" \
    --out runs/nuclear_auto.json

  # Watch it work (verbose by default):
  # [auto] Stage 1/3: T=8, K=8, R=2
  # [auto] Stage 1 metrics: p=0.723 width=0.113 stability=0.201 imbalance=1.00
  # [auto] Escalating to Stage 2: T=16, K=16, R=2
  # ...continues until gates pass or limits reached

  Quality Gates (automatic checking):
  - ✅ CI width ≤ 0.20 (uncertainty control)
  - ✅ Stability ≥ 0.70 (template consistency)
  - ✅ Imbalance ≤ 1.50 (balanced sampling)

  3️⃣ Batch Monitoring (Sentinel Tracking)

  For tracking multiple claims over time:

  # Create sentinel benchmark file
  cat > bench/my_sentinels.json << 'EOF'
  [
    {"claim": "climate change is primarily human-caused"},
    {"claim": "vaccines are generally safe"},
    {"claim": "quantum computers will break RSA encryption"}
  ]
  EOF

  # Run monitor with progress tracking
  uv run heretix-rpl monitor --bench bench/my_sentinels.json \
    --out runs/monitor/$(date +%Y%m%d).jsonl

  # Quick mode for faster testing (K=5, R=1)
  uv run heretix-rpl monitor --bench bench/my_sentinels.json \
    --quick --out runs/monitor/quick_test.jsonl

  Analyzing Results

  📊 Inspect Individual Runs

  # Basic inspection - shows per-template statistics
  uv run heretix-rpl inspect --run runs/nuclear_auto.json

  # Output:
  # Claim: nuclear energy is safer than fossil fuels
  # K=16  R=3  T=16
  # 
  # Per-template means (sorted by logit):
  #   hash       n   mean_p   mean_logit
  #   a3f2d9e1c4   3   0.681    0.782
  #   b7e5a2f8d6   3   0.703    0.892
  #   ...
  # IQR(logit) = 0.423  → stability = 0.703
  # p_RPL = 0.723   CI95 = [0.672, 0.769]   width = 0.097   is_stable = True

  🔍 Advanced Diagnostics

  # Show which templates contribute most to CI width
  uv run heretix-rpl inspect --run runs/nuclear_auto.json --show-ci-signal

  # CI signal (by |delta_logit| from trimmed center):
  #   hash       pidx  mean_p   delta_logit  paraphrase
  #   c9f3a7b2e1   12   0.823    +0.523      Is it accurate that nuclear energy...
  #   a3f2d9e1c4    3   0.681    -0.412      Does evidence support that nuclear...

  # Show within-template replicate consistency
  uv run heretix-rpl inspect --run runs/nuclear_auto.json --show-replicates

  # Within-template replicate spread:
  #   hash       pidx  stdev_logit  range_p   replicates_p
  #   d4e8c9a3f2    7      0.142     0.063    [0.712, 0.745, 0.775]

  📈 Monitor Analysis

  # Summarize a monitor run
  uv run heretix-rpl summarize --file runs/monitor/20250122.jsonl

  # Output:
  # Rows: 25  Models: gpt-5  Versions: rpl_g5_v2_2025-08-21
  # Means → p: 0.567  ci_width: 0.089  stability: 0.712
  # Counts → high(≥0.9): 3  low(≤0.1): 2  mid(0.4–0.6): 8
  # Widest CIs:
  #   - 0.187  quantum computers will break RSA encryption
  #   - 0.134  AI consciousness is possible

  Drift Detection (Compare Over Time)

  # Run weekly monitor
  uv run heretix-rpl monitor --bench bench/sentinels.json \
    --out runs/monitor/week1.jsonl

  # Week later, run with baseline comparison
  uv run heretix-rpl monitor --bench bench/sentinels.json \
    --baseline runs/monitor/week1.jsonl \
    --out runs/monitor/week2.jsonl

  # Check drift flags in output
  cat runs/monitor/week2.jsonl | jq '{claim, drift_p, drift_stability}'

  Understanding Output Files

  Single/Auto Run JSON Structure:
  {
    "claim": "...",
    "aggregates": {
      "prob_true_rpl": 0.723,      // Final probability estimate
      "ci95": [0.672, 0.769],      // 95% confidence interval
      "ci_width": 0.097,            // Uncertainty measure
      "stability_score": 0.703,     // Template consistency (0-1)
      "is_stable": true             // Passed CI width threshold
    },
    "aggregation": {
      "n_templates": 16,            // Unique templates used
      "imbalance_ratio": 1.0,       // Template balance (1.0 = perfect)
      "template_iqr_logit": 0.423   // Template spread
    },
    "paraphrase_results": [...]     // Raw API responses
  }

  Quick Decision Tree

  Need to evaluate a claim?
  ├── Just want a quick answer?
  │   └── uv run heretix-rpl rpl --claim "..."
  ├── Want robust, production-ready result?
  │   └── uv run heretix-rpl auto --claim "..."
  ├── Tracking multiple claims over time?
  │   └── uv run heretix-rpl monitor --bench bench/sentinels.json
  └── Debugging stability issues?
      └── uv run heretix-rpl inspect --run ... --show-ci-signal --show-replicates

  Pro Tips

  1. Always use Auto-RPL for important evaluations - it handles edge cases automatically
  2. Monitor sentinels weekly to detect model drift
  3. Use inspect with --show-ci-signal when stability is low to identify problematic templates
  4. Set HERETIX_RPL_SEED environment variable for reproducible bootstrap CIs (for debugging)
  5. Quick mode (K=5, R=1) for development/testing only, not production

  The system is designed to be robust, reproducible, and transparent - every number can be audited back to specific template-replicate pairs.
