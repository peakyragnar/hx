# Heretix — Raw Prior Lens (RPL)

![Estimator](https://img.shields.io/badge/Estimator-Frozen-green)
![Auto–RPL](https://img.shields.io/badge/Auto–RPL-Enabled-blue)
![Prompt%20Version](https://img.shields.io/badge/PROMPT__VERSION-rpl__g5__v2__2025--08--21-purple)

Heretix measures a model’s internal prior over claims and rewards durable belief movement. This repository now contains a clean RPL harness (`heretix/`) and quarantined legacy code under `legacy/`.

- Estimator (frozen): logit-space aggregation, equal-by-template weighting, 20% trimmed center (T≥5), cluster bootstrap (B=5000) with deterministic seed.
- Prompts: `PROMPT_VERSION=rpl_g5_v2_2025-08-21` with 16 paraphrases.

## Quick Start (New Harness)

- Setup environment (uv):
```
uv sync
```

- Create a minimal run config (example):
```
cat > runs/rpl_example.yaml << 'EOF'
claim: "tariffs don't cause inflation"
model: gpt-5
prompt_version: rpl_g5_v2
K: 8
R: 2
T: 8
B: 5000
seed: 42
max_prompt_chars: 1200
max_output_tokens: 1024
EOF
```

- Run RPL (single or multi-version):
```
export OPENAI_API_KEY=sk-...
uv run heretix run --config runs/rpl_example.yaml --out runs/new_rpl.json
```

- Smoke test (no network):
```
uv run heretix run --config runs/rpl_example.yaml --out runs/smoke.json --mock
```

- Describe plan (no network):
```
uv run heretix describe --config runs/rpl_example.yaml
```

- Output includes: p_RPL, CI95, stability, cache_hit_rate, rpl_compliance_rate.

Legacy CLI is available under `legacy/` for reference but is not installed by default.

## Local Postgres (App Data)
- Start the development database:
  - `docker compose up -d postgres`
- Use the local connection string in your shell: `DATABASE_URL=postgresql+psycopg://heretix:heretix@localhost:5432/heretix`
- Apply migrations after changes: `alembic upgrade head`
- Stop services when done: `docker compose down`
- Production deployments point at the Neon connection string saved as `DATABASE_URL_PROD`.

## Faster Runs (Optional Concurrency)

- CLI (opt‑in):
  - `HERETIX_CONCURRENCY=8 uv run heretix run --config runs/rpl_example.yaml --out runs/faster.json`
- UI (opt‑in):
  - `HERETIX_CONCURRENCY=8 UI_PORT=7799 uv run python ui/serve.py` then open `http://127.0.0.1:7799`
- Notes:
  - Concurrency parallelizes provider calls only; estimator/DB/identities unchanged.
  - For long claims, prefer `max_output_tokens: 768–1200` to avoid truncated JSON under parallel load.
  - Start with 6–8 workers; reduce if your provider rate‑limits.
  - See `faster-processing.md` for details.

## Single-Claim Workflow
- Use `claim:` in your config and run with `heretix run` as above. Outputs persist to SQLite and a single JSON file for easy inspection.
- See the detailed step‑by‑step guide in `documentation/how-to-run.md` (includes the HTML report and opening it in Chrome).

## Tests
- New harness (default): `uv run pytest -q`
- Include legacy (optional): `uv run pytest heretix/tests legacy/tests -q`

## Determinism
- Set a bootstrap seed in the config (`seed: 42`) to fix CI draws.
- Precedence: config `seed` > `HERETIX_RPL_SEED` env > derived deterministic value.
- The effective `bootstrap_seed` is shown in outputs and persisted in the DB.

## One‑Liner (Deterministic CI)
```
HERETIX_RPL_SEED=42 uv run heretix run --config runs/rpl_example.yaml
```

## Docs
- New harness design: see `refactor.md` (Tooling with uv, repo structure, phases)
- Estimator and stats: `documentation/aggregation.md`, `documentation/STATS_SPEC.md`
- Smoke tests: `documentation/smoke_tests.md`
- Legacy docs remain in `documentation/` and are referenced by the archived code under `legacy/`.

## Determinism & Provenance
- Same inputs → same decisions and CIs.
- Outputs include `bootstrap_seed`, `prompt_version`, `counts_by_template`, and stability diagnostics.

## Invariants (do not break without version bump)
- Aggregate in logit space; equal-by-template before global center; 20% trim when T≥5; cluster bootstrap with deterministic seed.
