RPL Compliance Rate

- Definition: fraction of attempted samples that pass the RPL policy checks.
- Criteria: output is strict JSON with numeric prob_true, and contains no URLs/citations (heuristic: any “http://”, “https://”, “www.” anywhere in the
JSON string).
- Aggregation: only compliant samples are included; non‑compliant ones are dropped.
- Value meaning: 1.0 means every attempted sample was compliant; lower values indicate JSON/formatting issues or citations from the provider.

Cache Hit Rate

- Definition: fraction of sampling attempts served from the local SQLite cache instead of calling the provider.
- Keying: cache key = hash of claim | model | prompt_version_full | prompt_sha256 | replicate_idx | max_output_tokens.
    - Changing any of these (e.g., K/R/T selection changes prompt set, prompt file version, output token limit) resets or partially invalidates the
cache.
- First run: typically 0.0 (no prior entries).
- Re‑run same config: should approach 1.0 (all attempts served from cache) unless HERETIX_RPL_NO_CACHE=1 or config changed.

center: trimmed: Uses a 20% trimmed mean on the per-template mean logits (drops lowest 20% and highest 20% before averaging). If T is small, trimming
effectively reduces to a plain mean.

bootstrap_seed: 10572428983809627848: Deterministic seed for the bootstrap RNG. Derived from claim, model, prompt_version, K, R, template hashes, center,
trim, and B. Ensures the CI is reproducible for the same inputs. You can override with HERETIX_RPL_SEED.
- 
imbalance_ratio: 1.0: Ratio of max/min valid counts across templates (from counts_by_template). 1.0 means perfectly balanced sampling; >1 indicates some
templates produced fewer compliant samples (e.g., invalid JSON or citations).
- 
template_iqr_logit: 0.1037: Interquartile range of the per-template mean logits (spread across paraphrases). Lower is better (more template consistency).
This feeds stability_score and the stability_band.

method: equal_by_template_cluster_bootstrap_trimmed: Equal weight per paraphrase template; aggregates per-template mean logits using a 20% trimmed
mean. Uncertainty from a cluster bootstrap (resample templates with replacement; within each, resample replicates), repeated B=5000 times. Selected by
the Phase‑1 invariants (frozen estimator).

run_id: Deterministic recipe ID for the run.
    - How it’s built: sha256(claim | model | prompt_version_full | K | R) → first 12 hex, prefixed with heretix-rpl-.
    - When it changes: change claim, model, prompt YAML version, K, or R.
    - When it doesn’t: change T, B, seed, or max_output_tokens.
    - Where it lives: primary key in runs; also stored on each sample row; latest summary for this recipe overwrites the runs row.

execution_id: Unique ID for this specific invocation.
    - How it’s built: random UUID (prefixed exec-), one per run call.
    - When it changes: every time you run, even with the same run_id.
    - Where it lives: primary key in executions; mapped to the exact cached samples used via execution_samples; never overwritten.

Mental model

- run_id = the recipe (identity of what you planned to run).
- execution_id = the exact run instance (what actually ran this time).