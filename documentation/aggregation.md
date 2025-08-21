# Heretix Aggregation Methodology

## The Gold Standard: Equal-by-Template, Cluster Bootstrap, Trimmed Center (20%), Deterministic

This document explains the robust statistical aggregation used in Heretix's Raw Prior Lens (RPL) evaluation.

## Why This Approach?

### Equal-by-Template Weighting
**Problem It Solves:** Your data had an imbalance—some paraphrase templates were used more often than others (the "wrap-around" issue). Simply averaging all results would give more influence to the overused templates, creating an accidental bias.

**The Solution:** This method calculates the average for each unique template first, and then averages those results together. This ensures every paraphrase template has exactly one vote, regardless of how many times it was run. It treats the wording as a "nuisance variable"—something to be averaged out, not a source of evidence.

---

### Cluster Bootstrap
**Problem It Solves:** The main source of uncertainty isn't the tiny random variations between runs of the same paraphrase (replicate noise). The real uncertainty comes from how much the results change when you use a different paraphrase (template-to-template variation). A simple bootstrap wouldn't capture this correctly.

**The Solution:** A cluster bootstrap mirrors this two-level structure. It randomly samples by first picking from the "clusters" (the 5 unique paraphrase templates) and then picking from the replicates within those chosen templates. This correctly models the real-world source of uncertainty, giving you a more honest and realistic confidence interval (CI).

---

### Trimmed Center (20%)
**Problem It Solves:** One poorly worded or "flaky" paraphrase could create an extreme outlier that skews the overall average.

**The Solution:** This is like a judge in a diving competition. 🏊‍♀️ With 5 templates, a 20% trim means you ignore the single best-performing template and the single worst-performing template. You then average the remaining middle 3. This makes the final estimate robust and resistant to outliers, preventing a single odd result from having too much influence.

---

### Deterministic RNG (Random Number Generator)
**Problem It Solves:** Statistical methods like bootstrapping use random numbers. If the process were truly random every time, you and a colleague could run the exact same analysis on the same data and get slightly different confidence intervals, which is bad for science.

**The Solution:** A deterministic process means that by starting with a known number (a "seed"), the sequence of "random" numbers it generates is always the same. The seed is derived from the run configuration (claim, model, templates, etc.). This ensures reproducibility. Anyone with your data and your code can get the exact same result, which is essential for auditing the work and making trustworthy "prior measurement" claims.

---

### Averaging in Log-Odds Space
**Problem It Solves:** Averaging probabilities directly is statistically tricky and can lead to incorrect results, especially when values are near 0 or 1.

**The Solution:** All probability values are first converted to the unbounded log-odds (logit) scale. All the averaging and trimming happens in this mathematically stable space. The final result is then converted back to a simple probability. This is the statistically sound and correct way to handle proportions.

---

## The Result

This yields an RPL that is **unbiased, robust, reproducible, and minimally sensitive to prompt wording artifacts**.

Note on orchestration: The estimator above is unchanged in the adaptive pipeline.
Auto‑RPL only changes how samples are collected (templates‑first escalation,
balanced deterministic sampling with rotation, and sample reuse across stages).
See `documentation/auto_rpl.md` for the controller policy and CLI.

## Technical Details

### Mental Model (First Principles)
- **Why logits?** Probabilities live on [0,1] with asymmetric geometry; logits make the estimator behave like a simple mean in an unbounded space with near-Gaussian behavior for small shifts.
- **Why cluster bootstrap?** Your randomness comes from two levels (templates, replicates). Resampling both levels preserves the variance structure; a flat bootstrap would understate uncertainty when templates disagree.
- **Why equal-by-template?** Paraphrase wording should not determine the estimate. Equalizing at the template level enforces that.

### Configuration
- **Bootstrap iterations (B):** 5000 for smooth confidence intervals
- **Trim percentage:** 20% (drops 1 template from each tail with 5 templates)
- **Center function:** Trimmed mean by default, regular mean available
- **Seed derivation:** SHA-256 hash of configuration → 64-bit integer

### Quick Recipe for Common Tasks
- **Tighter CIs without more API calls:** Increase B to 10000 (minor runtime cost)
- **Make runs reproducible:** Set `HERETIX_RPL_SEED=42` environment variable
- **Guard against one bad template:** Use center="trimmed" with trim=0.2 (default)
- **Large within-template imbalance:** Set fixed_m to the min replicate count
- **A/B test estimators:** Register a new function in AGGREGATORS and select via CLI --agg

## Output Interpretation

When you see in the output:
- **`aggregation.method`**: "equal_by_template_cluster_bootstrap_trimmed"
- **`aggregation.bootstrap_seed`**: A large integer ensuring reproducibility
- **`aggregation.imbalance_ratio`**: How uneven the template counts are (1.0 = perfectly balanced)
- **`aggregation.template_iqr_logit`**: Spread between templates (smaller = more consistent)

These diagnostics help you understand both the quality of your estimate and whether the aggregation successfully handled any data imbalances.
