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

