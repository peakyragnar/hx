Heretix — AGENTS.md (Phase‑1 RPL Harness)

Purpose: Enable coding agents (and humans) to work quickly and safely on the Phase‑1 RPL harness, with clear commands, file map, guardrails, and current scope. The long product/statistics spec lives in documentation; this file is the operational guide for this repo.

Status: Phase‑1 (RPL harness) implemented; now testing/validation. The RPL estimator and policy are frozen. Legacy code is archived under legacy/ and not part of the install.

Scope: Only the new harness in heretix/* is active. Auto‑RPL controller and monitor/inspect/summarize tooling are roadmap items and not exposed by the current CLI.

—

Quickstart (Phase‑1)
- Install (uv):
  - uv sync
- Prepare a run config (example):
  - runs/rpl_example.yaml
    - claim: "tariffs don't cause inflation"
    - model: gpt-5
    - prompt_version: rpl_g5_v2
    - K: 8
    - R: 2
    - T: 8
    - B: 5000
    - max_output_tokens: 1024
- Mock run (no network):
  - uv run heretix run --config runs/rpl_example.yaml --mock --out runs/smoke.json
- Live run (requires OPENAI_API_KEY):
  - export OPENAI_API_KEY=sk-...
  - uv run heretix run --config runs/rpl_example.yaml --out runs/rpl.json
- Deterministic CI for CI width and decisions (does not fix model outputs):
  - HERETIX_RPL_SEED=42 uv run heretix run --config runs/rpl_example.yaml

Dev Environment
- Python: >=3.10
- Package manager/runner: uv (not venv/poetry/pip). Always prefix commands with uv run
  - Examples: uv run heretix run --config runs/claim.yaml, uv run pytest -q
- Env vars:
  - OPENAI_API_KEY: required for live runs (dotenv supported)
  - HERETIX_RPL_SEED: optional deterministic bootstrap seed (CI reproducibility)
  - HERETIX_RPL_NO_CACHE=1: bypass cached samples
- Secrets: keep .env local; never commit secrets

Cloud Dev Environments
- GitHub Codespaces / VS Code Dev Containers:
  - Provided at .devcontainer/devcontainer.json
  - Open in Codespaces or "Reopen in Container" in VS Code; post-create runs uv sync automatically
- Gitpod:
  - Provided at .gitpod.yml
  - Start a workspace; setup task installs uv and runs uv sync automatically

CI (GitHub Actions)
- Runner uses uv for parity with local:
  - Installs uv via script and runs `uv sync --extra test`
  - Executes `uv run pytest -q` (defaults to new harness only via pytest.ini). To include legacy, run `uv run pytest heretix/tests legacy/tests -q`.
- Deterministic bootstrap in CI:
  - Set `HERETIX_RPL_SEED=42` for stable CI widths/decisions (does not change model outputs)
- Coverage:
  - Coverage collected against `heretix` and uploaded via Codecov on Python 3.11

Testing Instructions (Phase‑1)
- New harness suite (default): uv run pytest -q
- Include legacy tests explicitly: uv run pytest heretix/tests legacy/tests -q
- Focused tests:
  - uv run pytest heretix/tests/test_smoke.py -q -k smoke_mock_run
  - uv run pytest heretix/tests/test_smoke_params.py -q
  - uv run pytest heretix/tests/test_smoke_cli.py -q
  - uv run pytest heretix/tests/test_smoke_db.py -q
- Expectations:
  - Tests pass with --mock (no network)
  - SQLite database created at runs/heretix.sqlite (runs and samples tables)
  - JSON artifact written to the path passed via --out

CLI (Current)
- Entrypoints:
  - `uv run heretix describe --config <file>`: print effective config and sampling plan (no network)
  - `uv run heretix run --config <file> [--out <file>] [--mock] [--dry-run]`
- Config file keys (YAML/JSON):
  - claim (str)
  - claims_file (str, optional): path to JSONL or text file with one claim per line (batch mode)
  - model (str): gpt-5
  - prompt_version (str): rpl_g5_v2
  - K (int): paraphrase slots used (balanced across selected templates)
  - R (int): replicates per slot
  - T (int, optional): number of templates to include from the bank (<= size of bank)
  - B (int): bootstrap resamples (default 5000)
  - max_output_tokens (int)
  - prompts_file (str, optional): explicit prompt YAML path (overrides prompt_version)

Outputs & Interpretation
- Aggregates:
  - prob_true_rpl: model prior after robust aggregation (probability)
  - ci95: cluster‑aware 95% bootstrap CI in probability space
  - ci_width: CI width (probability space)
  - stability_score: 1/(1+IQR) on per‑template mean logits
  - rpl_compliance_rate: fraction of samples that returned strict JSON and no URLs/citations
  - cache_hit_rate: fraction of attempted samples served from cache
- Aggregation diagnostics:
  - counts_by_template: counts per paraphrase cluster (by prompt_sha256)
  - imbalance_ratio: max/min counts across templates (planned should be ~1)
  - template_iqr_logit: IQR of per‑template means (logit space)
- Provenance:
  - bootstrap_seed, prompt_version, provider_model_id (from provider), prompt_sha256 (per sample)
- Persistence:
  - SQLite DB: runs/heretix.sqlite (tables: runs, samples)
  - JSON summary file: path passed to --out
  - JSONL batch file: if `--out` ends with `.jsonl` and `claims_file` is set, one JSON object per claim is written

Repository Map (Active)
- heretix/cli.py: Typer CLI (heretix run)
- heretix/rpl.py: end‑to‑end RPL runner (sampling, cache, aggregation, persistence)
- heretix/aggregate.py: equal‑by‑template weighting, 20% trimmed center (T>=5), cluster bootstrap (B=5000)
- heretix/seed.py: deterministic bootstrap seed derivation
- heretix/metrics.py: stability metrics (from template IQR)
- heretix/prompts/rpl_g5_v2.yaml: system, user template, paraphrase bank (version: rpl_g5_v2_2025-08-21)
- heretix/provider/openai_gpt5.py: GPT‑5 Responses API adapter with reasoning‑flag fallback
- heretix/storage.py: SQLite schema (runs/samples), insert/get helpers
- heretix/cache.py: cache key helper (used via storage)
- legacy/*: archived; do not modify or import from legacy in heretix/

Invariants & Guardrails (Frozen)
- Estimator math (do not change without version bump and approval):
  - Aggregate in logit space
  - Equal‑by‑template weighting before global center
  - Trimmed center (20%) when number of templates T >= 5
  - Cluster bootstrap with deterministic seed (report B and bootstrap_seed)
- RPL policy:
  - No retrieval/citations; JSON‑only outputs following schema
  - Samples with URLs/citations or invalid JSON are excluded from aggregation
- Provenance:
  - Log prompt_version and provider model id
  - Cache/provenance keyed by prompt_sha256 (exact system+schema+user text)
- Tooling:
  - Use uv for all commands; do not switch tooling without approval

Common Tasks (Recipes)
- Run a mock RPL for fast iteration:
  - uv run heretix run --config runs/rpl_example.yaml --mock --out runs/smoke.json
- Increase sample size or rebalance paraphrases:
  - Edit K/R/T in the config; the sampler balances counts across selected templates
- Investigate wide CI or low stability:
  - Check counts_by_template, imbalance_ratio, and template_iqr_logit in the JSON
  - Increase K and/or T or adjust T to exclude flakiest templates (do not change estimator)
- Modify prompts/paraphrases:
  - Edit heretix/prompts/rpl_g5_v2.yaml
  - If semantics change, bump the version string (e.g., rpl_g5_v3_YYYY‑MM‑DD) and run with the new version
- Debug provider JSON failures:
  - heretix/provider/openai_gpt5.py already retries without reasoning flag if needed
  - Ensure outputs are strict JSON and contain prob_true

PR Instructions (Phase‑1 Testing)
- Title: [RPL][Phase‑1] <short imperative title>
- Must run locally before merge:
  - uv run pytest -q
  - Prefer --mock for speed unless your change targets provider behavior
- If executing live provider calls, note the model id and prompt_version in the PR description
- Do not modify:
  - heretix/aggregate.py estimator logic
  - heretix/prompts/rpl_g5_v2.yaml semantics (without version bump/approval)
  - CLI contract (heretix run) without coordination

Notes & Known Gaps (Roadmap)
- Auto‑RPL controller and monitor/inspect/summarize commands are specified in documentation but not exposed in the current CLI; treat them as roadmap
- Makefile targets referencing heretix-rpl are legacy and not aligned with the new CLI
- Future lenses (MEL/HEL/SEL) and telemetry (DE/HDI) are planned; do not stub them into the CLI until approved

References
- Stats & estimator spec: documentation/STATS_SPEC.md
- Output anatomy & interpretation: documentation/output_anatomy.md, documentation/interpretation_guide.md, documentation/RPL-JSON-output.md
- Refactor plan: refactor.md
- README quick start: README.md

Truth north: Pay for movement and durability, expose priors and amplifiers, and make every number auditably boring. This repository uses uv; do not switch tooling without explicit approval.
