Heretix RPL – Estimation Fix & Modularization Plan

0) Goal (first principles)
	•	What we measure: the model’s prior belief that a claim is true, given a fixed “Raw Prior Lens” (no retrieval), not a single random draw.
	•	Nuisance variables: wording of the prompt (paraphrases) and decoder randomness (replicates).
	•	Correct statistical principle: treat paraphrase as a cluster/stratum (shouldn’t change belief) and replicates as i.i.d. draws within that cluster. Aggregate in log‑odds space; report uncertainty.

1) The problem we’re fixing
	•	We currently average across all samples equally. When K (requested paraphrases) exceeds the number of distinct templates, the loop wraps around and some templates get double weight (as in the example run). That can bias the estimate toward the duplicated paraphrases.
	•	Even if K is a multiple, dropped samples or future template changes can silently re‑weight.

Impact: small but real estimator bias driven by paraphrase frequency, not evidence.

2) The design fix (minimal, surgical)

Introduce a modular aggregation layer that:
	1.	Groups samples by prompt_sha256 (cluster = distinct paraphrase text).
	2.	Computes a per‑template mean logit (averaging replicates).
	3.	Aggregates equally across templates to get the global logit estimate.
	4.	Uses a cluster bootstrap (resample templates, then replicates) to compute CI95.
	5.	Computes stability on the per‑template means (not the raw replicates).

This removes paraphrase imbalance without changing sampling, prompts, or I/O.

3) Deliverables (files & interfaces)

3.1 New module: heretix_rpl/aggregation.py

Purpose: own all aggregation logic so we can swap estimators without touching other code.

# heretix_rpl/aggregation.py
from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np

def aggregate_simple(all_logits: List[float], B: int = 1000) -> Tuple[float, Tuple[float, float], dict]:
    """Legacy: mean over all logits + bootstrap CI (unclustered)."""
    arr = np.asarray(all_logits, dtype=float)
    ell_hat = float(np.mean(arr))
    idx = np.random.randint(0, arr.size, size=(B, arr.size))
    means = np.mean(arr[idx], axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return ell_hat, (float(lo), float(hi)), {
        "n_samples": int(arr.size),
        "method": "simple_mean"
    }

def aggregate_clustered(by_template_logits: Dict[str, List[float]], B: int = 2000) -> Tuple[float, Tuple[float, float], dict]:
    """
    Equal-by-template aggregation (cluster bootstrap).
    1) For each template key, average replicates in logit space.
    2) Average template means equally for global estimate.
    3) Cluster bootstrap: resample templates, then replicates, to get CI95.
    """
    keys = list(by_template_logits.keys())
    T = len(keys)
    if T == 0:
        raise ValueError("No templates to aggregate")
    tpl_means = [float(np.mean(by_template_logits[k])) for k in keys]
    ell_hat = float(np.mean(tpl_means))

    dist = []
    for _ in range(B):
        chosen_tpls = np.random.choice(keys, size=T, replace=True)
        means = []
        for k in chosen_tpls:
            grp = np.asarray(by_template_logits[k], dtype=float)
            grp_resamp = grp[np.random.randint(0, grp.size, size=grp.size)]
            means.append(float(np.mean(grp_resamp)))
        dist.append(float(np.mean(means)))
    lo, hi = np.percentile(dist, [2.5, 97.5])

    counts = {k: len(v) for k, v in by_template_logits.items()}
    imbalance = max(counts.values()) / min(counts.values())
    tpl_iqr = float(np.percentile(tpl_means, 75) - np.percentile(tpl_means, 25))

    return ell_hat, (float(lo), float(hi)), {
        "n_templates": T,
        "counts_by_template": counts,
        "imbalance_ratio": imbalance,
        "template_iqr_logit": tpl_iqr,
        "method": "equal_by_template_cluster_bootstrap"
    }

# Optional: simple registry if we add more estimators later
AGGREGATORS = {
    "simple": aggregate_simple,
    "clustered": aggregate_clustered
}

3.2 Small change: rpl_eval.py
	•	Build by_template_logits using meta.prompt_sha256.
	•	Call the chosen aggregator.
	•	Compute stability using the same basis as the aggregator (per‑template means for clustered).

Patch outline (key bits only):
from collections import defaultdict
from heretix_rpl.aggregation import aggregate_clustered, aggregate_simple

def evaluate_rpl_gpt5(..., agg: str = "clustered"):
    runs = []
    # ... collect samples as you do now ...

    all_logits = []
    by_tpl = defaultdict(list)
    for s in runs:
        p = s["raw"]["prob_true"]
        l = _logit(p)
        all_logits.append(l)
        by_tpl[s["meta"]["prompt_sha256"]].append(l)

    # choose aggregator
    if agg == "clustered":
        ell_hat, (lo_l, hi_l), diag = aggregate_clustered(by_tpl, B=2000)
        stability_basis = [float(np.mean(v)) for v in by_tpl.values()]
    else:
        ell_hat, (lo_l, hi_l), diag = aggregate_simple(all_logits, B=1000)
        stability_basis = all_logits

    p_hat = _sigmoid(ell_hat)
    lo_p, hi_p = _sigmoid(lo_l), _sigmoid(hi_l)

    iqr_l = float(np.percentile(stability_basis, 75) - np.percentile(stability_basis, 25))
    stability = 1.0 / (1.0 + iqr_l)

    return {
        # ... unchanged metadata ...
        "aggregates": {
            "prob_true_rpl": p_hat,
            "ci95": [lo_p, hi_p],
            "ci_width": hi_p - lo_p,
            "stability_score": stability,
            "is_stable": (hi_p - lo_p) <= 0.2
        },
        "paraphrase_results": runs,
        "paraphrase_balance": diag if agg == "clustered" else {"method": "simple_mean"},
        "raw_logits": all_logits
    }

Also pass agg through the router:

def evaluate_rpl(..., agg: str = "clustered"):
    if model.startswith("gpt-5"):
        return evaluate_rpl_gpt5(..., agg=agg)
    # legacy path unchanged

3.3 Tiny CLI tweak: cli.py

Add a flag (default clustered) and forward it:

agg: str = typer.Option("clustered", help="Aggregator: clustered | simple")
result = evaluate_rpl(claim_text=claim, model=model, k=k, seed=seed, r=r, agg=agg)

CLI UX is unchanged otherwise.

4) Backwards compatibility
	•	Default behavior becomes clustered (the “correct” estimator).
	•	If you need to compare with the old behavior, run with --agg simple.
	•	All existing files, prompts, schemas, sampling (K×R), logging remain unchanged.

5) Future‑proofing
	•	Single point of change: all estimator variations live in aggregation.py.
	•	You can add:
	•	Robust location (trimmed mean, Huber) over template means,
	•	Weighted templates (e.g., learned weights from calibration),
	•	Different bootstrap B counts via config,
	•	Bayesian calibration layer post‑aggregation.
	•	Optional config file (e.g., heretix.toml):

[aggregation]
method = "clustered"
bootstrap_B = 2000

Loader reads this and sets defaults; CLI can still override.

6) Acceptance criteria (what “done” looks like)
	1.	Estimator isolation: Code compiles; aggregation.py contains both estimators; rpl_eval.py uses the aggregator interface only.
	2.	Correct outputs:
	•	paraphrase_balance present with counts_by_template, imbalance_ratio, n_templates.
	•	stability_score computed on per‑template means when agg=clustered.
	•	prob_true_rpl and CI95 change only slightly on current datasets (they may tighten); no formatting changes elsewhere.
	3.	CLI switch: --agg clustered|simple works; defaults to clustered.
	4.	Resilience: If some samples fail or templates change, the clustered estimator still gives equal weight per template present.

7) Quick test plan
	•	Smoke:

    uv run heretix-rpl rpl --claim "tariffs don't cause inflation" --k 7 --r 3

Confirm paraphrase_balance.counts_by_template shows the wrap‑around pattern (e.g., 6,6,3,3,3) and imbalance_ratio ≈ 2.0.

	•	Compare estimators:

    uv run heretix-rpl rpl --claim "..." --agg simple

  Numbers should be close; clustered is the one to publish.  

  	•	Uniform K:

    uv run heretix-rpl rpl --claim "..." --k 10 --r 3

    Now counts per template should be equal; both estimators should converge even closer.

8) Complexity & cost
	•	Time: O(N) over samples; bootstrap adds O(B·T) where T = #templates (small).
	•	Memory: negligible beyond current runs list.
	•	Cost: unchanged; you’re only changing how you reduce the samples you already pay for.

⸻

TL;DR for the assistant
	•	Add heretix_rpl/aggregation.py with two functions: aggregate_clustered (new default) and aggregate_simple (legacy).
	•	Wire rpl_eval.py to build by_template_logits using meta.prompt_sha256, call the chosen aggregator, compute stability on the matching basis, and include paraphrase_balance in the JSON.
	•	Add --agg to CLI (default clustered).
	•	No other files change. This makes the estimator correct, auditable, and future‑proof without touching sampling, prompts, or schema.