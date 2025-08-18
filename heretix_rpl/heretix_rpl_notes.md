cli.py explained

This cli.py file implements a command-line interface for the Raw Prior Lens (RPL) evaluation system from the Heretix design. Here's what it
  does:

  Purpose: CLI tool to evaluate claims using the Raw Prior Lens approach (model responses without external retrieval/citations)

  Main command: rpl

  Parameters:
  - claim - The claim text to evaluate
  - model - AI model to use (defaults to "gpt-4o-mini")
  - k - Number of evaluations to run (defaults to 5)
  - seed - Random seed for reproducibility (defaults to 42)
  - out - Output JSON file (defaults to "rpl_run.json")

  Workflow:
  1. Calls evaluate_rpl() function with the claim and parameters
  2. Saves results to JSON file
  3. Prints the aggregated probability that the claim is true

  Usage example:
  uv run python heretix_rpl/cli.py rpl "String theory has crowded out physics progress" --k 10 --out results.json

  This implements the first lens from the Heretix design - capturing the model's raw prior beliefs before any evidence retrieval influences the
  response.

rpl_eval.py explained


  Purpose

  Evaluates claims by measuring the AI model's "raw prior" - its beliefs without external retrieval or evidence, using only training data
  knowledge.

  Key Functions

  call_rpl_once() - Single evaluation:
  - Takes a claim and paraphrase prompt
  - Uses OpenAI's Responses API with structured JSON output
  - Returns probability that the claim is true (0-1)
  - Uses deterministic settings (temperature=0) for consistency

  evaluate_rpl() - Multiple evaluation aggregation:
  - Runs k evaluations with different paraphrases
  - Converts probabilities to logits for statistical aggregation
  - Returns mean probability in logit space, then converts back
  - Tracks variance to measure consistency

  Statistical Approach

  - Logit transformation: Converts probabilities (0-1) to unbounded logits for proper averaging
  - Variance tracking: Measures how consistent the model's responses are across paraphrases
  - Stable run IDs: SHA256 hash for reproducibility and provenance

  Output Structure

  Returns comprehensive metadata including:
  - Individual paraphrase results
  - Aggregated prob_true_rpl (the key RPL metric)
  - Logit variance (consistency measure)
  - Timestamps and versioning for reproducibility

  This implements the first lens from the Heretix design - capturing the model's training-distribution prior before any evidence retrieval
  influences it.

  rpl_prompts.py

  This rpl_prompts.py file contains the prompting strategy for the Raw Prior Lens evaluation. Here's the breakdown:

  System Prompt (SYSTEM_RPL)

  Core mission: Extract the model's "raw prior" - internal knowledge without external retrieval

  Key constraints:
  - No browsing, searching, or citations allowed
  - Must return structured JSON matching a schema
  - Focus on literal, empirical truth probabilities

  Quality guidelines:
  1. Handle ambiguity: Make reasonable assumptions for underspecified claims
  2. Literal interpretation: Treat causal claims as actual causation
  3. Uncertainty handling: Default to ~0.5 when lacking clear signal
  4. Structured reasoning: Concise, falsifiable bullet points
  5. Self-criticism: Include 2-4 contrary considerations
  6. No fabrication: Explicitly forbids made-up references

  User Template

  Simple structure requesting JSON with specific keys:
  - prob_true - Core probability estimate (0-1)
  - confidence_self - Model's confidence in its own assessment
  - assumptions[] - What the model assumed about ambiguous parts
  - reasoning_bullets[] - Factual reasoning points
  - contrary_considerations[] - Potential counterarguments
  - ambiguity_flags[] - Areas of uncertainty

  Paraphrases Array

  5 different ways to ask the same question to:
  - Test consistency across prompt variations
  - Reduce sensitivity to specific wording
  - Enable statistical aggregation across multiple runs

  Versioning

  PROMPT_VERSION tracks changes for reproducibility and comparison across runs.

  This implements the "no external retrieval" constraint that's central to measuring the model's training-distribution prior in the Heretix
  design.

  rpl_schema.py explained

  This rpl_schema.py file defines the strict JSON schema for Raw Prior Lens responses. Here's what it enforces:

  Schema Structure

  Name: "RPLScore" - identifies this as an RPL evaluation output

  Strict mode: "strict": True ensures exact compliance with OpenAI's structured outputs

  Required Fields

  Core metrics:
  - prob_true - Probability claim is true (0.0 to 1.0)
  - confidence_self - Model's confidence in its assessment (0.0 to 1.0)

  Reasoning components:
  - assumptions - Array of strings (any length) for handling ambiguous claims
  - reasoning_bullets - 3-6 concise factual reasoning points
  - contrary_considerations - 2-4 counterarguments or ways the model could be wrong
  - ambiguity_flags - Array noting areas of uncertainty

  Quality Controls

  Enforced reasoning depth:
  - Minimum 3 reasoning bullets (prevents shallow analysis)
  - Maximum 6 reasoning bullets (prevents rambling)
  - Minimum 2 contrary considerations (forces self-criticism)
  - Maximum 4 contrary considerations (keeps focused)

  Data validation:
  - Probabilities bounded to [0,1]
  - No additional properties allowed ("additionalProperties": False)
  - All fields required (no optional responses)

  Purpose

  This schema ensures every RPL evaluation produces:
  1. Quantified beliefs (probabilities)
  2. Transparent reasoning (structured explanations)
  3. Self-awareness (confidence + contrary views)
  4. Consistency (standardized format for aggregation)

  This supports the Heretix goal of measuring and comparing model beliefs in a structured, reproducible way.