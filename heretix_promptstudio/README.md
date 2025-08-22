# Heretix Prompt Studio (Lite)

A standalone, human-in-the-loop prompt optimization system for iteratively improving `SYSTEM_RPL` while maintaining complete isolation from production until explicit approval.

## Overview

Prompt Studio allows you to:
- Test variations of the SYSTEM_RPL prompt
- Evaluate them using the exact same statistical methodology as production
- Compare results against quality gates and baselines
- Apply approved prompts to production with safety guarantees

**Key Feature**: This system is completely isolated from production. It only modifies `heretix_rpl/rpl_prompts.py` when you explicitly run the `apply` command.

## Installation

The Prompt Studio is automatically installed with Heretix:

```bash
# From the Heretix directory
uv pip install -e .

# Verify installation
uv run heretix-pstudio --help
```

## Quick Start

### 1. Create a New Prompt Candidate

```bash
# Start a new optimization session
uv run heretix-pstudio propose --notes "Make JSON instruction more explicit"
```

This creates a new candidate (e.g., `cand_001`) with your proposed changes.

### 2. Evaluate the Candidate

```bash
# Run evaluation on training benchmark
uv run heretix-pstudio eval \
  --candidate cand_001 \
  --bench heretix_promptstudio/benches/claims_bench_train.yaml

# Quick mode for testing (not for production)
uv run heretix-pstudio eval \
  --candidate cand_001 \
  --bench heretix_promptstudio/benches/claims_bench_train.yaml \
  --quick
```

### 3. Review Results

```bash
# Generate scorecard with recommendations
uv run heretix-pstudio explain --candidate cand_001 --compare current
```

### 4. Make Decision

```bash
# Accept the candidate
uv run heretix-pstudio decide \
  --candidate cand_001 \
  --action accept \
  --feedback "Good improvement in JSON validity"

# Or reject it
uv run heretix-pstudio decide \
  --candidate cand_001 \
  --action reject \
  --feedback "CI width regression too large"
```

### 5. Apply to Production (if accepted)

```bash
# Dry run to see what would change
uv run heretix-pstudio apply --candidate cand_001 --dry-run

# Apply for real (creates backup)
uv run heretix-pstudio apply --candidate cand_001 --yes
```

## Quality Gates

All candidates must pass these gates before production:

| Gate | Threshold | Description |
|------|-----------|-------------|
| JSON Validity | ≥99.5% | Percentage of valid JSON responses |
| Median CI Width | ≤0.20 | Confidence interval width (uncertainty) |
| Median Stability | ≥0.70 | Cross-paraphrase consistency |
| Post-cutoff Behavior | p∈[0.35,0.65] | Appropriate uncertainty for future claims |
| Invariance | Δ≤0.03 | Insensitivity to irrelevant context |
| Jailbreak Resistance | 0% | No URLs, citations, or tool use |

## Workflow Example

```bash
# 1. Start optimization session
uv run heretix-pstudio propose --notes "Tighten JSON, add determinism instruction"

# 2. Evaluate on training set
uv run heretix-pstudio eval --candidate cand_001 \
  --bench heretix_promptstudio/benches/claims_bench_train.yaml

# 3. Check results
uv run heretix-pstudio explain --candidate cand_001

# 4. If gates pass, evaluate on holdout
uv run heretix-pstudio eval --candidate cand_001 \
  --bench heretix_promptstudio/benches/claims_bench_holdout.yaml

# 5. Review final results
uv run heretix-pstudio explain --candidate cand_001

# 6. Make decision
uv run heretix-pstudio decide --candidate cand_001 --action accept

# 7. Apply to production
uv run heretix-pstudio apply --candidate cand_001 --yes
```

## Session Management

```bash
# List all sessions
uv run heretix-pstudio list

# Resume a previous session
uv run heretix-pstudio resume --session session-20250122_143052

# Clean up old sessions
uv run heretix-pstudio gc --older-than 30 --dry-run
```

## File Structure

```
runs/promptstudio/
└── session-YYYYMMDD_HHMMSS/
    ├── config.json           # Session configuration
    ├── history.jsonl         # Append-only event log
    └── cand_001/
        ├── prompt.txt        # The candidate prompt
        ├── diff.md          # Diff vs production
        ├── metadata.json    # Candidate metadata
        ├── metrics.json     # Evaluation metrics
        ├── decision.json    # Accept/reject decision
        ├── benchmark_results.json  # Full benchmark results
        └── eval/            # Per-claim evaluation JSONs
```

## Prompt Editing Commands

When using `propose`, you can apply these edits:

- `shorten:10` - Reduce prompt by 10%
- `remove:phrase` - Remove specific phrase
- `add:text` - Add new text
- `replace:old:new` - Replace text
- `tighten_json` - Make JSON instruction more explicit
- `add_opaque` - Add deterministic/opaque instruction

## Important Notes

1. **Isolation**: No production code is modified until you run `apply`
2. **Reproducibility**: Uses deterministic seeds for consistent results
3. **Safety**: Always creates timestamped backups before applying
4. **Validation**: Won't apply prompts that fail gates
5. **Testing**: All existing tests continue to pass during development

## Troubleshooting

### "No evaluation results found"
Run `eval` command before trying to explain or apply a candidate.

### "Failed gates"
Review the scorecard recommendations and iterate on your prompt.

### "Provider model changed"
The model version changed during evaluation. Re-run to get consistent results.

### Tests failing
Prompt Studio is completely isolated - existing tests should not be affected. If they are, you may have accidentally modified production code.

## Advanced Usage

### Custom Gates

Edit gate thresholds in `heretix_promptstudio/metrics.py`:

```python
class GateChecker:
    JSON_VALIDITY_MIN = 0.995  # Adjust as needed
    CI_WIDTH_MAX = 0.20
    STABILITY_MIN = 0.70
```

### Batch Evaluation

Evaluate multiple candidates:

```bash
for i in 001 002 003; do
  uv run heretix-pstudio eval --candidate cand_$i \
    --bench heretix_promptstudio/benches/claims_bench_train.yaml
done
```

### Compare Candidates

```bash
uv run heretix-pstudio compare \
  --candidate cand_002 \
  --bench heretix_promptstudio/benches/claims_bench_train.yaml \
  --baseline cand_001
```

## Best Practices

1. **Always evaluate on training set first** - Don't waste API calls on holdout
2. **Use quick mode for iteration** - Fast feedback during development
3. **Review recommendations carefully** - The system suggests specific improvements
4. **Test on holdout before applying** - Ensures generalization
5. **Keep session notes** - Document what you tried and why

## Integration with Production

When a prompt is applied:
1. `SYSTEM_RPL` in `heretix_rpl/rpl_prompts.py` is replaced
2. `PROMPT_VERSION` is updated to `rpl_g5_v2_YYYY-MM-DD+psN`
3. A timestamped backup is created
4. The change is recorded in session history

The production system immediately uses the new prompt for all subsequent evaluations.

## Contributing

To extend Prompt Studio:
1. Add new gate checks in `metrics.py`
2. Add new edit operations in `propose.py`
3. Add new benchmark claims in `benches/`
4. Update recommendations logic in `explain.py`

Remember: Keep the system isolated! Never import production code that could create circular dependencies.