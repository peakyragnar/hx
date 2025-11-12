# Grok (xAI) Integration — Production Plan (Phase‑1)

Purpose
- Add Grok as a first‑class provider for Heretix RPL with minimal, reliable changes.
- Preserve estimator/DB invariants; keep CLI/API contracts stable.
- Target Grok 5 explicitly and verify model identity at runtime.

Scope (MVP)
- Single‑provider runs: allow `model: grok-5` end‑to‑end (CLI, API, UI).
- No estimator changes; no DB schema changes; reuse existing cache/seed logic.
- UI remains single‑select between GPT‑5 and Grok‑5 (multi‑model compare comes next phase).

Requirements
- Env vars
  - `GROK_API_KEY` (or `XAI_API_KEY`) set with a valid xAI key.
  - Optional rate limits: `HERETIX_XAI_RPS=1`, `HERETIX_XAI_BURST=2`.
  - Feature flag to expose in UI/API: `HERETIX_ENABLE_GROK=1`.
- Runtime
  - Python 3.10+, uv, existing Heretix stack.

Target Model (Grok 5)
- Public xAI docs and model ids may vary by release; the product intent is “Grok 5”.
- Heretix will use the model label `grok-5` in config/UI and pass through to xAI.
- Verification step (runtime): assert the provider‑reported `provider_model_id` equals an allowlist containing `grok-5` (and any documented equivalent like `grok-5-latest`).
  - If mismatch, log a high‑visibility warning and include `provider_model_id` in provenance.
  - We will ship a small probe script (optional) to print the effective model id from a trivial call.

Architecture Changes (minimal)
1) Provider registry (NEW: `heretix/provider/registry.py`)
   - `get_scorer(model: str, use_mock: bool) -> Callable` returning the correct `score_claim()`.
   - Mapping:
     - `gpt-5` → `heretix.provider.openai_gpt5.score_claim`
     - `grok-5` → `heretix.provider.grok_xai.score_claim`
     - mock path → `heretix.provider.mock.score_claim_mock`
   - Optionally return `capabilities` (supports_reasoning, supports_temperature) for future use.

2) Grok adapter (NEW: `heretix/provider/grok_xai.py`)
   - Transport: OpenAI SDK with xAI base URL
     - `OpenAI(api_key=os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY"), base_url="https://api.x.ai/v1")`
   - Inputs: identical signature to GPT‑5 scorer (`claim, system_text, user_template, paraphrase_text, model='grok-5', max_output_tokens`).
   - Instructions: identical strict JSON schema (prob_true, confidence_self, assumptions, reasoning_bullets, contrary_considerations, ambiguity_flags). No URLs/citations.
   - API shape:
     - Prefer `client.responses.create(...)` (if supported). If not, fallback to `client.chat.completions.create(...)` with messages.
   - Determinism: set `temperature=0` (if available). Do not send OpenAI reasoning flags unless xAI documents compatibility.
   - Parsing: prefer `resp.output_text`; else walk structured fields; else parse message text. On invalid JSON or policy violation, retry once with a small jitter.
   - Return shape: `{ raw, meta:{provider_model_id,prompt_sha256,response_id,created}, timing:{latency_ms} }`.
   - Rate limiting: `_XAI_RATE_LIMITER = RateLimiter(rate_per_sec=HERETIX_XAI_RPS or 1, burst=HERETIX_XAI_BURST or 2)`.
   - Model identity guard: compare reported `provider_model_id` with allowlist including `grok-5`/`grok-5-latest`; add a warning field when mismatched.

3) RPL provider switch (MOD: `heretix/rpl.py`)
   - Replace direct GPT‑5 import with registry lookup:
     - `score = get_scorer(cfg.model, use_mock)`
   - Keep sampling, cache keys, aggregation, seed derivation, and DB writes unchanged.

4) API/CLI/UI (unchanged for contract; small exposure tweaks)
   - CLI: users can set `model: grok-5` in run config; no new flags required.
   - API `/api/checks/run`: accepts `model: "grok-5"` already; no schema changes.
   - UI server: expose a single‑select choice (GPT‑5 or Grok‑5) behind `HERETIX_ENABLE_GROK=1`.

Configuration & Setup
- .env additions
  - `GROK_API_KEY=...`  (or `XAI_API_KEY=...`)
  - `HERETIX_XAI_RPS=1`
  - `HERETIX_XAI_BURST=2`
  - `HERETIX_ENABLE_GROK=1`
- Quick test (mock):
  - `uv run heretix run --config runs/rpl_example.yaml --mock --out runs/grok_mock.json` with `model: grok-5`
- Quick test (live):
  - `export GROK_API_KEY=...`
  - `uv run heretix run --config runs/rpl_example.yaml --out runs/grok_live.json` with `model: grok-5`

Testing Strategy (robust)

Unit tests (NEW: `tests/test_grok_provider.py`)
- JSON extraction
  - Parses valid JSON from `responses.create` and from `chat.completions.create` fallback.
  - Non‑JSON text triggers one retry; second failure yields `raw={}` and `json_valid=0` upstream.
- Policy enforcement
  - Responses containing URLs/citations are flagged and excluded by RPL (verify `_has_citation_or_url`).
- Rate limiting
  - Calls acquire the xAI rate limiter (mocked clock, assert acquire order).
- Prompt hashing
  - `prompt_sha256` must match GPT‑5 logic for identical system/schema/user text.
- Provider identity
  - `meta.provider_model_id` is captured; if not in {`grok-5`,`grok-5-latest`}, a warning flag is surfaced.
- Determinism
  - With `temperature=0`, identical inputs produce the same parsed `prob_true` under mocked transport.

RPL integration tests (extend existing patterns)
- Mock path end‑to‑end
  - Running RPL with `model: grok-5`, `mock=True` yields aggregates and CI without network.
  - Cache keys include `model`, ensuring isolation from GPT‑5 runs.
- Seed and run_id
  - `run_id` changes with `model`; bootstrap seed precedence unchanged.
- Compliance and aggregation
  - Samples with invalid JSON or URL leakage are excluded; CI and stability computed on valid subset only (unchanged estimator).

API/UI tests
- API (mock mode)
  - `/api/checks/run` accepts `model: "grok-5"` and returns prior/combined payloads identical in shape to GPT‑5.
- UI server
  - Model radio/chips select Grok‑5; selection is written into temp config; results render; Explain bottom sheet opens; mobile layout intact.

Manual live verification (staging)
- With `GROK_API_KEY` set, run 3–5 short claims; confirm:
  - `provenance.rpl.provider_model_id` equals `grok-5` (or allowlisted variant).
  - JSON compliance rate is high (≥0.98 typical), CI widths reasonable, no URLs.
  - Latency within acceptable bounds; rate limits not exceeded with default RPS.

Operational Notes
- No estimator or schema changes; aggregation remains in logit space with equal‑by‑template weighting and 20% trim for T≥5.
- Caching: sample keys include `model` and `max_output_tokens`; no collisions across providers.
- Seeds: unchanged derivation; provenance records `bootstrap_seed` and prompt version.

Rollout Plan
1) Merge behind flag: registry + adapter + rpl switch; `HERETIX_ENABLE_GROK=0` by default.
2) Staging: enable flag, configure key, run smoke + a few live runs; monitor compliance and CI width.
3) Production: enable flag; keep GPT‑5 as default; Grok‑5 selectable.

Troubleshooting
- 401/403: confirm `GROK_API_KEY` present and valid; base URL `https://api.x.ai/v1` reachable.
- Empty/invalid JSON: check token cap (`max_output_tokens`), reduce claim length, or re‑run with `HERETIX_RPL_NO_CACHE=1`.
- Model mismatch: if `provider_model_id` != allowlist, update allowlist or confirm xAI model naming.

Future (not in MVP)
- Add Gemini via the same registry and adapter pattern.
- Multi‑model compare endpoint (`/api/checks/run_multi`) and mobile tabs for side‑by‑side UX.
- Native iOS app consuming the stable API payload.

