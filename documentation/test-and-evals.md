# Test & Evaluation Strategy (Phase‑1 Harness)

This note captures which suites we expect engineers and agents to run while extending the
Phase‑1 RPL/WEL harness. It mirrors the structure from `multi-ai-plan.md` section 12 and
points to the concrete files that now live in the repo.

## 1. Test layout

```
heretix/tests/
  test_schemas.py                # Canonical payload + rejection cases for RPLSampleV1, WELDocV1, blocks, simple_expl
  test_json_utils.py             # JSON repair + validation warnings
  test_verdicts.py               # Combined weighting + verdict labelling
  test_phase1_*                  # Harness + DB invariants
  test_openai_provider.py        # Live adapter scaffold (mocked HTTP)
  test_grok_provider.py
  test_gemini_provider.py
  test_ui_cards.py               # Landing-page card renderer regression coverage
  test_ui_multiselect.py         # New multi-model input + Promise.allSettled contract
tests/evals/test_evals_smoke.py  # End-to-end run_evals.py smoke test
```

Provider adapter tests stub network calls (responses/httpx_mock) so they can run inside CI
without keys. Live-provider checks continue to live under `test_live_providers.py` and remain
`pytest.mark.live` gated.

## 2. Commands to run

- Everything (default CI target):
  ```
  uv run pytest -q
  ```
- Schema / JSON utils only (fast path when editing `heretix/schemas` or parsing helpers):
  ```
  uv run pytest heretix/tests/test_schemas.py heretix/tests/test_json_utils.py -q
  ```
- UI-only changes (locks multi-model grid + cards):
  ```
  uv run pytest heretix/tests/test_ui_multiselect.py heretix/tests/test_ui_cards.py -q
  ```
- API smoke test when touching FastAPI wiring:
  ```
  uv run pytest heretix/tests/test_phase1_cli_new.py api/tests/test_run_endpoint.py -q
  ```

## 3. Eval dataset & runner

- Claims live under `cohort/evals/claims_calibration.jsonl`. Each line contains
  `{ "id": "…", "claim": "…", "label": 0|1 }` so we can compute calibration metrics.
- Runner: `scripts/run_evals.py`
  ```
  uv run python scripts/run_evals.py \
    --provider openai \
    --logical-model gpt-5 \
    --mode baseline \
    --claims-file cohort/evals/claims_calibration.jsonl \
    --out evals/openai-gpt5-baseline.json \
    --mock
  ```
  Fields in the JSON payload:
  - `results`: individual claim scores + CI95 snapshots.
  - `metrics`: `brier`, `ece`, and `count` — asserted in `tests/evals/test_evals_smoke.py`.

`tests/evals/test_evals_smoke.py` shells out to the script with the mock provider so CI never
hits the network yet still guarantees that the file is created and that `metrics` contains the
expected keys.

## 4. Live provider smoke tests (optional)

- Marked with `@pytest.mark.live` and skipped unless the relevant API key is set.
- Quick sanity example:
  ```
  OPENAI_API_KEY=sk-… uv run pytest heretix/tests/test_live_providers.py -k gpt5 -q
  ```
- Use sparingly (nightly or manual verification) because they incur cost.

## 5. Checklist before opening a PR

1. Run `uv run pytest -q` (or the focused command that covers your change) and make sure the
   new regression tests above pass.
2. If you changed provider adapters or eval math, run `uv run python scripts/run_evals.py …`
   against the mock claims file to confirm we still emit `brier`/`ece`.
3. Capture the commands + outcomes inside PR descriptions or bead notes so future agents know
   which coverage already exists.
