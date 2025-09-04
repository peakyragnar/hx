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

## 11) Troubleshooting
- Missing API key: set `OPENAI_API_KEY` in your shell or `.env`.
- Prompt too long: reduce `K`/`T` or shorten the claim; the run fails fast if `max_prompt_chars` is exceeded.
- Unstable or wide CI: inspect `counts_by_template` and `template_iqr_logit`; adjust `K` and/or `T` or exclude the flakiest templates (do not change estimator math).

## References
- Configuration details: `documentation/configuration.md`
- SQLite tips and queries: `documentation/sqlite.md`
- Stats & estimator spec: `documentation/STATS_SPEC.md`

