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