Here’s a concise, end-to-end map of the repo and how it all fits together.

What It Does

- Raw Prior Lens (RPL): Elicits a model’s belief P(true) for a claim using only internal knowledge (no retrieval), then aggregates K×R samples into a robust prior with CI and stability.
- Robustness: Neutralizes paraphrase wording effects and decode stochasticity via equal-by-template weighting, trimmed center, and cluster bootstrap with deterministic seeding.
- Provenance: Logs prompt version and model IDs to handle provider drift; outputs full diagnostics.

Key Files (Phase‑1 harness)

- heretix/cli.py: Typer CLI entry for `heretix run`/`heretix describe`; handles config loading, prompt overrides, artifact persistence.
- heretix/rpl.py: End-to-end runner that orchestrates sampling, cache hits, aggregation, and DB writes.
- heretix/sampler.py: Balanced rotation sampler for paraphrase templates (K, R, T planning).
- heretix/aggregate.py: Statistical core implementing equal-by-template weighting, 20% trim (T≥5), cluster bootstrap.
- heretix/prompts/rpl_g5_v2.yaml: System rules, schema, paraphrase bank, and `version` string for provenance.
- heretix/seed.py, heretix/metrics.py, heretix/storage.py, heretix/cache.py: Seed derivation, stability metrics, SQLite schema helpers, and cache key utilities supporting the harness.
- pyproject.toml: uv-based project definition; installs CLI as `heretix`.

How RPL Works (GPT‑5)

- Sampling:
    - K paraphrase slots wrap over 5 fixed templates; R replicates per slot; total N=K×R.
    - Each sample returns JSON with prob_true and structured rationale arrays; meta includes provider_model_id, prompt_sha256.
- Aggregation (logit space):
    - Group by prompt_sha256 (template cluster).
    - Average replicates within template → template means.
    - 20% trimmed center (drop min and max template means when T=5; fallback to mean if T<5).
    - Cluster bootstrap: resample templates with replacement; resample replicates within each; recompute center; CI95 from percentiles.
    - Deterministic RNG: either env override HERETIX_RPL_SEED or computed seed (reproducible CI).
- Stability:
    - Compute IQR on template means (logit space).
    - Calibrated score via stability_from_iqr; band: high/medium/low.
    - is_stable if CI width ≤ stability_width (default 0.20, configurable via env).

CLI Usage

- Example: `uv run heretix run --config runs/rpl_example.yaml --out runs/rpl.json`
- Options:
    - `--mock` enables the deterministic provider stub (no network).
    - `--prompt-version` accepts one or many overrides for A/B runs.
    - `--dry-run` prints the sampling plan without calling the provider or writing to the DB.
- Environment:
    - `OPENAI_API_KEY` required for live runs; skipped when `--mock` or `HERETIX_MOCK=1`.
    - `HERETIX_RPL_SEED` fixes bootstrap order (deterministic CI widths).
    - `HERETIX_CONCURRENCY` bounds parallel provider calls; `HERETIX_DB_PATH` overrides the SQLite location.
- Output highlights:
    - `runs/<name>.json`: aggregates (prob_true_rpl, ci95, width, stability, compliance, cache).
    - `runs/heretix.sqlite`: `runs`, `samples`, `executions`, and `execution_samples` tables keyed by deterministic `run_id`.

Design Invariants

- Always aggregate in logit space.
- Equal-by-template weighting before global center.
- 20% trimmed center when T≥5.
- Cluster bootstrap with deterministic seed, report B and bootstrap_seed.
- Log prompt_version and provider_model_id.

Feature Detection & Guardrails

- GPT‑5 Responses API: embed schema in instructions; first attempt reasoning={"effort":"minimal"} then retry without if not supported. Strict JSON
parsing required.
- Reporting: show paraphrase imbalance; aggregation neutralizes it.

Tests (comprehensive, fast + slow)

- `heretix/tests` covers:
    - Transforms: _logit, _sigmoid invertibility, bounds, monotonicity.
    - Aggregation: equal-by-template invariance, trimming behavior, CI properties, deterministic RNG.
    - Seed: deterministic generation and propagation to bootstrap CIs.
    - Stability: calibrated mapping semantics and robustness to outliers.
    - E2E: pipeline with mocked API; configuration propagation; aggregation selection; partial failure handling.
- Runner: `uv run pytest -q` (or `./run_tests.sh` wrappers); defaults to Phase‑1 harness tests.

Docs You Asked About

- agents.md: Full product spec—RPL implemented; MEL/HEL/SEL planned; metrics (SI, AG, SC, IG); DCM/EPC economics; invariants; CLI interpretation;
roadmap.
- CLAUDE.md: Guardrails for not altering core methodology without approval; reiterates clustered aggregation and diagnostics.
- gpt5design.md: Lens architecture rationale; evidence admissibility; market design and monetization pillars; operational guidance.

Notable Observations

- README briefly mentions “median-of-means”; the actual implemented and documented default is the clustered + trimmed center + cluster bootstrap.
Prefer aggregation.md and agents.md as the canonical methodology.
approach.
- verbosity is referenced in constants but not passed if Responses API doesn’t support it; code feature-detects reasoning and retries safely.

Planned Next Work (from docs)

- Implement MEL/HEL/SEL with retrieval constraints and citation metrics.
- Telemetry (tokens, latency), DE and HDI instrumentation; Budget Lens sweeps.
- Market wiring (DCM/EPC) to Δ‑logit and durable Δ; calibration, reliability diagrams.
- Minimal web UI for lens vectors and market dashboards.

If you want, I can quiz you Socratically on:

- Why cluster bootstrap vs flat bootstrap.
- Why logit space averaging is required and how trim interacts with T.
- How HERETIX_RPL_SEED influences reproducibility but not model outputs.
- Interpreting imbalance_ratio and template_iqr_logit.
- The invariants you must not break.
