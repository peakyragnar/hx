The training and holdout benchmarks serve different purposes in the evaluation pipeline:

  Training Benchmark (claims_bench_train.yaml)

  - Purpose: Development and iterative optimization
  - Usage: You run this repeatedly while tweaking prompts
  - Risk: Prompts can be "overfit" to perform well on these specific claims
  - Think of it as: Practice exam questions

  Holdout Benchmark (claims_bench_holdout.yaml)

  - Purpose: Final validation on "unseen" data
  - Usage: Only run once before applying to production
  - Protection: Tests if improvements generalize beyond the development set
  - Think of it as: Final exam with different questions

  Key Differences

  | Aspect       | Training                               | Holdout                            |
  |--------------|----------------------------------------|------------------------------------|
  | Claims       | Different set of test claims           | Different set of test claims       |
  | Frequency    | Run many times during development      | Run once before apply              |
  | Optimization | You can iterate based on these results | Should not influence prompt design |
  | Purpose      | Find what works                        | Validate it actually works         |

  Why Both Are Required

  Without holdout validation, you might:
  - Create a prompt that works great on your 12 training claims
  - But fails on different types of claims in production
  - This is called "overfitting" to the training data

  The two-benchmark system ensures:
  - Your prompt improvements are robust and generalizable
  - You haven't just memorized the training examples
  - The prompt will work reliably in production

  This follows machine learning best practices where you never apply a model that hasn't been validated on held-out data.