# Simple Explanation (SimpleExpl) – Design Plan

This document describes how we generate plain‑language explanations for RPL verdicts, without changing the underlying RPL math or sampling. It focuses on:

- What data the explainer sees.
- How many LLM calls we make.
- How per‑model explanations work (GPT‑5, Grok‑4, Gemini).
- How this stays compatible with Phase‑1 tests and the existing CLI/API.

## 1. High‑Level Goals

- Keep the **RPL estimator and sampling unchanged** (K/R/T, logit aggregation, CI, stability, etc.).
- After a run completes, produce a **simple, human‑readable explanation** of the verdict.
- Use **one explanation call per model per run**, not per paraphrase or replicate.
- Let **each model explain its own verdict** (per‑provider narrator), instead of a single GPT‑5 narrator for all.
- Avoid stats jargon; explanations should be understandable to a motivated lay reader.

## 2. Current State (Phase‑1)

Today, the pipeline looks roughly like this:

1. **RPL sampling and aggregation**
   - `heretix/rpl.py` + `heretix/aggregate.py` handle K paraphrases × R replicates, logit‑space aggregation, trimming, bootstrap, etc.
   - Outputs go into `result["aggregates"]` and `result["aggregation"]` (probabilities, CI, stability, diagnostics).

2. **Blocks / verdicts**
   - `heretix/pipeline.py` constructs:
     - `prior_block` (probability, CI, stability).
     - Optional `web_block` (WEL scores, evidence summary).
     - `combined_block` (final `p`, label, prior vs web weights).

3. **Explanation (Simple View)**
   - For live runs (non‑mock), `perform_run` tries:
     - `heretix.explanations_llm.generate_simple_expl_llm(...)`  
       → calls a **single GPT‑5 narrator** via `heretix/provider/expl_openai.py`, using prompts in `heretix/prompts/simple_expl/`.
       → returns a `SimpleExplV1` JSON (`title`, `body_paragraphs`, `bullets`).
   - If that fails, it falls back to deterministic composers in `heretix/simple_expl.py`:
     - `compose_simple_expl` (web‑informed).
     - `compose_baseline_simple_expl` (baseline).
   - The API and CLI surface a simplified “Simple View” based on this explanation.

Issues with the current narrator:

- A single GPT‑5 narrator is used for all providers (GPT‑5, Grok‑4, Gemini).
- The prompt encourages **technical language** (probabilities, CI width, stability, web shift, etc.).
- This yields explanations that read like internal stats reports, not simple bullets for end users.

## 3. Target Design (v2 SimpleExpl)

We keep the RPL math and blocks exactly as they are, and change only the explanation layer.

### 3.1 Separation of Concerns

Per model and per run:

1. **RPL stage (unchanged)**
   - Do K×R sampling, aggregate in logit space, compute CI, stability, etc.
   - Produce `prior_block`, optional `web_block`, and `combined_block` with the final verdict.

2. **Explanation stage (new shape)**
   - Make **one LLM call per model** to generate a `SimpleExplV1` description.
   - The explainer **does not resample** or change the probability; it only narrates.
   - Each provider (GPT‑5, Grok‑4, Gemini) has its own explanation adapter and prompt variant.

### 3.2 Context Object for the Explainer

Instead of exposing raw internals, we pass a **small, bucketed context** to the explanation LLM.

For each model, the context JSON will look roughly like:

```json
{
  "claim": "Elon Musk is a great entrepreneur.",
  "mode": "baseline",
  "verdict": "Likely true",
  "prob_true": 0.655,
  "web": {
    "enabled": false,
    "shift": "no_change",
    "shift_phrase": "no web adjustment (prior only)",
    "docs_bucket": "none"
  },
  "confidence": {
    "stability_level": "medium",   // "low" | "medium" | "high"
    "precision_level": "narrow",   // "wide" | "medium" | "narrow"
    "compliance_ok": true
  },
  "sampling": {
    "paraphrases": "several wordings",
    "replicates": "multiple samples"
  }
}
```

Notes:

- `verdict` is a label like `"Likely true" | "Uncertain" | "Likely false"`, derived from the combined probability.
- `prob_true` is present but the narrator is encouraged to use **qualitative** phrases (“about two‑thirds likely”).
- `web` uses **coarse buckets**:
  - `enabled`: whether the run was `web_informed`.
  - `shift`: `"up" | "down" | "no_change"` based on how much the web lens moved the verdict.
  - `docs_bucket`: `"none" | "few" | "several"` from `n_docs`.
- `confidence` is derived from CI width, stability, and compliance, but expressed as `"low/medium/high"` and `"wide/medium/narrow"` rather than raw numbers.
- `sampling` describes K/R/T qualitatively (“several wordings”, “multiple samples”) instead of exposing exact counts.

### 3.3 Output Schema (SimpleExplV1)

We keep `heretix/schemas/simple_expl_v1.py` as the canonical schema:

- `title: str`
- `body_paragraphs: List[str]`
- `bullets: List[str]`

With the following constraints for the narrator:

- **Title**
  - ≤ 90 characters.
  - Factual and verdict‑tied, e.g. “Why this looks likely true”.
  - No hype or clickbait.

- **Body paragraphs**
  - 1–2 short paragraphs (2–3 sentences each).
  - Explain:
    - What the claim is about (in plain language).
    - How the model’s prior patterns (and web evidence, if present) point toward the verdict.
    - Any important caveats, described qualitatively.

- **Bullets**
  - 2–4 bullets, ideally 3.
  - Each < 120 characters.
  - Cover:
    - A primary reason the model leans toward this verdict.
    - A note about the web lens (used vs skipped, nudged vs unchanged).
    - A way the verdict might change with new evidence or clearer assumptions.

### 3.4 Language and Jargon Rules

To keep explanations user‑friendly:

- **Avoid stats jargon**
  - Do NOT mention: “confidence interval”, “CI”, “stability score”, “imbalance”, “logit”, “bootstrap”, “templates”.
  - Use phrases like:
    - “a narrow range around this answer” instead of “tight confidence interval”.
    - “rewordings mostly agreed” instead of “high stability score”.

- **Probabilities**
  - If probabilities are mentioned, round to **one decimal place** at most.
  - Prefer verbal phrases: “about two‑thirds likely”, “roughly even odds”, “much more likely than not”.

- **Web lens**
  - If `web.enabled == false`:
    - Explicitly say that the verdict is based on prior knowledge only; the web lens was skipped.
  - If `web.enabled == true` and `docs_bucket == "none"`:
    - Say that the web lens did not find usable articles, so the model leaned on its prior patterns.
  - If `docs_bucket` is `"few"` or `"several"`:
    - Explain qualitatively whether those articles mostly supported, contradicted, or mixed with the prior.
    - Mention if the web lens nudged the verdict or left it near the prior (`shift` / `shift_phrase`).

- **Uncertainty**
  - For “Uncertain” verdicts:
    - Emphasize ambiguity, missing details, or conflicting patterns.
    - Make it clear that the model sees reasons both for and against.
  - For “Likely true” / “Likely false”:
    - Explain why the weight of patterns points that way.
    - Still include at least one caveat or condition that could change the judgment.

### 3.5 Per‑Model Narrators

We use the existing explanation registry in `heretix/provider/registry.py`:

- `register_expl_adapter(aliases, fn)`
- `get_expl_adapter(model)`

Each model gets its own explanation adapter:

- **GPT‑5**
  - Already implemented via `heretix/provider/expl_openai.py:write_simple_expl`.
  - We will update the prompt to use the new shared + provider‑specific v2 instructions.

- **Grok‑4**
  - New adapter (e.g. `heretix/provider/expl_grok.py`) that:
    - Uses the XAI client to call Grok‑4.
    - Applies the same Explanation Lens contract and returns `{ "text": <JSON>, "telemetry": ... }`.

- **Gemini 2.5**
  - New adapter (e.g. `heretix/provider/expl_gemini.py`) that:
    - Uses the Gemini client.
    - Applies the same Explanation Lens contract.

Prompt resources:

- Shared instructions:
  - `heretix/prompts/simple_expl/shared_v2.md`
- Provider‑specific add‑ons:
  - `heretix/prompts/simple_expl/openai_v2.md`
  - `heretix/prompts/simple_expl/grok_v2.md`
  - `heretix/prompts/simple_expl/gemini_v2.md`

`build_simple_expl_prompt(...)` in `heretix/prompts/prompt_builder.py` will:

- Load the shared v2 instructions plus the provider‑specific variant.
- Inject the claim and the JSON context into the user message.

### 3.6 Mock vs Live Runs

To preserve Phase‑1 behavior and tests:

- **Mock runs (`--mock`)**
  - Continue to use deterministic composers in `heretix/simple_expl.py`:
    - `compose_simple_expl` for web‑informed.
    - `compose_baseline_simple_expl` for baseline.
  - These functions produce a simple explanation dict (`title`, `lines`, `summary`) without hitting any LLM.
  - `perform_run` keeps this fallback logic for mock mode.

- **Live runs**
  - `perform_run` (non‑mock) will:
    - Build a bucketed context object from `prior_block`, `web_block`, `combined_block`, and `aggregates`.
    - Call `generate_simple_expl_llm(...)` with:
      - `model=cfg.model` (logical model) and `provider` resolved via `infer_provider_from_model`.
      - The new prompt builder and context.
    - On success, store the resulting `SimpleExplV1` in `artifacts.simple_expl`.
    - On failure, fall back to the deterministic composer.

The CLI (`heretix/cli.py`) and API (`api/main.py`) already surface `simple_expl` and convert it into the `SimpleExplV1` API shape. That contract stays the same; only the narrator’s tone and source model change.

## 4. UX Expectations

For each provider card (GPT‑5, Grok‑4, Gemini) in the UI:

- Numeric panel (unchanged):
  - Final probability and verdict label.
  - CI band visualization, stability, etc., if the UI chooses to show them.

- Simple explanation panel (this spec):
  - One short title (e.g. “Why this looks likely true”).
  - 1–2 paragraphs summarizing how the model interpreted the claim and any web evidence.
  - 2–4 bullets:
    - A main reason for the verdict.
    - A clear statement about what the web lens did or did not add.
    - At least one caveat / “what could change this”.

The end result should feel like:

- “Here’s how this model is thinking about your claim,”
- rather than “Here is how our bootstrap estimator works.”

## 5. Next Implementation Steps (Outline)

Implementation work items (for when we move from design to code):

1. **Prompt resources**
   - Add `heretix/prompts/simple_expl/shared_v2.md`.
   - Add provider add‑ons: `openai_v2.md`, `grok_v2.md`, `gemini_v2.md`.

2. **Context builder**
   - Add a small helper in `heretix/explanations_llm.py` or `heretix/pipeline.py` to:
     - Take `prior_block`, `web_block`, `combined_block`, `aggregates`, and `sampling`.
     - Produce the bucketed context JSON described in §3.2.

3. **Per‑provider adapters**
   - Wire additional explanation adapters for Grok‑4 and Gemini 2.5 via `register_expl_adapter`.
   - Ensure they share the same return envelope as the GPT‑5 explanation adapter.

4. **Pipeline integration**
   - Update `perform_run` to:
     - Use `cfg.model` / `provider_id` when calling `generate_simple_expl_llm`.
     - Keep deterministic composers as fallback, especially in mock mode.

5. **Tests and guardrails**
   - Ensure tests like `test_cli_simple_expl_plain_language_all_models` still pass:
     - No “ci / stability / imbalance / logit / template” tokens in the explanation text.
   - Add narrative spot‑checks in tests for representative claims (subjective, numeric, web‑heavy) if needed.

This completes the design for per‑model, plain‑language explanations that sit cleanly on top of the existing RPL harness without changing any estimator logic.

