# Heretix RPL — How To Run (Phase‑1, Single‑Claim)

This guide walks you through a full, end‑to‑end run using the new RPL harness, including generating an HTML report and opening it in Chrome.

## 1) Requirements
- Python 3.10+
- uv package manager installed
- OpenAI API key for live runs (`OPENAI_API_KEY`)

## 2) Install dependencies
```
uv sync
```

## 3) Create a run config
Create `runs/rpl_example.yaml` (single‑claim):
```
claim: "tariffs don't cause inflation"
model: gpt-5
prompt_version: rpl_g5_v2
K: 8
R: 2
T: 8
B: 5000
max_prompt_chars: 1200
max_output_tokens: 1024
```

Notes:
- `K` = paraphrase slots; `R` = replicates per slot; `T` = templates used (<= size of the bank in `heretix/prompts/rpl_g5_v2.yaml`).
- `max_prompt_chars` enforces a hard cap on the composed prompt length (system+schema+user); the run fails fast if exceeded.

## 4) Optional: Describe the plan (no network)
```
uv run heretix describe --config runs/rpl_example.yaml
```
This prints template selection, planned counts, rotation offset, and the effective bootstrap seed.

## 5) Live run (network; requires API key)
Set your API key (one of these):
```
export OPENAI_API_KEY=sk-...
# or create a .env file in repo root with: OPENAI_API_KEY=sk-...
```
Run RPL and write a JSON summary:
```
uv run heretix run --config runs/rpl_example.yaml --out runs/rpl.json
```
Stdout shows a compact line with p_RPL, CI95, width, stability, compliance, and cache. The JSON file contains full aggregates and diagnostics.

## 6) Smoke run (no network)
For quick iteration without calling the provider:
```
uv run heretix run --config runs/rpl_example.yaml --mock --out runs/smoke.json
```

## 7) Inspect artifacts
- JSON summary:
```
jq '.runs[0].aggregates' runs/rpl.json
```
- SQLite database (created at `runs/heretix.sqlite`):
```
sqlite3 runs/heretix.sqlite '.tables'
sqlite3 runs/heretix.sqlite "SELECT run_id, datetime(created_at,'unixepoch','localtime') AS ts, claim, prompt_version, K,R,T,B, prob_true_rpl, ci_lo, ci_hi, ci_width, stability_score FROM runs ORDER BY created_at DESC LIMIT 1;"
```
More DB tips are in `documentation/sqlite.md`.

## 8) Optional: Concurrency (faster runs)

Run provider calls in parallel. Estimator/math/DB remain unchanged.

- CLI:
```
HERETIX_CONCURRENCY=6 uv run heretix run --config runs/rpl_example.yaml --out runs/faster.json
```
- UI:
```
HERETIX_CONCURRENCY=6 UI_PORT=7799 uv run python ui/serve.py
```
- Guidance:
  - Start with 6–8 workers; reduce if you see provider throttling.
  - For long claims, set `max_output_tokens: 768–1200` in your config to avoid truncated JSON under load.
  - Cache keys are unchanged; re‑runs benefit from cache regardless of concurrency.

## 8) Generate an HTML report
Create a static HTML report for the latest execution:
```
uv run python scripts/report.py
```
This writes `runs/report.html` with:
- Headline metrics (p_RPL, CI95, width, stability, compliance, cache)
- Prompt text (system, schema, user template)
- Selected templates with resolved user text, prompt_sha256, and prompt length
- Aggregation counts by template hash

To target a specific run or change the output path:
```
uv run python scripts/report.py --run-id <RUN_ID> --out runs/my_report.html
```

## 9) Open the report in Chrome
macOS:
```
open -a "Google Chrome" runs/report.html
```
Other platforms:
- Linux: `google-chrome runs/report.html` or `xdg-open runs/report.html`
- Windows (PowerShell): `Start-Process "chrome.exe" runs\report.html`

## 10) Determinism and cache controls
- Fix bootstrap draws for reproducible CI decisions (does not fix model outputs):
```
HERETIX_RPL_SEED=42 uv run heretix run --config runs/rpl_example.yaml
```
- Bypass cache to force fresh samples:
```
HERETIX_RPL_NO_CACHE=1 uv run heretix run --config runs/rpl_example.yaml
```

DB path override (optional):
- To keep test data out of your main DB, set a different path via env:
```
export HERETIX_DB_PATH=/tmp/heretix_test.sqlite
```
The test suite uses an isolated DB automatically via this env var.

## 11) Prompt versions and identity (read this once)

Prompts are identified by the `version:` string inside the YAML (not the filename). That value is stored in the DB and used in cache keys.

- New prompt version: create or copy a YAML under `heretix/prompts/` (e.g., `rpl_g5_v3.yaml`) and bump the internal `version:` to something like `rpl_g5_v3_YYYY-MM-DD`.
- Running a version: pass `--prompt-version rpl_g5_v3`. The CLI loads `heretix/prompts/rpl_g5_v3.yaml` unless you explicitly set `prompts_file` in the config.
- Uniqueness: `run_id` = hash of `(claim | model | prompt_version_full | K | R)`. Changing the YAML `version:` or K/R creates a new `run_id` (separate row in DB).
- Re‑runs: Re‑running the same `run_id` updates `runs` (aggregate) but always appends a new immutable row in `executions` (history is preserved). Samples reuse cache when possible.

Best practice: always bump `version:` any time you edit system, user_template, or paraphrases.

## 12) A/B compare (single claim) — simple path

Minimal workflow (assumes v2 already exists in DB):

1) Run the new version once (stores v3 in DB):
```
uv run heretix run --config runs/rpl_example.yaml \
  --prompt-version rpl_g5_v3 --out runs/rpl_v3.json
```
2) Generate A/B HTML (read‑only; no model calls):
```
uv run python scripts/compare_ab.py \
  --claim "<your exact claim from the config>" \
  --version-a rpl_g5_v2 --version-b rpl_g5_v3 \
  --since-days 365 --out runs/reports/ab.html && \
open -a "Google Chrome" runs/reports/ab.html
```

Notes:
- Compare is DB‑only; it does not call the model. It needs both versions for the exact claim in the DB.
- Parity: keep `model`, `K/R/T`, `B`, `max_output_tokens` identical; only change `prompt_version`.
- Seed: `HERETIX_RPL_SEED=42` stabilizes bootstrap CI decisions (does not fix model outputs).

What you’ll see in A/B HTML:
- Side‑by‑side metrics (p_RPL, CI width, stability, compliance, PQS) and PASS/FAIL gates.
- Clear winner banner (gates → narrower CI width → higher stability → higher PQS).
- “What changed?”: config diffs and prompt diffs (system/user changed? paraphrase bank sizes and overlap).

## 13) Cohort compare (breadth; DB‑only)

Compare two versions across many claims (latest per claim in a time window):
```
uv run python scripts/compare_cohort.py \
  --version-a rpl_g5_v2 --version-b rpl_g5_v3 \
  --since-days 30 --out runs/reports/cohort.html && \
open -a "Google Chrome" runs/reports/cohort.html
```
Options:
- `--model gpt-5` to restrict model.
- `--claims-file runs/claims.txt` to limit the cohort (one claim per line).

Output:
- Aggregate metrics: median CI width, median stability, mean compliance, median PQS, and cohort winner.
- Per‑claim deltas (B−A) for CI width, stability, PQS; excluded claims listed with parity reasons.

## 14) Understanding PQS and gates

- PQS (0–100): composite quality score summarizing precision, stability, and integrity.
  - PQS = 100 × [0.4 × Stability + 0.4 × (1 − min(CI_width, 0.5)/0.5) + 0.2 × Compliance].
  - 80–100: excellent; 65–79: good; 50–64: marginal; <50: weak.
- Gates (shown with PASS/FAIL):
  - Compliance ≥ 0.98 (strict JSON, no URLs/citations)
  - Stability ≥ 0.25 (templates broadly agree)
  - CI width ≤ 0.30 (≤0.20 ideal)

Use gates to accept/reject; use PQS to choose among passes.

## 15) Troubleshooting

- Missing API key: set `OPENAI_API_KEY` in your shell or `.env`.
- Prompt too long: reduce `K`/`T` or shorten the claim; the run fails fast if `max_prompt_chars` is exceeded.
- Unstable or wide CI: inspect `counts_by_template` and `template_iqr_logit`; adjust `K` and/or `T` or exclude the flakiest templates (do not change estimator math).
- A/B says “Missing latest execution for: A or B”: you haven’t run that prompt version for the exact claim yet (or it’s outside the time window). Run the missing version once, or widen `--since-days`.
- A/B shows “nothing changed” in prompt diffs: version name changed but content is identical; edit system/user/paraphrases to test a real change.

## References
- Configuration details: `documentation/configuration.md`
- SQLite tips and queries: `documentation/sqlite.md`
- Stats & estimator spec: `documentation/STATS_SPEC.md`
- Output review process: `documentation/output-review.md`
