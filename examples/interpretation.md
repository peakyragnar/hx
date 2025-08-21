# Interpreting Auto‑RPL Outputs (Quick Guide)

Use this guide with `examples/auto_tariffs_sample.json`.

## Headlines
- `final.p_RPL`: the robust prior estimate (probability the claim is true).
- `final.ci95` / `final.ci_width`: uncertainty from cluster bootstrap in logit space.
- `final.stability_score` / `final.stability_band`: paraphrase sensitivity via IQR(logit).
- `final.imbalance_ratio`: template usage balance (ideal ≈ 1.0).

## Gates
- Pass if: CI width ≤ 0.20, Stability ≥ 0.70, Imbalance ≤ 1.50.
- Warn if: Imbalance > 1.25 (non‑blocking) — check parser/sampler health.

## Decisions
- See `decision_log[]`:
  - Stage 1 failed (ci_width, stability) → escalated to Stage 2.
  - Stage 2 passed all gates → stopped; final selected.

## Stages (What changed?)
- Stage 1 (T=8,K=8,R=2):
  - Higher CI width (0.223) and lower stability (0.66) — paraphrases disagree more.
- Stage 2 (T=16,K=16,R=2):
  - Double templates → CI width tightened to 0.029; stability rose to 0.84.
- Stage 3 would add replicates (R=3) only if needed; not required here.

## Sampler Diagnostics
- `planned.offset`: deterministic rotation offset (sha256 claim|model|prompt_version).
- `planned.order`: rotated template order; counts are distributed evenly.
- `counts_by_template_planned` & `imbalance_planned`: near‑1.0 by design.

## Provenance
- `prompt_version=rpl_g5_v2_2025-08-21` with 16 paraphrases.
- `aggregation.bootstrap_seed` logged in each stage’s `raw_run` for CI reproducibility.

## Operator Tips
- Need tighter bands? Increase templates (T,K) before replicates (R).
- If Imbalance > 1.25 warning appears often, inspect JSON parsing and sampler logs.
- Use `inspect` to print per‑template means and IQR quickly:
```
uv run heretix-rpl inspect --run runs/rpl_auto.json
```

