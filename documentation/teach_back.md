What RPL (GPT‑5 edition) is measuring
	•	We’re estimating the model’s prior belief about a claim, without retrieval, using many prompts that are semantic paraphrases.
	•	Each call returns prob_true ∈ (0,1). We convert to log‑odds.

Sampling / design
	•	Use K paraphrase slots × R replicates per slot → N= K x R calls.
	•	Each paraphrase slot maps to a template identified by prompt_sha256. K can exceed the number of templates; duplicates are expected (wrap‑around).
    *   A paraphrase slot is a placeholder for a specific wording of your prompt, while a replicate slot is a repetition of that same wording to check for consistency
        * Paraphrase: test how the changing the wording of a prompt affects the outcome.  This is designed to meaure the impact of phrasing.  This a dfferent way of asking if this statement is true.
        * Replicate: Test how consistent and reliable the outcome for single, unchanged wording.

Aggregation (the “best” default)

	•	Equal‑by‑template weighting: average replicates within a template → template means; then combine templates with equal weight.
	•	Center: 20% trimmed mean across template means (robust to one flaky template).With 5 templates: drop min and max; average the middle 3.
	•	Uncertainty: cluster bootstrap (resample templates, then replicates) in logit space, then transform CI back to probability.  The Problem: Your experiment has two sources of randomness: variation from changing the wording (template-to-template variation) and minor noise from re-running the same wording (replicate noise). The variation between different wordings is the much bigger and more important source of uncertainty. A simple bootstrap would mix these up and give a misleadingly narrow CI.  The Solution: A cluster bootstrap respects this structure. Think of it as a two-stage lottery.

    Stage 1 (Resample Templates): First, you randomly draw from your main groups, or "clusters"—in this case, your 5 unique paraphrase templates. You draw 5 times with replacement, so you might get a list like [Template #0, Template #1, Template #1, Template #3, Template #4].

    Stage 2 (Resample Replicates): For each template you just drew, you then randomly pick from its original replicates.  
    
    Why it's better: This method correctly captures the real-world uncertainty. The confidence interval's width will be driven by how much the results vary from template to template, which is exactly what you want to measure.


	•	Determinism: CI reproducibility comes from a fixed RNG seed (env override or computed from run config). This does not fix the model’s outputs—only the bootstrap resampling.

        The seed is a number to put into Numpy np.random.default_rng().  You will get the same sequence of random numbers every time.

        We do not randomize the model’s outputs.
        Your K×R calls to GPT‑5 give you a fixed set of numbers (one prob_true per call). Those are the “data.”

        We do randomize which of those numbers we re-use in each bootstrap replica. There are two random draws per replica:
	        1.	Template selection (cluster level).
	            •	Suppose you have T distinct paraphrase templates (identified by prompt_sha256).
	            •	For one bootstrap replica, we draw T templates with replacement from those T.
                    Example: with templates {A,B,C,D,E}, one draw could be [B, B, D, A, E].
                    Because it’s “with replacement,” some templates can appear multiple times; some may be absent in that replica.
            
            2.	Replicate selection (within each chosen template).
	            •   For each chosen template (e.g., B above), you also draw replicate indices with replacement from the actual replicate logits within that template (the ones you collected from the model).
	            •	You take the mean of those resampled replicates to get one number for that template in this replica.
        
        After you’ve got one number per chosen template, you combine them with the trimmed mean (drop the lowest 20% and highest 20% of template means; with 5 templates that’s “drop best and worst, average the middle 3”). That single combined number is the bootstrap estimate for this replica (still in log‑odds space).

        We repeat that B times (B=5000). You now have 5000 such estimates, forming an empirical distribution. Take the 2.5th and 97.5th percentiles of those 5000 numbers → that’s your 95% CI (then map log‑odds back to probability with the sigmoid).

        The numbers used are the log-odds of true for the template (it done 3 times, it would be 3 numbers).  so as bootstrap replica just takes all the numbers and randomly pull them out and then puts them back in.  it is a statisticaly approach. this creats 5000 data set of this to get a confidence interval.

        stability is 1/(1+IQR) on the template‑level log‑odds, i.e., a compact, robust score of how much the model’s belief shifts when you change the wording. Your 0.872 implies small paraphrase sensitivity and a trustworthy RPL estimate around 0.217.i 

        Quiz:
        1. What does RPL measure, and what does it explicitly not certify?
        It measures the model's prior belief (truth probabilty) under a no retrieval lens, not the training data itself.  It explicity does not certify ground truthno 
        
        2. Distinguish between a paraphrase template, a paraphrase slot, and a replicate.
        Paraphrase template: one of the 5 fixed wordings (identified by prompt_sha256).
        Paraphrase slot: one of K positions in a run (0..K-1) that maps to a template via wrap-around.
        Replicate: repeated call with identical wording for that slot to sample decode stochasticity.

        3. Why are averaging and CI computation performed in logit space instead of probability space?
        Probabilities are bounded [0,1] and non-linear; averaging them biases results near 0/1. In logit (unbounded) space, changes are more linear and
        symmetric, so means and CIs behave well.

        The Problem with Averaging Probabilities
        ***Probabilities are not linear. The difference between 98% and 99% represents a much bigger leap in certainty than the difference between 50% and 51%.

        Averaging them directly can be misleading. For example, if you average two results, 0.1 (10%) and 0.9 (90%), you get 0.5 (50%). This simple average doesn't properly account for the weight of evidence at the extremes. This is the bias the text mentions.

        The Solution: Logit Space
        To fix this, we transform the probabilities using the logit function: logit(p) = log(p / (1-p)).

        What it does: This function takes a probability (a number between 0 and 1) and stretches it onto an infinite, unbounded number line.

        Why it helps: On this new number line, the "distance" between probabilities is more uniform and symmetrical. A change from logit(0.5) to logit(0.6) is now more comparable to a change from logit(0.98) to logit(0.99). This makes standard statistical tools, like calculating the mean and confidence intervals (CIs), behave correctly and reliably.

        ****Logits add under Bayesian updates; CI on logits is closer to normal, then map back with sigmoid. We clamp p away from 0/1 to avoid infinities.

        Bayesian Update: This is the process of updating your belief about something after getting new evidence. You start with a prior belief and combine it with new data to get a posterior belief.

        The Math: In normal probability, this is done with multiplication (Bayes' Theorem). However, when you convert probabilities to log-odds (logits), this complex multiplication becomes simple addition.  Why It's Better: Adding is computationally easier and more intuitive than multiplying probabilities. It's like adding evidence scores together. A positive logit score increases your belief, and a negative one decreases it.

        The Confidence Interval (CI) Process
        The Problem: Many standard statistical methods, like calculating a confidence interval, work best when the data follows a symmetrical, bell-shaped curve (a normal distribution). Probabilities are often skewed and don't fit this assumption well.

        The Solution: Data in logit space is unbounded and often much closer to a normal distribution. So, the reliable process is:
            - Calculate the CI on the logits: Perform the statistical calculations in this mathematically stable space.
            - Map back with sigmoid: The result (e.g., a CI from -1.3 to 0.8) isn't intuitive. You use the sigmoid function (the inverse of the logit) to convert the endpoints of the interval back to a normal probability scale (e.g., 0.21 to 0.69) that is easy to understand.

        Clamping to Avoid Infinities
        The Problem: The logit function, log(p / (1-p)), is mathematically undefined at the absolute extremes.
            - If probability p = 1, you get log(1/0), which is positive infinity.
            - If probability p = 0, you get log(0/1), which is negative infinity.
        
        The Solution: To prevent your program from crashing or producing errors, you "clamp" the probability. This means you artificially force it to be a tiny bit away from the edges. For example, you might treat any value of 0 as 0.0001 and any value of 1 as 0.9999 before converting to logits. This avoids the infinities without changing the practical result.

        4. Explain the two levels of resampling in the cluster bootstrap and why uncertainty is dominated by template (not replicate) variation.

        - Two-stage resampling: (1) Resample templates with replacement (choose T template clusters from the T unique prompt_sha256), (2) For each chosen
        template, resample its replicates with replacement, compute a mean per chosen template, then apply the center (20% trimmed) across template means.
        - Why template variation dominates: Wording effects (between-template differences) are much larger than within-template replicate noise; a flat
        bootstrap would understate uncertainty by ignoring this hierarchy. The cluster bootstrap matches the data-generating structure.

        5. Where exactly is the 20% trim applied and what is dropped when T=5? Reply in one sentence.

        Trim location: Apply the 20% trim to the set of per‑template mean logits (the template centers), not to raw samples. In each calculation (and within
        each bootstrap replicate), drop the lowest and highest template mean; with T=5 you average the middle 3.

        6. Describe equal‑by‑template weighting and why it’s necessary when K exceeds the 5 paraphrase templates. Reply in 1–2 sentences.

        Equal-by-template: average replicates within each template, then give each template one equal vote in the final center. This neutralizes wrap-around
        when K > 5 so duplicated templates don’t dominate.

        7. What metadata key identifies a template cluster, and how is it computed? Reply in one sentence.

        Correct key: prompt_sha256.  SHA-256: A standard algorithm that converts any text into a fixed-length, unique string of characters (the "hash").
        How it’s computed: a SHA‑256 hash of the exact prompt text (system instructions + embedded schema + user content with the paraphrase + claim).
        Deterministic: identical text → identical hash.

        8. What does HERETIX_RPL_SEED change, and what does it not change? Reply in 1–2 sentences.

        Changes: fixes the RNG sequence for the cluster bootstrap, making CI (and any bootstrap-derived diagnostics) reproducible.
        Does not change: model outputs, the collected sample probabilities, or the point estimate from the center; only the CI/percentiles move with the
        seed.

        9. List the required JSON fields each model response must include (names only).

        prob_true, confidence_self, assumptions, reasoning_bullets, contrary_considerations, ambiguity_flags

        10. What’s the difference between aggregate_clustered and aggregate_simple? Reply in 1–2 sentences.

        aggregate_clustered: Groups logits by prompt_sha256, averages replicates per template, applies equal-by-template weighting with a 20% trimmed center,and uses a cluster bootstrap (templates then replicates) with deterministic RNG.

        aggregate_simple: Averages all logits directly and bootstraps unclustered; no equal-by-template weighting or trimming, so it can bias under
        wrap-around.

        11. What’s the default rule for “is_stable”, and where is its threshold configured?

        In config.py, the default stability width is set to 0.2, influenced by the environment variable HERETIX_RPL_STABILITY_WIDTH. The aggregator determines if something is considered stable based on whether the difference between high and low probabilities is within this width.is_stable is true when the confidence interval width is 0.20 or less and to confirm the threshold can also be adjusted via that same environment

        Confidence Interval (CI): This is the range of plausible values for a measurement you're trying to estimate. For example, a CI of [0.60, 0.75] means you are 95% confident the true value is between 60% and 75%.

        Probability Space: This simply means the numbers are expressed as probabilities, on a scale from 0 to 1.

        CI Width: This is the precision of your estimate. You calculate it by subtracting the lower bound from the upper bound.

        ≤ 0.20: This is the threshold for precision. The width must be less than or equal to 0.20.