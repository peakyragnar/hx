# Heretix — Raw Prior Lens (RPL)

![Estimator](https://img.shields.io/badge/Estimator-Frozen-green)
![Auto–RPL](https://img.shields.io/badge/Auto–RPL-Enabled-blue)
![Prompt%20Version](https://img.shields.io/badge/PROMPT__VERSION-rpl__g5__v2__2025--08--21-purple)

Heretix measures a model’s internal prior over claims and rewards durable belief movement. This repository implements the RPL estimator and an adaptive controller that escalates sampling deterministically for quality.

- Estimator (frozen): logit-space aggregation, equal-by-template weighting, 20% trimmed center (T≥5), cluster bootstrap (B=5000) with deterministic seed.
- Prompts: `PROMPT_VERSION=rpl_g5_v2_2025-08-21` with 16 paraphrases.

## Quick Start

- Single run (legacy):
```
uv run heretix-rpl --claim "tariffs don't cause inflation" --k 7 --r 3 --agg clustered
```

- Adaptive controller (Auto‑RPL):
```
uv run heretix-rpl auto --claim "tariffs don't cause inflation" --out runs/rpl_auto.json
```
- Inspect a run:
```
uv run heretix-rpl inspect --run runs/rpl_auto.json
```
- Drift monitor (sentinels):
```
uv run heretix-rpl monitor --bench bench/sentinels.json --out runs/monitor/DATE.jsonl
```

## One‑Liner Shortcuts

- Export key (once per shell):
```
export OPENAI_API_KEY=sk-...
```

- Run Auto‑RPL now (defaults to gates CI≤0.20, stability≥0.70, imbalance≤1.50):
```
uv run heretix-rpl auto \
  --claim "<your claim>" \
  --start-k 8 --start-r 2 --max-k 16 --max-r 3 \
  --ci-width-max 0.20 --stability-min 0.70 --imbalance-max 1.50 \
  --out runs/rpl_auto.json
```

- Inspect stage/template behavior quickly:
```
uv run heretix-rpl inspect --run runs/rpl_auto.json
```

- Weekly drift snapshot (writes dated JSONL):
```
uv run heretix-rpl monitor \
  --bench bench/sentinels.json \
  --out runs/monitor/$(date +%F).jsonl
```

- Make CI deterministic (bootstrap only):
```
HERETIX_RPL_SEED=42 uv run heretix-rpl auto --claim "<your claim>"
```

## Docs
- Adaptive controller: `documentation/auto_rpl.md`
- Aggregation methodology (estimator): `documentation/aggregation.md`
- Flow diagram and module map: `documentation/flow_diagram.md`
- Examples: `examples/auto_tariffs_sample.json`, `examples/interpretation.md`, `examples/monitor_snapshot.jsonl`

## Determinism & Provenance
- Same inputs → same decisions and CIs.
- Outputs include `bootstrap_seed`, `prompt_version`, `counts_by_template`, and stability diagnostics.

## Invariants (do not break without version bump)
- Aggregate in logit space; equal-by-template before global center; 20% trim when T≥5; cluster bootstrap with deterministic seed.
