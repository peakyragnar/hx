# Supervised → RL Bridge Plan

This note captures the minimum viable path from today’s supervised-style forecasting (fixed prompt + deterministic aggregation) to a future reinforcement-learning loop. It mirrors the phased roadmap already in motion but adds the data, experiments, and guardrails needed so each stage unlocks the next.

---

## 1. Lock In High-Quality Supervised Data
- **Capture “fat rows” per run (Phase 3.1)**  
  Include: claim text/ID, mode, provider(s), knob set (K/R/B/T, prompt version), priors/web/combined probabilities + CIs, web weighting factors, doc/domain counts, dispersion metrics, latency, token usage, cost, seeds.  
  _Done when_: every RPL/WEL run writes a self-contained record suitable for training a supervised model.
- **Label outcomes where possible**  
  - For retrospective claims with known truths, attach resolved labels and resolution timestamps.  
  - For market-linked claims, log market price at resolution and realized P&L.
- **Quality gates**  
  - Maintain existing compliance/stability/precision gates; log gate failures so noisy entries can be filtered from training data.

## 2. Build the Supervised Baseline
- **Feature engineering**  
  - Start with prompt/runs metadata (provider, prompt_version, K/R/T, web stats, market price).  
  - Add textual embeddings (claim text, evidence snippets) when ready; store references not just raw text.
- **Modeling**  
  - Begin with interpretable regressors (logistic/GBM) predicting resolved truth or market outcome.  
  - Benchmark against current combined probability; ensure no supervised model degrades calibration.
- **Monitoring**  
  - Log predictions side-by-side with production combined probabilities for offline comparison.  
  - Track calibration curves, Brier score, log loss, and monotonicity with market odds.

## 3. Stand Up RL-Ready Infrastructure
- **State logging**  
  - Extend per-run records with `state_json` containing all signals an RL policy would observe (prior, web stats, cache hints, market price, provider availability).  
  - Add `action` (e.g., extra samples, provider choice, weighting tweak) even if in Phase 1 the action is “none”.  
  - Leave `reward` null for now; ensure schema supports future fill-in.
- **Simulation environment**  
  - Define a deterministic replay harness that can simulate actions using cached samples/web evidence.  
  - Ensure seeding matches production so offline RL reproduces the same stochastic pathways.
- **Offline evaluation hooks**  
  - Store counterfactual metrics (e.g., what combined probability would have been if weight changed) to evaluate candidate policies before deployment.

## 4. Incremental Policy Learning
- **Phase 0: Policy as supervised regression**  
  - Use the supervised model to recommend weights/concurrency settings; run shadow mode to compare against heuristics.
- **Phase 1: Rule-based → contextual bandit**  
  - Begin with contextual bandit or policy gradient on limited actions (e.g., decide whether to escalate K, or which provider to query).  
  - Reward = improved calibration / profitability minus cost.  
  - Roll out in controlled slices (e.g., one claim cohort) with fallback to deterministic policy.
- **Phase 2: Full RL loop**  
  - Expand action space (provider mix, sampling plan, web query depth).  
  - Use logged environments for offline training; only deploy once off-policy evaluation passes thresholds.

## 5. Guardrails & Governance
- **Versioned policies** with rollback hooks; log policy version alongside each run.  
- **Safety monitors** that ensure gates (precision, stability, compliance) remain satisfied; auto-disable learning policy on breach.  
- **Audit trails** tying supervised predictions and RL actions back to stored evidence (docs, artifacts, seeds) so outcomes are explainable.

---

### Next Concrete Tasks
1. Merge Phase 3.1 “fat row” logging and start populating the supervised dataset.  
2. Add empty RL trace table (state/action/reward/policy_version) so every run already records its context.  
3. Draft the deterministic replay harness spec—define how cached samples/web evidence will be reused for offline experiments.  
4. Kick off a calibration analysis comparing current combined probability vs. market prices/resolved labels to establish the baseline your supervised model must beat.
