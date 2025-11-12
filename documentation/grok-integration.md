# Grok (xAI) Integration — Production Plan (Phase‑1)

Purpose
- Add Grok 4 (fast non-reasoning) as a first-class provider for Heretix RPL with minimal, reliable changes.
- Preserve estimator/DB invariants; keep CLI/API contracts stable.
- Stay aligned with xAI’s published model catalogue (default `grok-4-fast-non-reasoning`).

Scope (MVP)
- Single-provider runs: allow `model: grok-4-fast-non-reasoning` end-to-end (CLI, API, UI).
- No estimator changes; no DB schema changes; reuse existing cache/seed logic.
- UI remains single-select between GPT‑5 and Grok 4 (multi-model compare arrives next phase).

Requirements
- Env vars
  - `GROK_API_KEY` (or `XAI_API_KEY`) set with a valid xAI key.
  - Optional rate limits: `HERETIX_XAI_RPS=1`, `HERETIX_XAI_BURST=2`.
  - `HERETIX_GROK_MODEL` (optional override of the model id; defaults to `grok-4-fast-non-reasoning`).
  - Feature flag to expose in UI/API: `HERETIX_ENABLE_GROK=1`.
- Runtime: Python 3.10+, uv, existing Heretix stack.

Target Model (Grok 4 fast non-reasoning)
- Default provider id: `grok-4-fast-non-reasoning` (non-reasoning, 2M tpm / 480 rpm per docs).
- Allowlist: `grok-4-fast-reasoning`, `grok-4-0709`, `grok-4`, `grok-5`, `grok-beta`, `grok-2-latest` (aliases route to the same adapter if needed).
- Runtime guard: capture `provider_model_id` from xAI and log a warning if it differs from the configured id; persist the raw value in provenance.

Architecture Changes (minimal)
1) Provider registry (`heretix/provider/registry.py`)
   - `get_scorer(model: str, use_mock: bool) -> Callable` returning the correct `score_claim()`.
   - Mapping:
     - `gpt-5` → `heretix.provider.openai_gpt5.score_claim`
     - Grok aliases (`grok-4-fast-non-reasoning`, `grok-4-fast-reasoning`, etc.) → `heretix.provider.grok_xai.score_claim`
     - mock path → `heretix.provider.mock.score_claim_mock`

2) Grok adapter (`heretix/provider/grok_xai.py`)
   - Transport: OpenAI SDK with xAI base URL `https://api.x.ai/v1` (or `XAI_BASE_URL`).
   - Inputs: same signature as GPT‑5 scorer; `model` defaults to `HERETIX_GROK_MODEL` or `grok-4-fast-non-reasoning`.
   - Instructions: same strict JSON schema (prob_true, confidence_self, assumptions, reasoning_bullets, contrary_considerations, ambiguity_flags). No URLs/citations.
   - API flow: try `responses.create` first; fall back to `chat.completions.create` if needed; set `temperature=0`. Avoid unsupported params (no reasoning_e ffort, penalties).
   - Parsing: prefer `resp.output_text`; otherwise scan structured output; final fallback parses chat message text. On invalid JSON/policy failure, retry once with small jitter.
   - Return shape: `{ raw, meta:{provider_model_id,prompt_sha256,response_id,created}, timing:{latency_ms} }`.
   - Rate limiting: `_XAI_RATE_LIMITER = RateLimiter(rate_per_sec=HERETIX_XAI_RPS or 1, burst=HERETIX_XAI_BURST or 2)`.

3) RPL provider switch (`heretix/rpl.py`)
   - Replace direct GPT‑5 import with registry lookup; scorer resolved once per run based on `cfg.model` + `mock` flag.
   - Sampling, aggregation, cache keys, seeds, and DB writes remain untouched.

4) API/CLI/UI (contract-stable)
   - CLI/config: `model: grok-4-fast-non-reasoning` works immediately.
   - API `/api/checks/run`: already accepts `model` strings; no schema change required.
   - UI server: exposes “Grok 4 (xAI)” when `HERETIX_ENABLE_GROK=1`; hidden otherwise.

Configuration & Setup
- `.env` additions:
  - `GROK_API_KEY=...` (or `XAI_API_KEY=...`)
  - `HERETIX_GROK_MODEL=grok-4-fast-non-reasoning` (optional)
  - `HERETIX_XAI_RPS=1`
  - `HERETIX_XAI_BURST=2`
  - `HERETIX_ENABLE_GROK=1`
- Quick test (mock):
  - `uv run heretix run --config runs/rpl_example.yaml --mock --out runs/grok_mock.json` with `model: grok-4-fast-non-reasoning`
- Quick test (live):
  - `export GROK_API_KEY=...`
  - `uv run heretix run --config runs/rpl_example.yaml --out runs/grok_live.json` with `model: grok-4-fast-non-reasoning`

Testing Strategy (robust)

Unit tests (`heretix/tests/test_grok_provider.py`)
- JSON extraction: verifies Responses path and Chat Completions fallback.
- Policy enforcement: ensures URL/citation hits are excluded upstream.
- Rate limiting: asserts `_XAI_RATE_LIMITER.acquire()` is invoked for every request.
- Prompt hashing: confirms Grok’s prompt hash matches GPT‑5 logic.
- Provider identity: asserts `meta.provider_model_id` equals `grok-4-fast-non-reasoning` (or configured override).
- Determinism: `temperature=0` ensures identical inputs produce identical parsed `prob_true` under mocked transport.

RPL integration (mock mode)
- Running `model: grok-4-fast-non-reasoning` with `mock=True` produces aggregates/CI identical in structure to GPT‑5 runs; cache keys remain segregated by model ID.
- Re-running proves seeds/run_ids remain deterministic (run_id hashes include `model`).

API/UI tests
- API: `/api/checks/run` with `model: "grok-4-fast-non-reasoning"` returns prior/combined payloads identical in shape; provenance captures `provider_model_id`.
- UI: selecting “Grok 4 (xAI)” writes the correct `model` into the temp config, updates loading copy (“Measuring how Grok 4’s training data…”) and renders the result card.

Manual live verification (staging)
- With `HERETIX_ENABLE_GROK=1` and valid key, run 3–5 claims; confirm:
  - `provenance.rpl.provider_model_id` == `grok-4-fast-non-reasoning` (unless override).
  - JSON compliance rate ≥0.98; CI/stability similar to GPT‑5.
  - Latency within documented limits; no `429` rate-limit responses at default RPS.

Operational Notes
- No estimator/schema changes. Aggregation stays in logit space with equal-by-template weighting and 20% trim when T≥5.
- Cache identity already includes `model` + `max_output_tokens`; no collisions with GPT‑5 samples/runs.
- Seeds unaffected; provenance continues to record `bootstrap_seed` and prompt version.

Rollout Plan
1. Merge behind flag (`HERETIX_ENABLE_GROK=0`).
2. Staging: enable flag, set key/model envs, run smoke + live claims; monitor JSON compliance/CI width.
3. Production: enable flag; keep GPT‑5 default; “Grok 4 (xAI)” selectable.

Troubleshooting
- 401/403: verify `GROK_API_KEY`/`XAI_API_KEY`, base URL, and account access to the Grok 4 model family.
- Invalid JSON: reduce prompt length or re-run with `HERETIX_RPL_NO_CACHE=1`; inspect sample text for schema violations.
- Model mismatch: if `provider_model_id` differs, update `HERETIX_GROK_MODEL` or extend the allowlist in the adapter.

Future (not in MVP)
- Add Gemini via the same adapter/registry pattern.
- Ship `/api/checks/run_multi` + mobile tabs for side-by-side GPT‑5/Grok comparisons.
- Build the native iOS app on top of the stabilized multi-model API.
