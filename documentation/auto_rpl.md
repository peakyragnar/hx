# Auto-RPL (Adaptive Controller)

Purpose: run RPL adaptively, escalating deterministically for quality while explaining every decision.

## Policy (Frozen)
- Stages (templates-first):
  - Stage 1: T=8, K=8, R=2
  - Stage 2: T=16, K=16, R=2
  - Stage 3: T=16, K=16, R=3
- Gates (hard):
  - CI width ≤ 0.20
  - Stability ≥ 0.70  (stability = 1/(1+IQR_logit))
  - Imbalance ≤ 1.50
- Warn (soft): log a warning if Imbalance > 1.25.
- Estimator: unchanged — logit space, equal-by-template, 20% trimmed center, clustered bootstrap (B=5000), deterministic seed.

## Deterministic Sampler
- Balanced counts with deterministic rotation: `offset = sha256(claim|model|PROMPT_VERSION) % T`.
- Order = rotate(range(T), offset), then distribute K as evenly as possible (counts differ by ≤1).
- Diagnostics: planned order, offset, counts_by_template_planned, imbalance_planned.

## Reuse Across Stages
- Samples are cached by `(prompt_sha256, replicate_idx)`.
- Escalations add only deltas:
  - 1→2: add templates to reach K=16 with R=2.
  - 2→3: add one replicate per template to reach R=3.

## CLI
- Adaptive:
  - `uv run heretix-rpl auto --claim "tariffs don't cause inflation" --out runs/rpl_auto.json`
  - Options: `--start-k 8 --start-r 2 --max-k 16 --max-r 3 --ci-width-max 0.20 --stability-min 0.70 --imbalance-max 1.50`.
- Inspect:
  - `uv run heretix-rpl inspect --run runs/rpl_auto.json`
  - Prints per-template means (p, logit), IQR(logit), stability, CI, counts, imbalance.
- Drift monitor:
  - `uv run heretix-rpl monitor --bench bench/sentinels.json --out runs/monitor/DATE.jsonl`
  - Optional: `--baseline runs/monitor/BASELINE.jsonl` to flag drift.

## Output (Shape)
Top-level fields (auto):
- `controller`: policy, start, ceilings, gates, timestamp.
- `final`: stage_id, K, R, p_RPL, ci95, ci_width, stability_score/band, imbalance_ratio, is_stable.
- `stages[]`: one per stage; includes:
  - `planned`: sampler offset, planned order, counts_by_template_planned, imbalance_planned.
  - `raw_run`: embedded full RPL JSON (aggregation diagnostics, seeds, counts, IQR, logits).
- `decision_log[]`: ordered actions with reasons and gate evaluations (values vs thresholds), plus imbalance warnings.

## Interpretation
- CI width ≤ 0.20: usable estimate; increase T (templates) before R for tighter bands.
- Stability ≥ 0.70: paraphrases agree sufficiently (medium-high floor).
- Imbalance ≤ 1.50 (warn at >1.25): near-equal template usage; higher values may indicate parsing drops.

## Provenance
- `PROMPT_VERSION=rpl_g5_v2_2025-08-21` with 16 paraphrase templates.
- Bootstrap seed logged; same inputs → same CI and decisions.

## Non-Goals
- No changes to estimator math or bootstrap mechanics.
- No hidden tuning; future estimator changes require a version bump.

