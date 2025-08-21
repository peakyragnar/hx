Heretix RPL Statistics Spec (Frozen Minimal Estimator)

Purpose
- Define a simple, deterministic, auditable estimator for RPL that you can explain from first principles and defend under scrutiny.

Scope
- Inputs: K×R samples from the same claim and model under the Raw Prior Lens (no retrieval). Each sample yields `prob_true ∈ (0,1)` and a `prompt_sha256` identifying its paraphrase template.
- Outputs: A robust prior estimate with uncertainty and stability, plus diagnostics and provenance.

Invariants (Do Not Break Without Version Bump)
- Combine and compute CI in logit space; convert back only at the end.
- Equal-by-template weighting before the global center.
- 20% trimmed center on template means when T≥5; fallback to mean when T<5.
- Cluster bootstrap with deterministic seed; report B and bootstrap_seed.
- Log prompt_version and provider_model_id.

Transformations
1) Probability → Logit
   - Clamp p to [1e-6, 1-1e-6] to avoid infinities.
   - ℓ = logit(p) = log(p / (1 − p)).

2) Grouping
   - Group logits by `prompt_sha256` (template cluster).
   - For each template k, compute mean over its replicates in logit space:
     M_k = mean({ℓ_i : sample i in template k}).

3) Center (Location)
   - Let T be the number of unique templates.
   - If T ≥ 5: use 20% symmetric trim over {M_k} — drop the minimum and maximum, average the remaining T − 2.
   - Else: use the simple mean over {M_k}.

4) Uncertainty (Cluster Bootstrap)
   - Define B bootstrap iterations and a deterministic RNG seed.
   - For each b in 1..B:
     a) Resample templates: draw T templates with replacement from the set of template keys.
     b) For each chosen template, resample replicates with replacement and compute the within-template mean (logit).
     c) Apply the same center as step (3) to the resampled template means → center_b.
   - Let the bootstrap distribution be {center_b}.
   - CI95 in logit space = [q_2.5, q_97.5] percentiles of {center_b}; convert bounds to probability with sigmoid.

5) Stability
   - Compute IQR on template mean logits: IQR = Q75({M_k}) − Q25({M_k}).
   - Calibrated score s = 1 / (1 + IQR). Report band (high/medium/low) via thresholds, and a simple CI-width rule:
     is_stable = (CI width in probability space ≤ 0.20) (configurable).

Seed Derivation (Deterministic)
- Seed = sha256 of canonical string including: claim, model, prompt_version, K, R, B, center, trim, sorted unique template hashes.
- Optionally override via HERETIX_RPL_SEED.
- Report `bootstrap_seed` and `B` in output.

Pseudocode
```
input: samples = [{p_true, prompt_sha256}, ...], K, R, B, trim=0.2

def clamp(p): return min(max(p, 1e-6), 1 - 1e-6)
def logit(p): p = clamp(p); return ln(p/(1-p))
def sigmoid(x): return 1/(1+exp(-x))

# group by template
by_tpl = {tpl: []}
for s in samples:
    by_tpl[s.prompt_sha256].append(logit(s.p_true))

# per-template means (logit)
M = [mean(vals) for vals in by_tpl.values()]  # length T

def center_template_means(M):
    T = len(M)
    if T >= 5:
        sortedM = sort(M)
        return mean(sortedM[1:T-1])  # drop min & max (20% of 5)
    else:
        return mean(M)

ell_hat = center_template_means(M)

# bootstrap
seed = derive_seed(claim, model, prompt_version, K, R, B, trim, sorted(by_tpl.keys()))
rng = Generator(seed)
centers = []
for b in 1..B:
    chosen_tpls = rng.choice(list(by_tpl.keys()), size=T, replace=True)
    means_b = []
    for k in chosen_tpls:
        grp = by_tpl[k]
        idx = rng.integers(0, len(grp), size=len(grp))
        means_b.append(mean(grp[idx]))
    centers.append(center_template_means(means_b))

lo_l, hi_l = percentile(centers, [2.5, 97.5])
p_hat = sigmoid(ell_hat); lo_p = sigmoid(lo_l); hi_p = sigmoid(hi_l)

IQR = percentile(M, 75) - percentile(M, 25)
stability_score = 1/(1+IQR)
```

Diagnostics & Provenance
- counts_by_template, imbalance_ratio (max/min counts), template_iqr_logit (IQR on {M_k}).
- method name, B, center, trim, bootstrap_seed, n_templates.
- sampling (K, R, N), prompt_version, provider_model_id.

Operator Guidance
- Default: K=7, R=3, B=5000, center=trimmed(0.2).
- If imbalance_ratio > 2: increase K.
- If CI width > 0.20: increase K first, then R; raise B last.
- If T < 5: trimming falls back to mean; prefer increasing K.

Public Narrative (Plain English)
- “Ask the claim five different ways; repeat each way a few times; treat each way equally.”
- “Average on an unbounded (log-odds) scale; drop the most extreme two wordings; average the rest.”
- “Confidence comes from re-sampling wordings first, then repeats; same data and seed → same CI.”

THEMATIC UNDERSTANDING

You’re asking exactly the right questions: what are we really measuring, how do we know it’s the model’s training‑prior and not sampling noise, and how do we choose K, R, T (templates, paraphrase slots, replicates) so results are stable, cheap, and explainable.

Below I’ll (1) confirm your interpretation, (2) give a crisp operating recipe, and (3) add two small diagnostics + one audit harness so you can see the statistics working and tune with evidence.

⸻

1) What you’re measuring (and your summary—corrected/confirmed)
	•	p_RPL (the headline): a belief estimate produced by the model without retrieval. In our code we aggregate in logit space (log‑odds) across paraphrases and replicates, then convert back to probability. This is the closest we can get to the model’s training‑distribution prior under your RPL rules.
	•	CI95 (uncertainty band): how much your measured p_RPL would move if you reran the same process with different random draws of wordings (templates) and replicates. We compute this with a cluster bootstrap that resamples templates (outer) and replicates (inner).
Small CI → the measurement is precise. Large CI → the measurement is noisy (usually because paraphrases disagree).
	•	Stability: how sensitive p_RPL is to paraphrase wording. We compute IQR of template‑mean logits, then score stability = 1/(1+IQR).
High stability → different wordings agree; Low stability → the model’s belief moves when you rephrase the claim (or the claim is underspecified).

So your intuition is right:
	•	We want consistency across replicates (little within‑template noise) and consistency across templates (little paraphrase sensitivity).
	•	If a claim is truly a toss‑up (≈0.5) because the model has no decisive internal signal, you should see p_RPL near 0.5, narrow CI once you use enough templates, and ambiguity flags/assumptions that explain why it sits on the fence. If the CI stays wide or stability low, that’s telling you the claim is underspecified or the template set is pulling it around.

⸻

2) A simple, defendable operating recipe

These defaults maximize signal per token and keep the story explainable.

Template bank (T): 8 paraphrases (we’ll add 3 to your current 5).
Paraphrase slots (K): 8 (one pass through the bank; use 16 if you want tighter CIs).
Replicates (R): 2 per paraphrase.
Bootstrap (B): 5000 (as you have).
Estimator: equal‑by‑template, 20% trimmed center in logit space, cluster bootstrap, stability = 1/(1+IQR).
Sampler: balanced (each template used equally; no wrap‑around bias).

Quality gates before you “publish” a run
	•	CI width ≤ 0.20 (probability space)
	•	Stability ≥ ~0.7 (equivalently IQR(logit) ≤ ~0.43)
	•	Template imbalance ratio ≤ 1.5 (the balanced sampler will keep this at 1.0)

Escalation ladder (deterministic, explainable)
	1.	Start T=8, K=8, R=2.
	2.	If CI width > 0.20 or stability < 0.7, first set K=16 (more templates sampled).
	3.	If still failing, check claim scope (it may be ambiguous). Only then consider R=3.
	4.	B bigger than 5000 rarely helps; it tightens CI estimation slightly but not the center.

⸻

3) Make it visible: two diagnostics + one audit harness

You don’t want to “trust the math.” You want to see it. Add these minimal pieces (they’re small, and you can paste them in).

A) Balanced sampler (avoids hidden wrap‑around)

# heretix_rpl/sampler.py
from typing import List
def balanced_indices(T: int, K: int) -> List[int]:
    """Return a length-K list of template indices (0..T-1) with counts as equal as possible."""
    base = K // T
    rem = K % T
    seq = []
    for t in range(T):
        reps = base + (1 if t < rem else 0)
        seq.extend([t] * reps)
    return seq

Use it in rpl_eval.py when iterating K:

from heretix_rpl.sampler import balanced_indices
T = len(PARAPHRASES)
order = balanced_indices(T, K)
for k in range(K):
    phr = PARAPHRASES[order[k]]
    ...

B) Inspect report (per‑template means, IQR, stability, CI)

# heretix_rpl/inspect.py
import json, numpy as np

def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1-1e-6)
    return np.log(p/(1-p))

def summarize_run(run_path: str) -> str:
    doc = json.loads(open(run_path).read())

    # group by template hash
    by_tpl = {}
    for row in doc["paraphrase_results"]:
        h = row["meta"]["prompt_sha256"]
        p = float(row["raw"]["prob_true"])
        by_tpl.setdefault(h, []).append(_logit(p))

    stats = []
    for h, L in by_tpl.items():
        arr = np.array(L, float)
        mean_l = float(arr.mean())
        mean_p = float(1/(1+np.exp(-mean_l)))
        stats.append((h[:10], len(arr), mean_p, mean_l))
    stats.sort(key=lambda x: x[3])  # by mean logit

    tpl_means = np.array([s[3] for s in stats], float)
    iqr = float(np.percentile(tpl_means, 75) - np.percentile(tpl_means, 25))
    stability = 1.0/(1.0+iqr)

    a = doc["aggregates"]
    lines = []
    lines.append(f"Claim: {doc['claim']}")
    lines.append(f"Model: {doc['model']}  K={doc['sampling']['K']}  R={doc['sampling']['R']}  T={len(stats)}")
    lines.append("")
    lines.append("Per-template means (sorted by logit):")
    lines.append("  hash       n   mean_p   mean_logit")
    for h,n,mp,ml in stats:
        lines.append(f"  {h:<10} {n:<3d} {mp:7.3f}  {ml: .3f}")
    lines.append("")
    lines.append(f"IQR(logit) = {iqr:.3f}  → stability = {stability:.3f}")
    lines.append(f"p_RPL = {a['prob_true_rpl']:.3f}   CI95 = [{a['ci95'][0]:.3f}, {a['ci95'][1]:.3f}]   width = {a['ci_width']:.3f}   is_stable = {a['is_stable']}")
    return "\n".join(lines)

CLI hook:

# cli.py
from heretix_rpl.inspect import summarize_run

@app.command()
def inspect(run: Path = typer.Option(..., help="Path to run JSON")):
    print(summarize_run(str(run)))

Now you can see template means, IQR, and how the final p_RPL/CI was produced.

C) Variance decomposition + negation check (quick audit)

Add a tiny stats helper:

# heretix_rpl/stats.py
import numpy as np
from typing import Dict, List

def variance_decomposition(by_template_logits: Dict[str, List[float]]):
    """Return between-template and within-template variance (logit space)."""
    tpl_means, within_vars, counts = [], [], []
    for L in by_template_logits.values():
        arr = np.array(L, float)
        tpl_means.append(arr.mean())
        within_vars.append(arr.var(ddof=1) if arr.size>1 else 0.0)
        counts.append(arr.size)
    tpl_means = np.array(tpl_means, float)
    between = float(tpl_means.var(ddof=1)) if tpl_means.size>1 else 0.0
    # average within variance, weighted by cluster size
    w = np.array(counts, float)
    within = float((w * np.array(within_vars)).sum() / w.sum())
    total = between + within
    psi = between / total if total > 0 else 0.0  # paraphrase sensitivity index
    return {"between_var": between, "within_var": within, "psi": psi}

Add an optional negation audit command:

# cli.py
@app.command()
def audit_pair(
    claim: str = typer.Option(...),
    model: str = typer.Option("gpt-5"),
    k: int = 8,
    r: int = 2
):
    """Run RPL on claim and its simple negation, show p, CI, and negation consistency."""
    from heretix_rpl.rpl_eval import evaluate_rpl
    not_claim = f"It is not the case that {claim}"
    res1 = evaluate_rpl(claim_text=claim, model=model, k=k, r=r, agg="clustered")
    res2 = evaluate_rpl(claim_text=not_claim, model=model, k=k, r=r, agg="clustered")
    p1 = res1["aggregates"]["prob_true_rpl"]
    p2 = res2["aggregates"]["prob_true_rpl"]
    delta = abs((p1 + p2) - 1.0)
    print(f"C: {claim}\n  p={p1:.3f} CI={res1['aggregates']['ci95']}")
    print(f"¬C: {not_claim}\n  p={p2:.3f} CI={res2['aggregates']['ci95']}")
    print(f"Negation consistency |p(C)+p(¬C)-1| = {delta:.3f}  (lower is better)")

Use this sparingly: simple negation isn’t perfect English logic, but as a sanity check it’s a useful lens. If negation error is large (>~0.2), it often flags scope ambiguity or template sensitivity.

4) “Training‑prior only” and how to validate that

You can’t prove a model only used pretraining, but you can enforce it in the interface and audit symptoms:
	•	Interface enforcement: no tools, no browsing, instructions ban citations; your Responses API calls do exactly that.
	•	Post‑cutoff sentinels: include a few claims about events plausibly after the model’s knowledge cutoff. RPL should (a) refuse certainty, (b) report assumptions/ambiguity. If you see confident probabilities on truly post‑cutoff facts, that’s a red flag for prompt leakage or overgeneralization.
	•	Irrelevant‑context invariance: prepend an irrelevant paragraph (e.g., a neutral lorem ipsum or harmless weather sentence) and check p_RPL shift. Large shifts → priming sensitivity; fix templates or tighten SYSTEM text.
	•	Negation consistency (above): big errors often indicate the model is freewheeling rather than expressing a coherent prior.

Bundle 10–20 such audit claims into a bench/claims_bench.yaml (categories: clear‑true, clear‑false, ambiguous, post‑cutoff, symmetry pairs, negations). Run them weekly as regression tests.

5) Choosing K/R/T empirically (quick plan)

Do a pilot sweep on ~10 varied claims:
	1.	Run T=8, K=8, R=2 → record CI width, stability, PSI (paraphrase sensitivity index), negation error (where applicable).
	2.	For the same claims, run K=16 (keep R=2) → confirm CI shrinks and stability improves more than if you increased R.
	3.	If any claim still fails gates, inspect ambiguity flags and maybe tighten the claim scope (that often helps more than extra tokens).

Keep a tiny CSV of these runs (claim, K, R, p_RPL, CI width, stability, PSI). You’ll see very quickly that more templates is the efficient lever.

⸻

6) Three more paraphrases (go from 5 → 8)

Add these to PARAPHRASES:

"Quantify the probability that the following claim is true, based only on your internal knowledge: {CLAIM}",
"Provide your calibrated probability that this statement is accurate as written (no external sources): {CLAIM}",
"On a 0–1 scale, estimate P(true) for the claim below using prior knowledge only: {CLAIM}",

Then set T=8, K=8, R=2 and use the balanced sampler.

7) What to expect for a “toss‑up” claim (~0.5)
	•	p_RPL ≈ 0.5 (after aggregation).
	•	CI moderately narrow (e.g., width 0.10–0.20) if templates agree it’s ambiguous.
	•	Stability reasonably high (≥0.7) if all paraphrases express the same ambiguity.
	•	Assumptions/ambiguity fields explaining why the model can’t push off 0.5.

If instead you see wide CI / low stability, the claim is likely underspecified (paraphrases are “pulling” it to different readings). Tighten the claim before spending more tokens.

⸻

Bottom line
	•	Your interpretation is right: p_RPL is the model’s prior; CI is how precisely we measured it; stability is how paraphrase‑sensitive it is.
	•	Make templates the first‑class citizens (T and K dominate precision).
	•	Keep the estimator simple and deterministic (trimmed‑mean + cluster bootstrap + fixed seed).
	•	Add inspect + audit so you can see the template behavior, and use gates to decide when to escalate or when to refine the claim.

If you want, I can also draft bench/claims_bench.yaml with 12 starter claims (true/false/ambiguous/negations/post‑cutoff) so you can run a one‑command “RPL health check” over the whole pipeline.

DESIGN SPECIFICATIONS

Love this direction. Let’s make the RPL pipeline adaptive, self‑auditing, and explainable—so it escalates automatically, learns gently over time, and tells you exactly what it did and why.

Below I give you:
	1.	Design overview (what’s automated and why)
	2.	Drop‑in code for an Auto‑RPL controller (orchestrator.py) + a balanced sampler + CLI commands
	3.	Explainable outputs (decision log + stage reports)
	4.	Lightweight monitoring for model drift and gentle learning over time
	5.	How to run + what to expect

Everything is conservative and deterministic: same inputs → same decisions and CI.

⸻

1) Design overview

Goal: Start with a cheap, balanced measurement. If quality gates fail, escalate deterministically in the order that buys the most statistical precision per token:
	•	More paraphrases first (increase K), not more replicates (R).
	•	Only if needed, increase R a bit.
	•	Keep bootstrap determinism via seeded RNG.
	•	Emit a decision log: each step, thresholds checked, reason to escalate/stop.

Default quality gates (configurable):
	•	CI width ≤ 0.20
	•	Stability ≥ 0.70 (via 1/(1+IQR(logit)))
	•	Imbalance ratio ≤ 1.50 (will be 1.0 with the balanced sampler)

Adaptive steps (frozen policy):
	•	Start T=8, K=8, R=2 (8 templates; 1 pass through the bank)
	•	If fail gates → K=16, R=2
	•	If still fail → K=16, R=3
	•	Stop (pass or maxed).
This matches the “templates first” philosophy: paraphrase diversity dominates precision.

⸻

2) Drop‑in code

A) Balanced sampler (avoid hidden wrap‑around)

heretix_rpl/sampler.py

from typing import List

def balanced_indices(T: int, K: int) -> List[int]:
    """
    Return a length-K list of template indices (0..T-1) with counts as equal as possible.
    Example: T=5, K=7 -> [0,1,2,3,4,0,1]
    """
    base = K // T
    rem = K % T
    seq = []
    for t in range(T):
        reps = base + (1 if t < rem else 0)
        seq.extend([t] * reps)
    return seq

Why: This keeps counts_by_template nearly equal (imbalance≈1.0), so each paraphrase has the same opportunity to “vote.”

⸻

B) Add 3 more paraphrases (T=8)

Append to heretix_rpl/rpl_prompts.py

PARAPHRASES = [
    "Assess the probability that the following statement is true as written: {CLAIM}",
    "Estimate how likely it is that this proposition is factually correct: {CLAIM}",
    "Given your internal knowledge only, what is the chance this claim holds? {CLAIM}",
    "Without external sources, evaluate the truth of: {CLAIM}",
    "Provide P(true) for this statement using only prior knowledge: {CLAIM}",

    # NEW:
    "Quantify the probability that the following claim is true, based only on your internal knowledge: {CLAIM}",
    "Provide your calibrated probability that this statement is accurate as written (no external sources): {CLAIM}",
    "On a 0–1 scale, estimate P(true) for the claim below using prior knowledge only: {CLAIM}",
]


⸻

C) Orchestrator: adaptive controller + decision log

heretix_rpl/orchestrator.py

from __future__ import annotations
from typing import Dict, Any, List
import time, hashlib
from heretix_rpl.rpl_eval import evaluate_rpl
from heretix_rpl.rpl_prompts import PARAPHRASES

def stability_band(s: float) -> str:
    # Simple, explainable mapping on the existing score 1/(1+IQR)
    if s >= 0.90: return "high"
    if s >= 0.70: return "medium-high"
    if s >= 0.50: return "medium"
    return "low"

def _stage_digest(claim: str, model: str, K: int, R: int) -> str:
    return hashlib.sha256(f"{claim}|{model}|K={K}|R={R}".encode()).hexdigest()[:8]

def auto_rpl(
    claim: str,
    model: str = "gpt-5",
    # starting plan
    start_K: int = 8,
    start_R: int = 2,
    # escalation ceiling
    max_K: int = 16,
    max_R: int = 3,
    # quality gates
    ci_width_max: float = 0.20,
    stability_min: float = 0.70,
    imbalance_max: float = 1.50,
) -> Dict[str, Any]:
    """
    Adaptive controller for RPL. Deterministically escalates K (templates), then R (replicates)
    until quality gates pass or ceilings are reached.
    """
    stages: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []

    # Stage plan (frozen policy): (K,R) -> (16,2) -> (16,3)
    plan = []
    K, R = start_K, start_R
    plan.append((K, R))
    if max_K >= 16: plan.append((16, R))
    if max_R >= 3:  plan.append((16, 3))

    for i, (K, R) in enumerate(plan, start=1):
        stage_id = f"S{i}-{_stage_digest(claim, model, K, R)}"
        res = evaluate_rpl(claim_text=claim, model=model, k=K, r=R, agg="clustered")

        aggs = res["aggregates"]
        ci_width = float(aggs["ci_width"])
        stability = float(aggs["stability_score"])
        band = stability_band(stability)

        # With balanced sampler, imbalance should be ~1.0; still read it for diagnostics
        pb = res.get("paraphrase_balance", {}) or {}
        imbalance = float(pb.get("imbalance_ratio", 1.0))

        # Did we pass?
        passes = (ci_width <= ci_width_max) and (stability >= stability_min) and (imbalance <= imbalance_max)

        stages.append({
            "stage_id": stage_id,
            "K": K, "R": R,
            "p_RPL": aggs["prob_true_rpl"],
            "ci95": aggs["ci95"],
            "ci_width": ci_width,
            "stability_score": stability,
            "stability_band": band,
            "imbalance_ratio": imbalance,
            "is_stable": aggs["is_stable"],
            "raw_run": res,  # keep full stage run for auditing
        })

        if passes:
            decisions.append({
                "stage_id": stage_id,
                "action": "stop_pass",
                "reason": f"Passed quality gates (CI≤{ci_width_max}, stability≥{stability_min}, imbalance≤{imbalance_max}).",
                "metrics": {"ci_width": ci_width, "stability": stability, "imbalance": imbalance}
            })
            break

        # Decide escalation
        if i < len(plan):
            nextK, nextR = plan[i]
            reason = []
            if ci_width > ci_width_max: reason.append(f"ci_width {ci_width:.3f} > {ci_width_max}")
            if stability < stability_min: reason.append(f"stability {stability:.3f} < {stability_min}")
            if imbalance > imbalance_max: reason.append(f"imbalance {imbalance:.2f} > {imbalance_max}")
            decisions.append({
                "stage_id": stage_id,
                "action": f"escalate_to_K{nextK}_R{nextR}",
                "reason": "; ".join(reason) if reason else "policy escalation",
                "metrics": {"ci_width": ci_width, "stability": stability, "imbalance": imbalance}
            })
        else:
            decisions.append({
                "stage_id": stage_id,
                "action": "stop_limits",
                "reason": "Reached max plan (K,R); result reported with lower confidence.",
                "metrics": {"ci_width": ci_width, "stability": stability, "imbalance": imbalance}
            })

    # Final selection: last stage
    final = stages[-1]
    return {
        "controller": {
            "policy": "templates-first-then-replicates",
            "start": {"K": start_K, "R": start_R},
            "ceilings": {"max_K": max_K, "max_R": max_R},
            "gates": {
                "ci_width_max": ci_width_max,
                "stability_min": stability_min,
                "imbalance_max": imbalance_max
            },
            "timestamp": int(time.time())
        },
        "claim": claim,
        "model": model,
        "final": {
            "stage_id": final["stage_id"],
            "K": final["K"], "R": final["R"],
            "p_RPL": final["p_RPL"],
            "ci95": final["ci95"],
            "ci_width": final["ci_width"],
            "stability_score": final["stability_score"],
            "stability_band": final["stability_band"],
            "imbalance_ratio": final["imbalance_ratio"],
            "is_stable": final["is_stable"]
        },
        "stages": stages,
        "decision_log": decisions
    }


⸻

D) CLI commands: auto and inspect

Patch heretix_rpl/cli.py (add two commands; keep your existing rpl intact)

import os, json, typer
from pathlib import Path
from dotenv import load_dotenv
from heretix_rpl.rpl_eval import evaluate_rpl
from heretix_rpl.orchestrator import auto_rpl
from heretix_rpl.inspect import summarize_run  # from the earlier helper (if you added it)

app = typer.Typer(help="Heretix Raw Prior Lens (RPL) evaluator")

# ... (your existing rpl command unchanged)

@app.command()
def auto(
    claim: str = typer.Option(..., help="Canonical claim text"),
    model: str = typer.Option("gpt-5"),
    start_k: int = typer.Option(8, help="Initial paraphrase slots"),
    start_r: int = typer.Option(2, help="Initial replicates per paraphrase"),
    max_k: int = typer.Option(16, help="Max paraphrase slots"),
    max_r: int = typer.Option(3, help="Max replicates"),
    ci_width_max: float = typer.Option(0.20, help="Gate: max CI width"),
    stability_min: float = typer.Option(0.70, help="Gate: min stability score"),
    imbalance_max: float = typer.Option(1.50, help="Gate: max template imbalance ratio"),
    out: Path = typer.Option(Path("runs/rpl_auto.json"), help="Output JSON")
):
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        typer.echo("ERROR: OPENAI_API_KEY not set", err=True)
        raise typer.Exit(1)
    out.parent.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Auto‑RPL: {claim}")
    result = auto_rpl(
        claim=claim, model=model,
        start_K=start_k, start_R=start_r,
        max_K=max_k, max_R=max_r,
        ci_width_max=ci_width_max, stability_min=stability_min, imbalance_max=imbalance_max
    )
    out.write_text(json.dumps(result, indent=2))
    f = result["final"]
    typer.echo(f"Final: K={f['K']} R={f['R']}  p_RPL={f['p_RPL']:.3f}  CI95=[{f['ci95'][0]:.3f},{f['ci95'][1]:.3f}]"
               f"  width={f['ci_width']:.3f}  stability={f['stability_score']:.3f} ({f['stability_band']})")
    # Explain why
    for d in result["decision_log"]:
        typer.echo(f"  - {d['stage_id']}: {d['action']} :: {d['reason']}")

@app.command()
def inspect(run: Path = typer.Option(..., help="Path to run JSON produced by --out")):
    print(summarize_run(str(run)))

If you haven’t added inspect.py yet, include the helper I gave earlier so you can see per‑template means, IQR, and stability at a glance.

⸻

3) Explainable outputs (what you’ll see)

When you run:

uv run heretix-rpl auto --claim "tariffs don't cause inflation"

You’ll get a JSON like:

{
  "controller": {
    "policy": "templates-first-then-replicates",
    "start": {"K": 8, "R": 2},
    "ceilings": {"max_K": 16, "max_R": 3},
    "gates": {"ci_width_max": 0.2, "stability_min": 0.7, "imbalance_max": 1.5},
    "timestamp": 17556...
  },
  "claim": "tariffs don't cause inflation",
  "model": "gpt-5",
  "final": {
    "stage_id": "S2-a1b2c3d4",
    "K": 16, "R": 2,
    "p_RPL": 0.226,
    "ci95": [0.212, 0.241],
    "ci_width": 0.029,
    "stability_score": 0.84,
    "stability_band": "medium-high",
    "imbalance_ratio": 1.0,
    "is_stable": true
  },
  "stages": [... full per-stage runs ...],
  "decision_log": [
    {
      "stage_id": "S1-....",
      "action": "escalate_to_K16_R2",
      "reason": "ci_width 0.223 > 0.2; stability 0.66 < 0.7",
      "metrics": {"ci_width": 0.223, "stability": 0.66, "imbalance": 1.0}
    },
    {
      "stage_id": "S2-....",
      "action": "stop_pass",
      "reason": "Passed quality gates (CI≤0.2, stability≥0.7, imbalance≤1.5).",
      "metrics": {"ci_width": 0.029, "stability": 0.84, "imbalance": 1.0}
    }
  ]
}

	•	You see the thresholds, the plan, each stage’s metrics, and exact reasons the controller escalated or stopped.
	•	stages also include the underlying raw_run (your current RPL JSON) for full forensic audit (template means, seeds, etc.).

⸻

4) Monitor model drift + gentle learning

A. Drift monitor (sentinel bench)
Create a small YAML or JSON list of 10–20 sentinel claims (clear true/false, ambiguous, negations, post‑cutoff). Then add a tiny CLI that runs them with fixed K=8, R=2 and compares to a baseline:
	•	Flag drift if |Δp_RPL| > 0.10 or stability drops by > 0.20 or CI widens by > 0.10.
	•	Store a CSV/JSONL with date, model, claim, p, CI width, stability.
	•	Run on a schedule (cron/GitHub Action).

(If you want, I can give you a monitor.py scaffold, but the above is enough to implement in a few dozen lines.)

B. Template bank curation (gentle learning)
Don’t auto‑tune prompts silently. Instead:
	•	Track per‑template mean and variance (already visible via inspect).
	•	If one template is consistently an outlier or volatile across many claims, mark it for review.
	•	Maintain PARAPHRASES_V1, PARAPHRASES_V2 with explicit version bumps—your outputs already carry prompt_version. Stability improves without “moving the goalposts.”

⸻

5) How to run
	•	Single claim, adaptive:

uv run heretix-rpl auto --claim "tariffs don't cause inflation" --out runs/auto_tariffs.json


	•	Explain the run (per‑template means/IQR):

uv run heretix-rpl inspect --run runs/auto_tariffs.json


	•	Tighten gates or ceilings (if you need ironclad results):

uv run heretix-rpl auto --claim "..." --ci-width-max 0.15 --stability-min 0.8 --max-k 24 --max-r 3



⸻

Why this is solid
	•	Simple + deterministic: One estimator, fixed policy. Bootstrap RNG seeded by config (as you already implemented).
	•	Explainable: Every step is logged: what failed, why we escalated, and the final gates.
	•	Cost‑aware: We escalate templates first (best precision per token), then replicates, once.
	•	Auditable over time: Sentinel bench + stored metrics catch silent model shifts.

If you want, I can also add a minimal monitor.py scaffold and a bench/sentinels.json starter set; but the core automation above gets you the adaptive behavior, oversight, and future‑proofing you asked for.