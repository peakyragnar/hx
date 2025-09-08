
•	openai = official SDK (Responses API)
•	pydantic = optional local validation
•	typer = CLI
•	numpy = log‑odds math

. Removed: venv/ directory
  2. Added:
    - pyproject.toml - Modern Python project configuration
    - uv.lock - Lockfile for reproducible builds
    - .venv/ - uv-managed virtual environment
    - main.py - Basic Python entry point
    - README.md - Project readme

Usage commands:
  - Run code: uv run python main.py
  - Add dependencies: uv add package-name
  - Install dependencies: uv sync
  - Activate shell: uv shell (optional)

  Pitfalls & guardrails
	•	Tie‑like situations: If two tokens have nearly equal probability, providers have deterministic tie‑breakers but small numeric noise can flip outcomes across versions. Mitigation: paraphrase bagging and aggregating in log‑odds space (as we planned).
	•	Provider changes: A silent model update can shift outputs even with the same settings. Always log model id/version and prompt version; treat RPL as a measurement with provenance, not an absolute.
	•	Formatting fragility: If you’re not using a structured‑output mode, add strict instructions and consider a stop sequence after the closing brace to reduce over‑generation.

The minimal API/parameter changes you enact
	1.	Use the Responses API everywhere (you already do). Keep Structured Outputs for schema‑enforced JSON.  ￼
	2.	Stop sending: temperature, top_p, presence_penalty, frequency_penalty. (Treat them as no‑ops on GPT‑5.)  ￼
	3.	Do send:
	•	model="gpt-5" (or gpt-5-mini for throughput),
	•	max_output_tokens=... (fixed),
	•	reasoning_effort="minimal"; optionally verbosity="low" if your account supports it (feature‑detect).  ￼ ￼
	4.	Increase samples: set defaults like K=7, R=3 (N=21) and adapt upward if stability is poor.
	5.	Aggregate with robustness and publish CI + stability.

Output:
prob_true_rpl: 0.237 (low probability the claim is true)
CI95: [0.229, 0.251] (tight confidence interval)
is_stable: true (reliable estimate)

prob_true_rpl: p_RPL: This is the model’s estimated probability that the claim is true, using only its internal knowledge (no retrieval), aggregated across 21 samples.  We computed it correctly in log‑odds space (convert each sample’s probability to logits → robustly average → convert back). That avoids arithmetic illusions you’d get from naïvely averaging probabilities.  Interpretation: the model’s prior is that the claim is likely false—about a 24% chance it’s true as stated under the scope the model implicitly assumed.

CI95: [0.229, 0.251] (tight confidence interval).  You substract 0.251 - 0.229 = 0.022. Interpretation: A narrow width (a small number like 0.022) means the estimate is very precise.  Why it's Surprising: With a small sample size (N=21), you typically expect a lot of uncertainty, which would result in a wide confidence interval. A narrow interval from just 21 samples is a strong sign of a very stable and consistent result.  This is using bootstrapping statistical method (Resample: Create a new "bootstrap sample" by randomly picking 21 data points from your original set. Crucially, you pick with replacement, meaning the same data point can be chosen multiple times.) and logic space transformation (Probabilities are stuck between 0 and 1. Standard statistical methods often work better with data that has no upper or lower limit.)

is_stable: The stability score (S) is a single number designed to quickly tell you how consistent your estimate is. It is calculated based on the spread of the bootstrapped results.  it uses IQR (interquartile range) this measures the spread of the middle 50% of your data.  It is the distance between 25% and 75%.   A tightly clusters means high consistency, very spread out means low consistency. 

Clustered aggregation is the default (and statistically correct) method that fixes a bias problem in the original implementation.

  The Problem It Solves:

  - With K=7 paraphrases but only 5 templates available, the system wraps around
  - Templates 0 and 1 get used twice (6 samples each)
  - Templates 2, 3, 4 get used once (3 samples each)
  - This creates paraphrase imbalance where some templates have double weight

  How Clustered Aggregation Works:

  1. Groups samples by template: Uses prompt_sha256 to identify which samples came from the same paraphrase template
  2. Per-template averaging: Averages the R replicates within each template in log-odds space
  3. Equal template weighting: Each of the 5 templates gets equal weight in the final estimate (regardless of how many samples it contributed)
  4. Cluster bootstrap: Generates confidence intervals by resampling templates first, then replicates within templates

  Alternative:

  - --agg simple: The old method that directly averages all 21 samples equally (can be biased due to template wraparound)

  Why It Matters:

  Clustered aggregation ensures that your estimate reflects an equal contribution from each paraphrase approach, rather than being skewed toward
  whichever templates happened to get sampled more often due to the K > 5 wraparound.

  The paraphrase_balance output shows you the imbalance ratio and counts per template so you can verify the bias was corrected.

   Command Options Explained

  Let me break down what each option does:

  The Basic Command Structure:

  uv run heretix-rpl --claim "your text" --k 7 --r 3

  What Each Part Means:

  --claim "your text" (REQUIRED)

  This is the statement you want to evaluate. The system will estimate how likely it is to be true.
  - Example: --claim "coffee improves productivity"
  - Example: --claim "tariffs cause inflation"

  --k 7 (Number of paraphrase slots)

  The system asks the same question 7 different ways to avoid bias from specific wording.
  - We only have 5 unique ways to ask, so with K=7, two ways get used twice
  - Default is 7 (recommended)
  - Think of it like asking 7 different people to translate your question

  --r 3 (Replicates per paraphrase)

  For each way of asking, we ask 3 times to handle randomness in GPT-5.
  - With K=7 and R=3, you get 7×3 = 21 total samples
  - Default is 3 (recommended)
  - Like rolling a die 3 times to get a better average

  --agg clustered (Aggregation method)

  How to combine all 21 results into one final answer:
  - clustered (default) = Smart method that fixes imbalances, drops outliers
  - simple = Old method, just averages everything (can be biased)
  - You usually don't need to change this

  --out runs/filename.json (Output file)

  Where to save the results:
  - Default: runs/rpl_run.json
  - Change it to keep different runs separate

  --model gpt-5 (Which AI model)

  - Default: gpt-5
  - Other options: gpt-5-mini, gpt-4o

  The Special Environment Variable:

  HERETIX_RPL_SEED=42 (Optional)

  Makes the random parts non-random (reproducible):
  # Without seed: Different confidence intervals each run (but same estimate)
  uv run heretix-rpl --claim "test" --k 7 --r 3

  # With seed: EXACT same results every time
  HERETIX_RPL_SEED=42 uv run heretix-rpl --claim "test" --k 7 --r 3

  Simple Examples:

  Just evaluate a claim (easiest):
  uv run heretix-rpl --claim "sugar is addictive"
  This uses all defaults: K=7, R=3, clustered aggregation

  Make it reproducible:
  HERETIX_RPL_SEED=999 uv run heretix-rpl --claim "sugar is addictive"
  Now you'll get the EXACT same numbers if you run it again

  Save with a specific name:
  uv run heretix-rpl --claim "sugar is addictive" --out runs/sugar_test.json

  What You'll Get:

  - prob_true_rpl: Probability the claim is true (e.g., 0.237 = 23.7% chance)
  - ci95: Confidence interval [lower, upper] showing uncertainty
  - stability_score: How consistent the result is (closer to 1 = more stable)

  TEST SUITE


  ✅ Updated all scripts and hooks to use uv:
  - run_tests.sh - Now detects and uses uv run pytest
  - .git/hooks/pre-commit - Uses uv run pytest when available
  - .git/hooks/pre-push - Uses uv run pytest when available
  - tests/README.md - Updated documentation for uv commands

  🧪 How to Test the Test Suite with uv

  Quick test commands:

  # Run fast tests (what pre-commit runs)
  ./run_tests.sh fast

  # Run all tests
  ./run_tests.sh

  # Run with coverage
  ./run_tests.sh coverage

  # Or directly with uv
  uv run pytest tests -m "not slow" -v  # Fast tests
  uv run pytest tests -v                 # All tests

  🪝 Git Hooks Explained

  Git hooks are scripts that Git automatically runs at specific points in your workflow. They're stored in .git/hooks/ and act as automated
  gatekeepers for code quality.

  How Git Hooks Work

  1. Location: .git/hooks/ directory
  2. Trigger: Git automatically executes them at specific events
  3. Control: If a hook exits with non-zero status, Git blocks the operation
  4. Languages: Any executable script (bash, python, etc.)

  Our Two Hooks

  🏃 Pre-commit Hook (Fast Tests)

  Trigger: Every time you run git commit

⏺ Read(.git/hooks/pre-commit)
  ⎿  Read 31 lines (ctrl+r to expand)

⏺ What it does:
  - Runs only fast tests (marked with -m "not slow")
  - Takes ~2 seconds
  - Blocks commit if tests fail
  - Can be bypassed with --no-verify

  🚀 Pre-push Hook (Full Tests)

  Trigger: Every time you run git push

⏺ Read(.git/hooks/pre-push)
  ⎿  Read 31 lines (ctrl+r to expand)

⏺ What it does:
  - Runs all tests including slow ones
  - Takes longer (~10+ seconds)
  - Blocks push if any tests fail
  - Ensures code quality before sharing

  🔄 Testing Workflow in Practice

  Here's how the hooks integrate into your development workflow:

  # 1. Make changes to code
  vim heretix_rpl/aggregation.py

  # 2. Try to commit (pre-commit hook runs automatically)
  git add .
  git commit -m "fix aggregation bug"

  🧪 Running fast statistical tests...
  ===== test session starts =====
  ... (fast tests run in ~2 seconds)
  ✅ Fast tests passed!
  [main abc1234] fix aggregation bug

  # 3. Try to push (pre-push hook runs automatically)  
  git push

  🧪 Running full statistical test suite (including slow tests)...
  ===== test session starts =====
  ... (all tests run in ~10 seconds)
  ✅ All tests passed! Ready to push.

  🆚 Hooks vs Manual Testing

  | Aspect      | Git Hooks                    | Manual Testing   |
  |-------------|------------------------------|------------------|
  | Automation  | Automatic on git commands    | Manual execution |
  | Speed       | Fast tests only (pre-commit) | You choose       |
  | Coverage    | Staged progression           | Any subset       |
  | Enforcement | Blocks bad code              | Optional         |
  | Bypass      | --no-verify flag             | N/A              |

  📊 Test Categories by Hook

  Pre-commit (Fast - 82 tests)

  # These run automatically on git commit
  uv run pytest tests -m "not slow" --quiet
  - ✅ Logit/sigmoid transformations
  - ✅ Basic aggregation
  - ✅ Edge cases
  - ✅ Seed determinism
  - ✅ Configuration tests
  - ✅ Property-based tests (bounded)

  Pre-push (All - 84 tests)

  # These run automatically on git push
  uv run pytest tests -v
  - Everything from fast tests, PLUS:
  - 🐢 Bootstrap CI coverage tests
  - 🐢 Large sample convergence
  - 🐢 Heavy statistical simulations

  🛠️ Manual Override Options

  # Skip pre-commit hook
  git commit -m "message" --no-verify

  # Test hooks manually
  .git/hooks/pre-commit   # Test the pre-commit hook
  .git/hooks/pre-push     # Test the pre-push hook

  # Run same tests manually
  ./run_tests.sh fast     # Same as pre-commit
  ./run_tests.sh          # Same as pre-push

  🎯 Why This Design?

  1. Developer Experience: Fast feedback loop (2s vs 10s)
  2. Quality Gates: Multiple checkpoints prevent bad code
  3. Efficiency: Heavy tests only run before sharing
  4. Flexibility: Can bypass when needed
  5. CI Alignment: Same tests run locally and in CI

  The hooks ensure statistical correctness is verified at every stage without slowing down development!