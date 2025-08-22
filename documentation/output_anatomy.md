# Heretix RPL Output Anatomy (Quick Reference)

Audience: operators, auditors, and maintainers who need to interpret run JSON quickly.

## Single RPL Run (cli: `rpl`)

- Provenance: `run_id`, `claim`, `model`, `prompt_version`, `timestamp`.
- Sampling: `sampling` → `{ "K": int, "R": int, "N": int }`.
- Decoding: `decoding` → `max_output_tokens`, `reasoning_effort`, `verbosity`.
- Aggregates:
  - `prob_true_rpl`: final probability estimate (in [0,1]).
  - `ci95`: `[lo, hi]` bootstrap confidence interval (probability space).
  - `ci_width`: `hi - lo`.
  - `paraphrase_iqr_logit`: IQR on per‑template mean logits (dispersion).
  - `stability_score`: calibrated stability `1/(1+(IQR/s)^α)` (s=0.2, α=1.7).
  - `stability_band`: `high | medium | low` (from raw IQR thresholds).
  - `is_stable`: `ci_width ≤ stability_width` (default 0.20).
- Aggregation: `aggregation` →
  - `method`: `equal_by_template_cluster_bootstrap_trimmed` (clustered) or `simple_mean` (legacy).
  - `B`: bootstrap iterations (clustered default 5000).
  - `center`: `trimmed` (clustered) or `mean`.
  - `trim`: 0.2 (drop min/max templates when T≥5).
  - `min_samples`, `stability_width`.
  - `bootstrap_seed`: deterministic seed used (clustered only).
  - `n_templates`, `counts_by_template`, `imbalance_ratio`, `template_iqr_logit`.
- Paraphrase results: `paraphrase_results[]` items contain:
  - `raw`: `{ prob_true, confidence_self, assumptions[], reasoning_bullets[], contrary_considerations[], ambiguity_flags[] }`.
  - `meta`: `{ provider_model_id, prompt_sha256, response_id, created }`.
  - `paraphrase_idx`, `replicate_idx` (integers).
- Paraphrase balance: `paraphrase_balance` → equals aggregation diagnostics for clustered; `{ "method": "simple_mean" }` for simple.
- Raw logits: `raw_logits[]` (per‑sample log‑odds for audits).

## Auto Run (cli: `auto`)

- Controller: `controller` →
  - `policy`: `templates-first-then-replicates`.
  - `start`: `{ K, R }`, `ceilings`: `{ max_K, max_R }`.
  - `gates`: `{ ci_width_max, stability_min, imbalance_max, imbalance_warn }`.
  - `timestamp`.
- Final: `final` →
  - `stage_id`, `K`, `R`, `p_RPL`, `ci95`, `ci_width`, `stability_score`, `stability_band`, `imbalance_ratio`, `is_stable`.
- Stages: `stages[]` (one snapshot per stage) →
  - Top‑level: `stage_id`, `K`, `R`, `T`, `p_RPL`, `ci95`, `ci_width`, `stability_score`, `stability_band`, `imbalance_ratio`, `is_stable`.
  - Planned: `planned` → `offset`, `order`, `counts_by_template_planned[]`, `imbalance_planned`.
  - Raw run: `raw_run` → embedded single‑run structure (`sampling`, `decoding`, `aggregation`, `aggregates`, `paraphrase_results`, `raw_logits`, provenance fields).
- Decisions: `decision_log[]` → ordered entries with `stage_id`, `action` (e.g., `stop_pass`, `escalate_to_T16_K16_R2`, `stop_limits`), `reason`, `gates` report, optional `warning` = `imbalance_warn`.

## Invariants & Policy (do not assume otherwise)

- Always aggregate in logit space; convert to probability only for reporting.
- Equal‑by‑template weighting before global center; 20% trimmed center when T≥5.
- Cluster bootstrap CI with deterministic seed; report `B` and `bootstrap_seed`.
- Prompts: 16 neutral templates; `PROMPT_VERSION = rpl_g5_v2_2025-08-21`.
- Sampler: deterministic balanced rotation by `sha256(claim|model|prompt_version)`.
- Stability: calibrated formula with s=0.2, α=1.7; bands from raw IQR thresholds.
- Gates (Auto‑RPL): CI width ≤ 0.20; Stability ≥ 0.70; Imbalance ≤ 1.50 (warn > 1.25).

## CLI Reminders (uv)

- Run single: `uv run heretix-rpl rpl --claim "..." --k K --r R --agg clustered`.
- Run auto: `uv run heretix-rpl auto --claim "..." --out runs/rpl_auto.json`.
- Inspect run: `uv run heretix-rpl inspect --run runs/…json` (per‑template means, IQR, stability, counts, imbalance).
- Inspect details:
  - CI signal (top templates by deviation from trimmed center):
    - `uv run heretix-rpl inspect --run runs/rpl_auto.json --show-ci-signal --limit 3`
  - Within-template replicate spreads (stdev/logit and prob ranges with replicate list):
    - `uv run heretix-rpl inspect --run runs/rpl_auto.json --show-replicates --limit 3`
  - Combine both:
    - `uv run heretix-rpl inspect --run runs/rpl_auto.json --show-ci-signal --show-replicates`
- Monitor: `uv run heretix-rpl monitor --bench bench/sentinels.json --out runs/monitor/<date>.jsonl`.
- Summarize: `uv run heretix-rpl summarize --file runs/monitor/<date>.jsonl`.

## Reproducibility Tips

- `HERETIX_RPL_SEED`: overrides deterministic seed used for bootstrap CI (does not fix model outputs).
- Compare runs by `prompt_version` and `provider_model_id` to identify provider drift.
- For stability issues: check `imbalance_ratio`, per‑template counts, and `template_iqr_logit`; consider increasing `K`/`R` or using Auto‑RPL.
