# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This project uses uv (NOT venv)

## ⚠️ IMPORTANT: Core Design Integrity

**NEVER make changes to the core design methodology without explicitly asking the user first.** This includes:
- Statistical aggregation methods
- Evaluation lens definitions
- Sampling strategies
- Core metrics calculations
- Economic model fundamentals

Always propose changes and get approval before modifying these foundational elements.

## Project Overview

This repository contains the conceptual design for **Heretix**, a truth-scoring and belief evaluation platform. The system is designed to measure how AI models' beliefs change when exposed to different types of evidence and sources, with the goal of exposing consensus amplification and rewarding genuine intellectual discovery.

## Core Architecture Concepts

The system operates on four evaluation lenses:

1. **Raw Prior Lens (RPL)** - Model responses without external retrieval or citations
2. **Mainstream Evidence Lens (MEL)** - Responses constrained to canonical/official sources  
3. **Heterodox Evidence Lens (HEL)** - Non-mainstream but documented sources
4. **Sandbox Evidence Lens (SEL)** - Reasoning from only provided artifacts

## Key Metrics

- **Shock Index (SI)**: Difference between raw prior and heterodox evidence beliefs
- **Amplification Gap (AG)**: How mainstream retrieval reinforces or corrects model priors
- **Source Concentration (SC)**: Citation diversity measurement
- **Information Gain (IG)**: Belief updates measured via KL-divergence

## Economic Model

The platform uses a dual-pool system (Heretic/Orthodox) with:
- **Dynamic Claim Markets (DCM)**: Share-based betting on claim outcomes
- **Epistemic Prediction Communities (EPC)**: Rewards for durable belief updates
- **Exploration Track**: Reputation-based discovery without monetary stakes
- **Adjudication Track**: Cash payouts for robust outcomes

## Current Implementation: Raw Prior Lens (RPL)

The RPL module is now implemented with a robust statistical methodology designed to handle GPT-5's inherent stochasticity.

### Clustered Aggregation Methodology

The system uses a **clustered aggregation** approach to ensure unbiased estimation:

#### The Problem We Solved
When requesting K paraphrases but having only 5 templates, the system would wrap around (e.g., K=7 means templates 0,1 get used twice). This created bias where some paraphrase templates had double weight in the final estimate.

#### The Solution: Equal-by-Template Aggregation
1. **Clustering**: Samples are grouped by `prompt_sha256` (unique paraphrase hash)
2. **Per-Template Means**: Each template's replicates are averaged in log-odds space
3. **Equal Weighting**: Template means are averaged equally (regardless of sample count)
4. **Cluster Bootstrap**: Confidence intervals use cluster-aware resampling:
   - Resample templates (with replacement)
   - Then resample replicates within each template
   - This preserves the hierarchical structure of the data

#### Statistical Properties
- **K×R Sampling**: K paraphrases × R replicates (default: 7×3 = 21 samples)
- **Log-odds Transformation**: All averaging happens in logit space to avoid probability averaging artifacts
- **Bootstrap CI**: 2000 bootstrap iterations for 95% confidence intervals
- **Stability Score**: S = 1/(1 + IQR_logit) where IQR is computed on per-template means

#### Diagnostic Outputs
The system now reports:
- `paraphrase_balance`: Shows counts per template and imbalance ratio
- `imbalance_ratio`: Max/min template counts (ideal = 1.0)
- `template_iqr_logit`: Spread of template means (consistency measure)

### Backwards Compatibility
- Default: `--agg clustered` (correct, unbiased estimator)
- Legacy: `--agg simple` (old behavior for comparison)

## Future Implementation Priorities

When implementing remaining components:

- Focus on the four-lens evaluation architecture
- Implement reliability scoring for non-academic evidence sources
- Build the dual-track system (exploration vs adjudication)
- Create mechanisms to measure and reward information gain rather than raw point changes

Purpose: Build an AI system that measures and moves beliefs away from passive consensus. Heretix exposes a model’s internal prior (“what it already believes”), challenges that prior with evidence and argument, and rewards durable improvements in belief—not verbosity or theater.

This document specifies:
	•	Product goals and architecture (lenses, metrics, market)
	•	Statistical design (how we sample, aggregate, and report)
	•	GPT‑5–specific constraints and how we adapt
	•	CLI behavior and output interpretation
	•	Future‑proofing and invariants

⸻

0) Executive Summary
	•	What: A pipeline that queries a model for a claim’s truth probability under different lenses and reports a robust, reproducible belief score with uncertainty.
	•	Why: Models amplify consensus; Heretix rewards arguments that change a model’s belief in ways that survive rebuttal (durable delta).
	•	How (today): We’ve implemented RPL (Raw Prior Lens) on GPT‑5. Because GPT‑5 lacks deterministic sampling controls, we use K×R sampling, paraphrase clustering, trimmed centers, and cluster bootstrap to estimate a stable prior with CI.
	•	How (market): The Dynamic Conviction Market (DCM) and Episodic Proportional Claims (EPC) pay labor and capital for movement and durability of belief changes, not for wordcount.

⸻

1) Product Goals & Non‑Goals

Goals
	1.	Measure priors: Quantify a model’s belief before retrieval—expose consensus it absorbed during training.
	2.	Reward real updates: Incentives tied to Δ belief (info gain), not verbosity or vibes.
	3.	Auditability: Deterministic statistics given the same data: fixed RNG seeds, prompt hashes, model/version logging.
	4.	Robustness: Insulate measurement from wording artifacts and stochastic decode noise.

Non‑Goals
	•	We do not certify ground truth. We measure model beliefs under lenses and how challengers can move them.
	•	We do not pay for rhetorical performance. Tokens without movement are explicitly discounted.

⸻

2) Lenses (Conceptual API)

We evaluate each claim with distinct lenses (only RPL is implemented now):
	1.	RPL — Raw Prior Lens (implemented)
	•	No retrieval/citations. Temperature controls are unavailable on GPT‑5; treat the model as stochastic and sample repeatedly.
	•	Output: prob_true ∈ [0,1] + structured rationale arrays.
	2.	MEL — Mainstream Evidence Lens (planned)
	•	Retrieval constrained to canonical sources; reproducible citations.
	3.	HEL — Heterodox Evidence Lens (planned)
	•	Retrieval excluding canonical list; primary data, replications, OSINT, well‑documented blogs/code.
	4.	SEL — Sandbox Evidence Lens (planned)
	•	Only challenger‑provided bundle; model must reason from artifacts given.

We publish a vector: p_{\text{RPL}}, p_{\text{MEL}}, p_{\text{HEL}}, p_{\text{SEL}} plus dispersion and source concentration metrics.

⸻

3) Metrics (Cross‑Lens, later phases)
	•	Shock Index (SI) = |p_{\text{RPL}} - p_{\text{HEL}}|
Flags “shocking priors” vs heterodox evidence.
	•	Amplification Gap (AG) = p_{\text{MEL}} - p_{\text{RPL}}
Retrieval pushing toward consensus.
	•	Source Concentration (SC): Herfindahl over MEL citations.
	•	Information Gain (IG): Price updates via KL/Δ‑logit, not raw points.

⸻

4) RPL Implementation (GPT‑5)

4.1 Constraints & adaptation
	•	No temperature/top‑p/penalties on GPT‑5 Responses API.
	•	We therefore:
	•	Run K paraphrases × R replicates ⇒ N = K·R samples.
	•	Cluster samples by prompt hash (the exact instruction+user text), i.e., template clusters.
	•	Aggregate in logit space with robust estimators and cluster bootstrap for CI.

4.2 Prompting & schema
	•	System rules: concise, falsifiable bullets; numeric precision; no citations; JSON‑only.
	•	User content: PARAPHRASES (5 templates) + canonical USER_TEMPLATE.
	•	Schema fields: belief.{prob_true,label}, reasons[], assumptions[], uncertainties[], flags{refused, off_topic}.

Provenance: We log provider_model_id and prompt_sha256 (hash of exact instructions+user text). Paraphrase “clusters” are keyed by this hash.

⸻

5) Statistical Design (and why)

Design objective: estimate the model’s prior belief while neutralizing two nuisances:
	•	Wording sensitivity (paraphrase effects)
	•	Decode stochasticity (intra‑paraphrase variance)

Pipeline
	1.	Sampling
	•	Choose K paraphrase slots from PARAPHRASES (wrap‑around allowed).
	•	For each slot, run R replicates (identical wording, independent samples).
	•	Record: prob_true → convert to logit \ell = \log\frac{p}{1-p}.
	2.	Equal‑by‑Template weighting (cluster means)
	•	Group logits by template cluster (same prompt_sha256).
	•	Compute a per‑cluster mean in logit space.
	•	Reason: Avoid over‑weighting whichever paraphrase got more replicates (fairness).
	3.	Trimmed center (20%)
	•	With 5 templates, drop the min and max cluster means; average the middle 3.
	•	Reason: Robust to a flaky paraphrase (outlier resistance).
	4.	Cluster bootstrap (B=5000)
	•	Resample templates with replacement (outer), then replicates within each chosen template (inner).
	•	Recompute the trimmed center each time.
	•	CI95 = 2.5th–97.5th percentiles of the bootstrapped distribution.
	•	Reason: Uncertainty is dominated by template‑to‑template variation; a simple bootstrap on all samples would underestimate uncertainty.
	5.	Deterministic RNG seed
	•	We compute a 64‑bit seed from run config (claim|model|prompt_version|K|R|B|center|trim|sorted(template_hashes)), or you can override with HERETIX_RPL_SEED.
	•	Guarantee: Given the same inputs, the bootstrap resampling sequence—and thus the CI—is reproducible.
	6.	Stability score
	•	Let M_k be per‑template mean logits.
	•	\text{IQR} = Q_{75}(M) - Q_{25}(M).
	•	\text{stability} = \frac{1}{1+\text{IQR}} \in (0,1].
	•	Rule of thumb: stable if CI width ≤ 0.20 (in probability space). Lower stability means paraphrase sensitivity.

All aggregation is done in logit space because logits add under Bayes updates; averaging probabilities biases results near 0/1.

⸻

6) Anti‑“Illusion of Thinking” Instrumentation

Verbose outputs often don’t improve correctness. We therefore log and penalize “thinking theater”:
	•	Telemetry per sample: output tokens, latency, prompt condition (plain / coax / strict), budget (max tokens, reasoning effort).
	•	Deliberation Elasticity (DE): Δ logit per Δ tokens across budgets.
	•	If DE ≈ 0: more words, same belief → hollow deliberation.
	•	Hollow Deliberation Index (HDI): tokens_out / |Δ logit|.
	•	Very high HDI triggers reward down‑weighting in the market.

⸻

7) Economic Layer (DCM + EPC) — Summary

Actors
	•	Challengers (labor) submit arguments with a stake S on Heretic (score up) or Orthodox (score down/steady).
	•	Stakers (capital) fund the two pools: P_H and P_O.

Immediate mechanics (DCM)
	•	Failure: Challenger loses S. Platform takes op fee F_{op}; remainder Y goes as Resilience Yield to the opposite pool.
	•	Success: Reward \propto impact; quadratic in Δ: M = \Delta^2 / 100.
	•	Gross reward from opposing pool: R_{\text{gross}} = P_{\text{opp}} \cdot (M/100).
	•	Split: Challenger R_{\text{C}} = R_{\text{gross}} \cdot R_{\text{split}}; Stakers on same side R_{\text{S}} = R_{\text{gross}} \cdot (1-R_{\text{split}}).
	•	Platform rake R_{\text{rake}} applies to R_{\text{gross}}.

Durable mechanics (EPC)
	•	During the episode, successful challenges mint Claim Shares via M=\Delta^2/100.
	•	At resolution: durable net change \Delta_E sets Victory Margin M_V = |\Delta_E|/100.
	•	Transfer from loser to winner: T_A = P_{\text{loser}} \cdot M_V.
	•	Post‑rake, split T_A across stakers and challengers (proportional to Claim Shares).
	•	Draw: \Delta_E = 0 → no transfer; shares void. Oscillation without durability earns nothing.

Pool accounting uses shares (LP‑style): yields increase share value; impairments reduce it.

⸻

8) CLI Usage & Output Interpretation

Command

uv run heretix-rpl \
  --claim "tariffs don't cause inflation" \
  --model gpt-5 \
  --k 7 \
  --r 3 \
  --agg clustered

Options
	•	--claim (str): canonical claim text.
	•	--model (str): gpt-5 (default).
	•	--k (int): paraphrase slots (wrap‑around over 5 templates).
	•	--r (int): replicates per slot (GPT‑5 only).
	•	--agg (str): clustered (robust; default) or simple (legacy mean).
	•	OPENAI_API_KEY required; optional HERETIX_RPL_SEED to override deterministic bootstrap seed.

Output fields (excerpt)

{
  "aggregates": {
    "prob_true_rpl": 0.2255,
    "ci95": [0.2148, 0.2366],
    "ci_width": 0.0217,
    "stability_score": 0.9401,
    "is_stable": true
  },
  "aggregation": {
    "method": "equal_by_template_cluster_bootstrap_trimmed",
    "B": 5000,
    "center": "trimmed",
    "trim": 0.2,
    "bootstrap_seed": 137228...,
    "n_templates": 5,
    "counts_by_template": { "<hash>": 6, ... },
    "imbalance_ratio": 2.0,
    "template_iqr_logit": 0.0637
  },
  "paraphrase_results": [
    {
      "raw": { "prob_true": 0.23, ... },
      "meta": {
        "provider_model_id": "gpt-5-2025-08-07",
        "prompt_sha256": "a51f3c...",
        "response_id": "resp_...",
        "created": 1755597340.0
      },
      "paraphrase_idx": 3,
      "replicate_idx": 2
    }
  ],
  "raw_logits": [ ... ]
}

Interpretation
	•	prob_true_rpl: model’s prior belief (RPL) after robust aggregation.
	•	ci95: 95% bootstrap confidence interval (cluster‑aware).
	•	stability_score: 1/(1+\text{IQR}) on template means; near 1.0 is stable across paraphrases.
	•	counts_by_template & imbalance_ratio: how many samples per paraphrase cluster and their imbalance.
	•	prompt_sha256: exact prompt variant identity; paraphrase clusters share hashes.

Heuristics:
	•	Stable if ci_width ≤ 0.20.
	•	If imbalance_ratio > 2, consider increasing K or rebalancing.
	•	For audits, compare runs by prompt_version and provider_model_id.

⸻

9) Files & Responsibilities
	•	heretix_rpl/rpl_prompts.py — system & user templates; PARAPHRASES; PROMPT_VERSION.
	•	heretix_rpl/rpl_schema.py — JSON shape the model must emit.
	•	heretix_rpl/rpl_eval.py — end‑to‑end RPL execution for GPT‑5 (Responses API), aggregation callout, provenance logging.
	•	heretix_rpl/aggregation.py — aggregation strategies:
	•	aggregate_clustered(...) (default): equal‑by‑template weighting, 20% trimmed center, cluster bootstrap, deterministic RNG.
	•	aggregate_simple(...): legacy mean bootstrap (unclustered).
	•	heretix_rpl/seed.py — deterministic seed derivation from run config (or override via HERETIX_RPL_SEED).
	•	cli.py — Typer CLI, arguments, pretty print.

Future modules (planned):
	•	heretix_mel, heretix_hel, heretix_sel (lenses)
	•	telemetry.py (tokens, latency, DE, HDI)
	•	market/ (DCM, EPC accounting)

⸻

10) Feature Detection & Guardrails
	•	Responses API quirks: Not all params are supported everywhere. We feature‑detect:
	•	If reasoning={"effort":"minimal"} errors, retry without.
	•	We embed the schema in instructions (Responses API), no response_format flag.
	•	Formatting fragility: We hard‑require JSON; if parsing fails, we raise with clear error text.
	•	Provider drift: Log provider_model_id and prompt_version. Treat RPL as a measured prior with provenance, not an absolute.
	•	Paraphrase balance: We report cluster counts and imbalance; aggregation already equal‑weights templates to neutralize wrap‑around bias.

⸻

11) Calibration & Quality Checks (roadmap)
	•	Anchor claims: tautologies/contradictions to chart reliability curves.
	•	Reliability diagrams: bin by predicted probability; plot observed correctness (for resolvable claims).
	•	Isotonic/Platt (optional): post‑hoc calibration if needed for market pricing.
	•	Budget Lens: run at {256, 512, 1024} tokens; compute DE and HDI. Publish per‑claim.

⸻

12) Market Policy Knobs (defaults to tune later)
	•	S (min stake) = $20
	•	T (success threshold in Δ points) = 3.0
	•	F_op (op fee on lost stakes) = 25%
	•	R_rake (platform rake on rewards/transfers) = 10%
	•	R_split (Challenger share on success) = 60%
	•	Impact multiplier M = \Delta^2/100 (bounded if needed).

These live in a config file for on‑chain/off‑chain parity when we launch the market.

⸻

13) Invariants (do not break without version bump)
	•	Always aggregate in logit space.
	•	Equal‑by‑template weighting before global center.
	•	Trimmed center (20%) unless T<5.
	•	Cluster bootstrap with deterministic seed (report B and bootstrap_seed).
	•	Log prompt_version and provider_model_id.

⸻

14) Quick FAQ for Maintainers
	•	Why bootstrap? Closed‑form SEs are wrong under clustered heterogeneity. Bootstrap matches structure (templates as clusters).
	•	Why trim 20%? With 5 templates, it drops min & max—protects against a single flaky paraphrase.
	•	Can I set K not multiple of 5? Yes; aggregation equal‑weights templates, so wrap‑around duplicates don’t bias the estimate.
	•	What if JSON fails? The call raises; the runner logs a warning and continues; the aggregator requires ≥3 samples.

⸻

15) Roadmap (immediate)
	•	Add telemetry capture (tokens, latency) and compute DE & HDI.
	•	Add Budget Lens sweeps in RPL.
	•	Implement MEL/HEL/SEL with retrieval constraints + citation concentration.
	•	Wire DCM/EPC payouts to Δ‑logit and durable Δ respectively.
	•	Minimal web UI for vector display and market dashboards.

⸻

Glossary
	•	Logit: \ell = \log\frac{p}{1-p}. Use for averaging and deltas; converts probabilities to an unbounded, additive scale.
	•	Cluster bootstrap: Resample clusters (templates) and replicates within clusters to compute CI.
	•	Paraphrase cluster: All samples with the same prompt_sha256.
	•	RPL: Raw Prior Lens—no retrieval; measures the model’s internal prior.
	•	DE/HDI: Deliberation Elasticity / Hollow Deliberation Index—penalize verbosity without belief movement.

⸻

Contact points in code
	•	Aggregator choice: cli --agg clustered (default).
	•	Seed override: HERETIX_RPL_SEED=12345 for reproducible CI.
	•	Prompts: heretix_rpl/rpl_prompts.py (PROMPT_VERSION controls provenance).
	•	Stats core: heretix_rpl/aggregation.py (look here if you change K/R/B/trim logic).

Truth north: Pay for movement and durability, expose priors and amplifiers, and make every number auditably boring.

This project used uv NOT venv

⸻

Addendum (2025‑08‑21) — Auto‑RPL + Ops Updates

Repository & Change Control
• Package manager: uv (not venv). All examples and scripts assume `uv run ...`.
• Change policy: Do not modify files without explicit user approval. Do not alter the core statistical methodology or frozen sampling policy without a versioned proposal and user sign‑off.

RPL Enhancements (Frozen Policy)
• Paraphrase bank expanded to 16 neutral templates; `PROMPT_VERSION = rpl_g5_v2_2025‑08‑21` for provenance.
• Deterministic balanced sampler with rotation (by sha256 of claim|model|prompt_version) to avoid low‑index favoritism while keeping counts equal.
• Auto‑RPL controller (templates‑first) with sample reuse and decision logging.
• Estimator unchanged: logit aggregation, equal‑by‑template weighting, 20% trimmed center (T≥5), cluster bootstrap CI (B=5000) with deterministic seed.

Auto‑RPL (Adaptive, Templates‑First)
• Frozen stage sequence: 
  1) T=8, K=8, R=2 → 2) T=16, K=16, R=2 → 3) T=16, K=16, R=3.
• Gates (hard): CI width ≤ 0.20; Stability ≥ 0.70 (1/(1+IQR_logit)); Imbalance ≤ 1.50.
• Warn (soft): log a warning if Imbalance > 1.25.
• Behavior: deterministic balanced rotation; reuse samples across stages (add only deltas); emit decision_log and per‑stage snapshots (full RPL JSON) for audit.

CLI Additions (uv)
• auto: `uv run heretix-rpl auto --claim "..." --out runs/rpl_auto.json`
  – Runs the frozen stage plan; stops early on pass; prints stage metrics; writes `controller`, `final`, `stages[]`, `decision_log[]`.
• inspect: `uv run heretix-rpl inspect --run runs/rpl_auto.json`
  – Pretty‑prints per‑template means (p, logit), IQR(logit), stability, CI, counts, imbalance. Accepts plain runs, auto top‑level, or stage snapshots.
• monitor: `uv run heretix-rpl monitor --bench bench/sentinels.json --out runs/monitor/<date>.jsonl [--baseline prior.jsonl]`
  – Weekly sentinel snapshot with fixed K=8, R=2 (for comparability). Streams progress and writes one JSONL row per claim; adds drift flags if baseline supplied.
• summarize: `uv run heretix-rpl summarize --file runs/monitor/<date>.jsonl`
  – Prints row/model/version summary, mean p/CI width/stability, counts of high/low/mid p, drift counts, and top‑3 widest CIs.

Operations (Weekly)
• Baseline: run `monitor` weekly to `runs/monitor/<date>.jsonl`; then `summarize` for a quick health report.
• Audits: use `inspect` on any claim with wide CI or low stability to see per‑template behavior.
• Determinism: set `HERETIX_RPL_SEED` to fix bootstrap sequence for CI reproducibility (does not fix model outputs).

Safety Rails (Reiterated)
• Never change estimator math (logit aggregation, equal‑by‑template, 20% trim, cluster bootstrap with deterministic seed) without a version bump and explicit approval.
• Never change the frozen Auto‑RPL stage sequence or gates without explicit user approval and a documented policy/version update.
• Repository uses uv; do not switch tooling without user approval.
