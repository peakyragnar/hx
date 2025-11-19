Here is a conceptual explanation of how WEL (Web-Informed Lens) works.

  1. Core Purpose

  At its heart, the Web-Informed Lens (WEL) is designed to improve upon the "Raw Prior Lens" (RPL). While RPL
  measures a model's internal beliefs about a claim, WEL enriches this by consulting the web for real-world 
  evidence.

  The goal is to provide a more accurate and grounded assessment of a claim by either:

   1. Finding a definitive answer: If the web provides strong, consistent evidence, WEL can declare a claim a
      "resolved fact."
   2. Blending evidence with the model's prior: If the evidence is mixed or inconclusive, WEL combines the web
      findings with the model's original belief to produce a more nuanced probability.

  2. How It Works: The Execution Flow

  Conceptually, WEL operates in a series of steps:

   1. Fetch Evidence: For a given claim, WEL starts by fetching a set of relevant documents (snippets, articles,
      etc.) from the web. It then deduplicates these results and ensures a diversity of sources by limiting the
      number of documents from any single domain.

   2. Enrich and Understand the Evidence:
       * Find Publish Dates: For each document, WEL tries to determine its publication date. This is crucial for
         assessing the recency and relevance of the evidence. It uses a variety of techniques to do this, from
         looking at structured data on the page to analyzing the URL and page content.
       * Analyze the Claim: WEL does a lightweight analysis of the claim itself to understand what kind of claim
         it is (e.g., about an event, a person, etc.) and whether it's time-sensitive.

   3. Attempt to Resolve the Claim as a Fact: This is a key feature of WEL. It tries to determine if there is a
      clear consensus on the web that resolves the claim.
       * Per-Document Verdict: WEL uses an AI model to read each document and determine its stance on the claim
         (e.g., "supports," "contradicts," or "unclear"). It also extracts a direct quote that supports its
         verdict.
       * Weigh the Evidence: The "votes" from each document are weighted based on factors like the reputation of
         the source domain and the recency of the article.
       * Declare a Consensus: If the weighted evidence strongly supports or contradicts the claim (and comes
         from multiple different domains), WEL declares the claim a "resolved fact."

   4. Produce the Final Result:
       * If the claim is resolved (the "short-circuit" path): WEL provides a definitive answer (e.g., 99.9% true
         or 0.1% false) along with the citations (quotes and sources) that support the consensus. In this case,
         the model's original "prior" belief is not used in the final result, though it is still shown for
         transparency.
       * If the claim is unresolved (the probabilistic path): If the web evidence is weak, mixed, or
         contradictory, WEL falls back to a probabilistic approach. It combines the web evidence with the
         model's original prior belief to produce a final, blended probability.

  In a Nutshell

  Think of WEL as a two-stage fact-checker. It first tries to find a definitive, evidence-backed answer on the
  web. If it succeeds, it presents that answer with its sources. If it can't find a clear consensus, it acts
  more like a research assistant, synthesizing the web evidence with a model's "gut feeling" to give a more
  nuanced, probabilistic answer.

  Excellent question. When a claim isn't definitively resolved by web evidence, WEL calculates a weight to
  determine how much influence the web evidence should have compared to the model's original belief (the RPL).

  This weight, called w_web, is a blend of two key factors: the recency of the evidence and the strength of
  the evidence.

  Here’s a conceptual breakdown of how each is determined:

  1. Recency Score: How timely is the evidence?

  The recency score is designed to give more weight to newer information, especially for claims about recent
  events. It is calculated based on two main inputs:

   * Is the claim itself timely? The system first determines if the claim is about a recent event (e.g., "the
     stock market went up yesterday") or a more timeless fact (e.g., "the earth is round").
   * What is the median age of the web documents? The system looks at the publication dates of all the web
     documents it found and calculates the median age.

  The final recency score is a combination of these two factors. A claim about a recent event with very fresh
  web articles will get a high recency score. A timeless claim or a claim with very old articles will get a
  lower score.

  2. Strength Score: How strong and reliable is the evidence?

  The strength score assesses the quality and diversity of the web evidence. It is based on four main inputs:

   * Coverage (Number of Documents): How many relevant documents were found? More documents generally lead to a
     higher score.
   * Diversity (Number of Domains): How many different websites did the documents come from? Evidence from a
     wide range of domains is considered stronger and gets a higher score.
   * Agreement (Dispersion): How much do the different sources agree with each other? If the evidence is all
     pointing in the same direction, the strength score will be higher. If the evidence is contradictory, the
     score will be lower.
   * Validity (JSON Valid Rate): This is a measure of how reliably the AI model was able to extract structured
     information from the web documents. A higher success rate leads to a higher strength score.

  3. The Final w_web Weight

  The final w_web is a weighted average of the recency_score and the strength_score (with recency being
  slightly more important). This final weight is then clamped to be between a minimum of 0.20 and a maximum of
  0.90.

  This means that the web evidence will always have at least 20% influence on the final result, but no more
  than 90%.

  In summary, if the web evidence is recent, strong, and comes from a diverse set of sources that are in 
  agreement, it will be given a high weight, and the final result will be heavily influenced by the web. If
  the evidence is old, weak, or contradictory, it will be given a lower weight, and the model's original
  belief will have a stronger influence on the final result.

  Here is a conceptual explanation of how RPL (Raw Prior Lens) works.

  1. Core Purpose

  The "Raw Prior Lens" (RPL) is a method for measuring a model's "internal prior" belief about a claim. In
  simple terms, it tries to answer the question: "Without looking anything up, what does the AI model *really* 
  think is the probability that this claim is true?"

  The "raw prior" part is key: RPL is designed to elicit the model's belief based only on its training data,
  not on any information it might retrieve from the web during the conversation.

  2. How It Works: The RPL Workflow

  To get a reliable measure of the model's belief, RPL uses a sophisticated process of prompting, sampling,
  and aggregation. Here's a step-by-step breakdown of the concepts involved:

  Step 1: Paraphrasing the Claim

  Instead of just asking the model about the claim in one way, RPL uses a set of 16 different paraphrases to
  ask the same question in slightly different ways. For example, it might ask:

   * "Assess the probability that the following statement is true as written: {CLAIM}"
   * "Given your internal knowledge only, what is the chance this claim holds? {CLAIM}"
   * "Without external sources, evaluate the truth of: {CLAIM}"

  This is done to ensure that the result is not overly sensitive to the specific wording of the prompt.

  Step 2: Balanced and Rotated Sampling

  RPL is designed to be very robust and reproducible. To achieve this, it uses a "balanced and rotated"
  sampling strategy:

   * Rotation: The list of 16 paraphrases is "rotated" based on a hash of the claim, model, and prompt version.
     This means that the same claim will always be prompted with the same sequence of paraphrases, which is
     crucial for reproducibility.
   * Balancing: RPL prompts the model a configurable number of times (e.g., 20 times). It ensures that the
     paraphrases are used in a balanced way, so that each paraphrase is used at least once, and the number of
     times each paraphrase is used is as even as possible.

  Step 3: Prompting the Model and Getting Samples

  For each prompt, the model returns a JSON object that validates against `RPLSampleV1`, which includes:


   * belief.prob_true (and belief.label): the estimated probability (0-1, two decimals) and qualitative label.
   * reasons: 2-4 concise prior-based supporting points.
   * assumptions: any explicit scope or definitional assumptions.
   * uncertainties: factors that could move the estimate or missing evidence.
   * flags: refusal/off-topic booleans indicating whether the sample should be excluded.

  The results of each of these prompts are called "samples."

  Step 4: Aggregating the Samples

  This is the most complex part of the RPL process. Once all the samples have been collected, they are
  aggregated to produce a single, robust estimate of the model's belief. This is done using a method called
  "clustered bootstrap with trimmed mean."

  Here's a conceptual breakdown of what that means:

   1. Convert to Logits: The probabilities from each sample are first converted to "logits." Logits are a
      mathematical transformation of probabilities that makes them easier to work with statistically.
   2. Group by Paraphrase: The logits are grouped together based on which paraphrase was used to generate them.
   3. Calculate the "Trimmed Mean" for Each Group: For each group of logits, a "trimmed mean" is calculated. This
      is like a normal average, but it first throws out a certain percentage of the lowest and highest values.
      This makes the result more robust to outliers.
   4. Bootstrap Resampling: This is a statistical technique used to estimate the uncertainty of the result. It
      involves two levels of resampling:
       * Resample the Paraphrase Groups: It randomly selects (with replacement) from the groups of paraphrases.
       * Resample the Logits within Each Group: For each selected group, it randomly selects (with replacement)
         from the logits within that group.
   5. Calculate the Final Result: It then calculates the trimmed mean of the means of the resampled groups. This
      process is repeated thousands of times to create a distribution of the result. The final probability is the
      center of this distribution, and the 95% confidence interval is taken from the 2.5th and 97.5th percentiles
      of the distribution.

  In a Nutshell

  Think of RPL as a very rigorous and well-designed survey. Instead of just asking one person one question, it
  asks a diverse group of people the same question in many different ways, and then uses a sophisticated
  statistical method to aggregate the results and calculate the margin of error. This ensures that the final
  result is a reliable and reproducible measure of the group's collective belief.
