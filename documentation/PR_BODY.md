[RPL][Phase‑1] Single‑claim UX, reports + compare, prompts table, PQS

## Summary
- Simplifies harness to single‑claim flow; removes batch code paths.
- Adds clear HTML reports (per‑run, A/B, cohort) for evaluation and attribution.
- Introduces `prompts` table in SQLite for self‑contained prompt provenance.
- Persists PQS and gate flags (compliance/stability/precision) to DB.
- Tightens docs and “how to run” for beginners.

## Key Changes
- CLI/Config
  - `heretix/cli.py`: single‑claim only; fix `--prompt-version` to select YAML by version unless `prompts_file` is set.
  - `heretix/config.py`: remove batch‑only field; keep single‑claim config.
- Reports
  - `scripts/report.py`: per‑run HTML with Gates + PQS; prompt text (system/user/paraphrases) resolved; selected templates, hashes, lengths.
  - `scripts/compare_ab.py`: A/B HTML (single claim) with parity checks, winner logic, and “What changed?” diffs (config + prompt).
  - `scripts/compare_cohort.py`: cohort HTML across many claims; median CI width/stability, mean compliance, median PQS, per‑claim deltas.
- DB/Provenance
  - `heretix/storage.py`: new `prompts` table; adds PQS + gate columns on `runs`/`executions`; auto‑migration (ALTER TABLE) in `_ensure_db`.
  - `heretix/rpl.py`: compute PQS + gates (v1), write to `runs`/`executions`; insert prompt text into `prompts` once per version; estimator unchanged.
- Prompts
  - `heretix/prompts/rpl_g5_v3.yaml`: v3 copy, then tightened to fit under `max_prompt_chars`.
- Docs
  - `documentation/how-to-run.md`: step‑by‑step quick start, A/B and cohort compare, prompt identity, PQS/gates, Chrome open commands.
  - `documentation/database-schema.md`: schema with every column explained.
  - `README.md`, `AGENTS.md`: point to new how‑to; remove batch mode refs.
- Tests
  - Disable `pytest-asyncio` plugin in `pytest.ini` (no async tests; resolves pytest 8 collection issue).

## Not Changed
- Estimator math and RPL policy remain frozen (logit aggregation, equal‑by‑template weighting, 20% trim when T≥5, cluster bootstrap; JSON‑only, no retrieval/URLs).

## Migration Notes
- Schema upgrades are automatic on first run:
  - New `prompts` table
  - New columns on `runs`/`executions`: `pqs`, `gate_compliance_ok`, `gate_stability_ok`, `gate_precision_ok`, `pqs_version`
- Existing DBs: to see PQS on old rows, run the one‑time backfill below (e.g., in DB Browser → Execute SQL):

```sql
-- Backfill PQS v1 and gates for runs
UPDATE runs
SET
  pqs = CAST(100 * (0.4 * stability_score
        + 0.4 * (1 - (CASE WHEN ci_width > 0.5 THEN 0.5 ELSE ci_width END) / 0.5)
        + 0.2 * rpl_compliance_rate) AS INT),
  gate_compliance_ok = CASE WHEN rpl_compliance_rate >= 0.98 THEN 1 ELSE 0 END,
  gate_stability_ok = CASE WHEN stability_score >= 0.25 THEN 1 ELSE 0 END,
  gate_precision_ok = CASE WHEN ci_width <= 0.30 THEN 1 ELSE 0 END,
  pqs_version = COALESCE(pqs_version, 'v1')
WHERE pqs IS NULL OR pqs_version IS NULL;

-- Backfill PQS v1 and gates for executions
UPDATE executions
SET
  pqs = CAST(100 * (0.4 * stability_score
        + 0.4 * (1 - (CASE WHEN ci_width > 0.5 THEN 0.5 ELSE ci_width END) / 0.5)
        + 0.2 * rpl_compliance_rate) AS INT),
  gate_compliance_ok = CASE WHEN rpl_compliance_rate >= 0.98 THEN 1 ELSE 0 END,
  gate_stability_ok = CASE WHEN stability_score >= 0.25 THEN 1 ELSE 0 END,
  gate_precision_ok = CASE WHEN ci_width <= 0.30 THEN 1 ELSE 0 END,
  pqs_version = COALESCE(pqs_version, 'v1')
WHERE pqs IS NULL OR pqs_version IS NULL;
```

## Validation
- Mock run (no network):
  - `uv run heretix run --config runs/rpl_example.yaml --mock --out runs/smoke.json`
- Live run (requires `OPENAI_API_KEY`):
  - `uv run heretix run --config runs/rpl_example.yaml --out runs/rpl.json`
- Per‑run report:
  - `uv run python scripts/report.py && open -a "Google Chrome" runs/report.html`
- A/B compare:
  - `uv run python scripts/compare_ab.py --claim "<claim>" --version-a rpl_g5_v2 --version-b rpl_g5_v3 --out runs/reports/ab.html && open -a "Google Chrome" runs/reports/ab.html`
- Cohort compare:
  - `uv run python scripts/compare_cohort.py --version-a rpl_g5_v2 --version-b rpl_g5_v3 --out runs/reports/cohort.html && open -a "Google Chrome" runs/reports/cohort.html`
- DB checks (DB Browser):
  - `prompts` populated after first run per version
  - `runs`/`executions` contain `pqs` and gate flags
- Tests:
  - `uv run pytest -q`

## Risks
- Auto‑migrations occur at runtime; safe on empty/existing DBs. If YAML content changes without bumping the internal version, the `prompts` table retains the first hash (we log a warning). Best practice is to bump the YAML version on semantic changes.

