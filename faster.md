Faster Response Plan (UI + API)
===============================

Goals
- Keep model fidelity: user-selected models (gpt-5, grok-4, gemini-2.5) must be used as requested; no model swaps.
- Cut wall-clock latency for UI runs without changing estimator math or policy.

Plan
- Model fidelity: Audit adapters/factory to ensure requested models are used and no “reasoning” flags are set for gpt-5/grok-4/gemini-2.5.
- Faster but safe rate limits: Provide HERETIX_PROVIDER_CONFIG with higher conservative limits (OpenAI 5 rps / burst 10; Grok 3/6; Gemini 3/6). Raise further if no 429s.
- Clamp sampling defaults (no opt-in): For UI runs, shrink sampling to something like K=4, R=1, T=4, B=200 to reduce calls while keeping estimator logic unchanged.
- Concurrency aligned to limits: Set HERETIX_CONCURRENCY to ~8–12 so parallelism matches the raised rate limits and avoids self-throttling.
- Caching on: Ensure UI path keeps caching enabled; no `no_cache` unless explicitly requested.
- Visibility: Add per-provider timing/wall-clock logs to identify slow lanes and validate speed gains.
