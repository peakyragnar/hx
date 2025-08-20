1. __init__.py

  - Empty file that makes heretix_rpl a Python package
  - Allows you to import modules with from heretix_rpl import ...

2. cli.py - Command Line Interface

  Purpose: The entry point when you run uv run heretix-rpl

  What it does:
  - Parses command line arguments (--claim, --k, --r, --agg, etc.)
  - Checks for OpenAI API key
  - Calls the main evaluation function
  - Saves results to JSON file
  - Displays summary results in terminal

  Key function: rpl() - the main command that gets called

3. rpl_prompts.py - Prompt Templates

  Purpose: Contains all the text prompts sent to GPT-5

  What it contains:
  - SYSTEM_RPL: Instructions telling GPT-5 to be the "Raw Prior Lens" evaluator
  - USER_TEMPLATE: The format for asking about a claim
  - PARAPHRASES: 5 different ways to ask the same question (to avoid wording bias)
  - PROMPT_VERSION: Version tracking for prompts

4. rpl_schema.py - Response Validation

  Purpose: Ensures GPT-5 returns properly structured JSON

  What it defines:
  - Required fields: prob_true, confidence_self, assumptions, etc.
  - Data types and constraints (probabilities must be 0-1)
  - Array size limits (3-6 reasoning bullets, 2-4 contrary considerations)

  5. seed.py - Deterministic Seeding (NEW)

  Purpose: Creates reproducible random numbers for bootstrap confidence intervals

  What it does:
  - Takes your claim, model, settings, and templates
  - Creates a unique "fingerprint" using SHA-256 hash
  - Returns a seed number that's always the same for identical inputs
  - Ensures same claim + settings = same confidence intervals

  6. aggregation.py - Statistical Aggregation (ENHANCED)

  Purpose: Combines 21 probability samples into a final estimate

  Two methods:
  - aggregate_simple(): Old method, direct average (can be biased)
  - aggregate_clustered(): New robust method with:
    - Equal weighting per template (fixes bias)
    - Trimmed mean (drops outlier templates)
    - 5000 bootstrap iterations (smooth confidence intervals)
    - Deterministic seeding (reproducible results)

  Helper: _trimmed_mean() - Drops extreme values before averaging

  7. rpl_eval.py - Core Evaluation Engine (ENHANCED)

  Purpose: Orchestrates the entire evaluation process

  Main functions:
  - evaluate_rpl_gpt5(): Handles GPT-5 evaluation with K×R sampling
  - call_rpl_once_gpt5(): Makes single API call to GPT-5
  - evaluate_rpl(): Router that picks GPT-5 vs legacy path

  What it does:
  1. Makes K×R API calls (e.g., 7×3 = 21 calls)
  2. Groups samples by template hash
  3. Generates deterministic seed (or uses HERETIX_RPL_SEED)
  4. Calls robust aggregation with seeded random number generator
  5. Returns comprehensive JSON with results, seed, and diagnostics

  The Flow:

  1. CLI parses your command
  2. rpl_eval orchestrates K×R sampling
  3. rpl_prompts provides the text templates
  4. rpl_schema validates GPT-5 responses
  5. seed creates reproducible randomness
  6. aggregation combines results robustly
  7. CLI saves and displays final results

  The system is now unbiased (equal template weighting), robust (trimmed mean), and reproducible (deterministic seeding).

  The Import Chain

  Look at the imports in cli.py:
  from heretix_rpl.rpl_eval import evaluate_rpl

  Then look at the imports in rpl_eval.py:
  from heretix_rpl.rpl_prompts import SYSTEM_RPL, USER_TEMPLATE, PARAPHRASES, PROMPT_VERSION

  What Happens When You Run the Command

  When you run uv run heretix-rpl --claim "test", here's the sequence:

  1. Python loads cli.py

  - Python sees the import: from heretix_rpl.rpl_eval import evaluate_rpl
  - This forces Python to load and execute rpl_eval.py

  2. Python loads rpl_eval.py

  - Python sees: from heretix_rpl.rpl_prompts import SYSTEM_RPL, USER_TEMPLATE, PARAPHRASES, PROMPT_VERSION
  - This forces Python to load and execute rpl_prompts.py
  - The prompts are now loaded into memory as variables

  3. Python loads rpl_prompts.py

  - All the prompt templates get defined:
  SYSTEM_RPL = """You are the Raw Prior Lens..."""
  PARAPHRASES = [
      "Assess the probability that...",
      "Estimate how likely it is...",
      # etc.
  ]

  4. Now cli.py can run

  - The rpl() function calls: evaluate_rpl(claim_text=claim, ...)
  - evaluate_rpl() already has access to PARAPHRASES because it was imported
  - Inside the evaluation loop: phr = PARAPHRASES[k % len(PARAPHRASES)]

  Key Point: Imports Happen BEFORE Execution

  The prompts are loaded during the import phase, not when the function is called. By the time cli.py:rpl() runs, all the prompt templates are
  already in memory.

  The Actual Flow:

  uv run heretix-rpl --claim "test"
      ↓
  cli.py loads
      ↓
  cli.py imports evaluate_rpl from rpl_eval.py
      ↓
  rpl_eval.py loads and imports PARAPHRASES from rpl_prompts.py
      ↓
  rpl_prompts.py loads, defines all prompt templates
      ↓
  Now cli.py:rpl() function can execute
      ↓
  Calls evaluate_rpl() which already has PARAPHRASES available
      ↓
  Uses PARAPHRASES[k % len(PARAPHRASES)] to get prompt templates

  So the prompts are "pre-loaded" through the Python import system before any evaluation actually happens!