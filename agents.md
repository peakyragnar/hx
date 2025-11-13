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
    - models: optional list → run the same claim across multiple models (e.g., gpt-5, grok-4, deepseek-r1)
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
  - Add `--mode web_informed` to blend in the Web-Informed Lens when you want prior + web
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
  - HERETIX_CONCURRENCY: optional bounded thread pool for provider calls (e.g., 6–8). Default off.
  - ANON_COOKIE_NAME: optional override for the anonymous usage cookie (defaults to `heretix_anon`).
- Database:
  - Start local Postgres with `docker compose up -d postgres` (connection string `postgresql+psycopg://heretix:heretix@localhost:5433/heretix`).
  - Run `alembic upgrade head` after schema changes; stop services via `docker compose down`.
  - Production deployments load credentials from `DATABASE_URL_PROD` (Neon project).
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
  - SQLite database created at runs/heretix.sqlite (legacy runs/samples plus new checks rows)
  - JSON artifact written to the path passed via --out

CLI (Current)
- Entrypoints:
  - `uv run heretix describe --config <file>`: print effective config and sampling plan (no network)
  - `uv run heretix run --config <file> [--out <file>] [--mock] [--dry-run] [--mode baseline|web_informed] [--database-url <db>]`
- Config file keys (YAML/JSON):
  - claim (str)
  - model (str): gpt-5
  - models (list[str], optional): overrides `model` and runs each entry sequentially; CLI `--model` flags take precedence
  - prompt_version (str): rpl_g5_v2
  - K (int): paraphrase slots used (balanced across selected templates)
  - R (int): replicates per slot
  - T (int, optional): number of templates to include from the bank (<= size of bank)
  - B (int): bootstrap resamples (default 5000)
  - seed (int, optional): bootstrap seed; precedence is config seed > HERETIX_RPL_SEED env > derived deterministic
  - max_prompt_chars (int, default 1200): hard cap on composed prompt length (system+schema+user); run fails fast if exceeded
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
  - Seeds: runs row stores both configured `seed` (if any) and effective `bootstrap_seed` for auditability

Repository Map (Active)
- heretix/cli.py: Typer CLI (heretix run) feeding the shared RPL/WEL pipeline (persists into `checks`)
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
- Run a claim through multiple models:
  - Config-driven: add `models: [gpt-5, grok-4, deepseek-r1]` to your YAML
  - CLI override: `uv run heretix run --config runs/rpl_example.yaml --model gpt-5 --model grok-4 --mock`
- Faster live run (optional concurrency, CLI):
  - HERETIX_CONCURRENCY=8 uv run heretix run --config runs/rpl_example.yaml --out runs/faster.json
- Faster live run (UI):
  - HERETIX_CONCURRENCY=8 UI_PORT=7799 uv run python ui/serve.py
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
- Documentation index: documentation/README.md
- How to run (end‑to‑end): documentation/how-to-run.md
- Configuration details: documentation/configuration.md
- SQLite tips and queries: documentation/sqlite.md
- Stats & estimator spec: documentation/STATS_SPEC.md
- Refactor plan: refactor.md
- README quick start: README.md
 - Faster runs and guidance: faster-processing.md

Truth north: Pay for movement and durability, expose priors and amplifiers, and make every number auditably boring. This repository uses uv; do not switch tooling without explicit approval.

## MCP Agent Mail: coordination for multi-agent workflows

What it is
- A mail-like layer that lets coding agents coordinate asynchronously via MCP tools and resources.
- Provides identities, inbox/outbox, searchable threads, and advisory file reservations, with human-auditable artifacts in Git.

Why it's useful
- Prevents agents from stepping on each other with explicit file reservations (leases) for files/globs.
- Keeps communication out of your token budget by storing messages in a per-project archive.
- Offers quick reads (`resource://inbox/...`, `resource://thread/...`) and macros that bundle common flows.

How to use effectively
1) Same repository
   - Register an identity: call `ensure_project`, then `register_agent` using this repo's absolute path as `project_key`.
   - Reserve files before you edit: `file_reservation_paths(project_key, agent_name, ["src/**"], ttl_seconds=3600, exclusive=true)` to signal intent and avoid conflict.
   - Communicate with threads: use `send_message(..., thread_id="FEAT-123")`; check inbox with `fetch_inbox` and acknowledge with `acknowledge_message`.
   - Read fast: `resource://inbox/{Agent}?project=<abs-path>&limit=20` or `resource://thread/{id}?project=<abs-path>&include_bodies=true`.
   - Tip: set `AGENT_NAME` in your environment so the pre-commit guard can block commits that conflict with others' active exclusive file reservations.

2) Across different repos in one project (e.g., Next.js frontend + FastAPI backend)
   - Option A (single project bus): register both sides under the same `project_key` (shared key/path). Keep reservation patterns specific (e.g., `frontend/**` vs `backend/**`).
   - Option B (separate projects): each repo has its own `project_key`; use `macro_contact_handshake` or `request_contact`/`respond_contact` to link agents, then message directly. Keep a shared `thread_id` (e.g., ticket key) across repos for clean summaries/audits.

Macros vs granular tools
- Prefer macros when you want speed or are on a smaller model: `macro_start_session`, `macro_prepare_thread`, `macro_file_reservation_cycle`, `macro_contact_handshake`.
- Use granular tools when you need control: `register_agent`, `file_reservation_paths`, `send_message`, `fetch_inbox`, `acknowledge_message`.

Common pitfalls
- "from_agent not registered": always `register_agent` in the correct `project_key` first.
- "FILE_RESERVATION_CONFLICT": adjust patterns, wait for expiry, or use a non-exclusive reservation when appropriate.
- Auth errors: if JWT+JWKS is enabled, include a bearer token with a `kid` that matches server JWKS; static bearer is used only when JWT is disabled.


## Integrating with Beads (dependency-aware task planning)

Beads provides a lightweight, dependency-aware issue database and a CLI (`bd`) for selecting "ready work," setting priorities, and tracking status. It complements MCP Agent Mail's messaging, audit trail, and file-reservation signals. Project: [steveyegge/beads](https://github.com/steveyegge/beads)

Recommended conventions
- **Single source of truth**: Use **Beads** for task status/priority/dependencies; use **Agent Mail** for conversation, decisions, and attachments (audit).
- **Shared identifiers**: Use the Beads issue id (e.g., `bd-123`) as the Mail `thread_id` and prefix message subjects with `[bd-123]`.
- **Reservations**: When starting a `bd-###` task, call `file_reservation_paths(...)` for the affected paths; include the issue id in the `reason` and release on completion.

Typical flow (agents)
1) **Pick ready work** (Beads)
   - `bd ready --json` → choose one item (highest priority, no blockers)
2) **Reserve edit surface** (Mail)
   - `file_reservation_paths(project_key, agent_name, ["src/**"], ttl_seconds=3600, exclusive=true, reason="bd-123")`
3) **Announce start** (Mail)
   - `send_message(..., thread_id="bd-123", subject="[bd-123] Start: <short title>", ack_required=true)`
4) **Work and update**
   - Reply in-thread with progress and attach artifacts/images; keep the discussion in one thread per issue id
5) **Complete and release**
   - `bd close bd-123 --reason "Completed"` (Beads is status authority)
   - `release_file_reservations(project_key, agent_name, paths=["src/**"])`
   - Final Mail reply: `[bd-123] Completed` with summary and links

Mapping cheat-sheet
- **Mail `thread_id`** ↔ `bd-###`
- **Mail subject**: `[bd-###] …`
- **File reservation `reason`**: `bd-###`
- **Commit messages (optional)**: include `bd-###` for traceability

Event mirroring (optional automation)
- On `bd update --status blocked`, send a high-importance Mail message in thread `bd-###` describing the blocker.
- On Mail "ACK overdue" for a critical decision, add a Beads label (e.g., `needs-ack`) or bump priority to surface it in `bd ready`.

Pitfalls to avoid
- Don't create or manage tasks in Mail; treat Beads as the single task queue.
- Always include `bd-###` in message `thread_id` to avoid ID drift across tools.
