CONFIGURATION OPTIONS

location of configuration file: /Heretix/runs/rpl_example.yaml
describe to see projected output: uv run heretix describe --config runs/rpl_example.yaml
mock run: uv run heretix run --config runs/rpl_example.yaml --out runs/pick_name.json --mock  / This writes a JSON artifact at runs/k12_mock.json and persists rows to SQLite
SQLite access: RUN_ID=$(jq -r '.runs[0].run_id' runs/k12_mock.json). command saved the run ID into a shell variable, then run: sqlite3 -header -column runs/heretix.sqlite "SELECT run_id, prompt_sha256, paraphrase_idx, replicate_idx, prob_true, logit, json_valid FROM samples
WHERE run_id='$(jq -r '.runs[0].run_id' runs/k12_mock.json)' LIMIT 5;"

****imbalance_ratio: Imbalance ratio = max/min on the number of times a template is run.  T=8 templates and K=12 slots, 
    - per = floor(12/8) = 1, rem = 4
    - First rem (4) templates get reps=2 → [0,0,1,1,2,2,3,3]
    - Remaining 4 templates get reps=1 → [4,5,6,7]
    - Concatenated → [0,0,1,1,2,2,3,3,4,5,6,7]
    - Replicates R=2 are applied later (each slot is attempted R times), so total attempts per template = planned_count × R.
    - If you want a perfect balance ratio, make K a multiple of T

****rotation_offset:  rotation_offset=0, this means when the extra slots gets allocated exactly in sequence to the 1,2,3 templace in order.  For a different claim/version, rotation_offset would shift which templates get the extras, spreading load fairly across claims.  Deterministic rotation for fairness; 0 means “no rotation” for this claim/version.

****T_bank: 16: there are 16 paraphrases in the prompt YAML. There are the templates used that uses to ask the question "is this true" in different ways. 

****tpl_indices: [0..7]: the 8 templates selected (after rotation). Different claims can pick a different contiguous 8. A list of the templates used.

****K: 8 → seq: [0..7]: K “slots” are balanced across the 8 selected templates: one slot per template.

****R: 2 → total attempts: K × R = 16: each slot is sampled twice, so each template is attempted 2 times.

****seed:  42 fixes the randomness and keeps it consistent

****max_output_tokens:  The cache key 

****rpl_compliance_rate: Fraction of attempted samples that comply with the RPL policy and are eligible for aggregation.
    Policy checks:
    - JSON-only: output parses as strict JSON and contains a numeric prob_true.
    - No citations/URLs: text must not contain “http://”, “https://”, or “www.” (simple heuristic).
    - Result: a sample is compliant if both are true; otherwise it’s dropped.


****runs vs. samples:  
    runs: One summary row per run_id (claim|model|prompt_version|K|R). Stores what ran and the aggregate results.
    samples: One row per unique sample (cache_key). Stores per-template/replicate outputs used as a cache.

    What runs contains
    - Identity and inputs: claim, model, prompt_version, K/R/T/B, seed, bootstrap_seed.
    - Aggregates: prob_true_rpl, ci_lo/ci_hi/ci_width, stability_score, imbalance_ratio, rpl_compliance_rate, cache_hit_rate.
    - Diagnostics: counts_by_template_json, sampler_json (selected templates, planned seq), config_json, created_at.

    What samples contains
    - Linkage: run_id (foreign key to runs), prompt_sha256, paraphrase_idx, replicate_idx.
    - Values: prob_true, logit, json_valid, latency_ms, provider_model_id, response_id, created_at, tokens_out.
    - Cache role: rows are keyed by cache_key and are replaced when reused; they’re not a full historical log.

    Important nuances
    - Same run_id re-run: runs row is replaced; samples rows with the same cache_key are replaced; new cache_keys (e.g., different T selection or
    max_output_tokens) add rows that share the same run_id.
    - Row counting: JSON artifact shows exactly-what-was-used this execution; counting samples by run_id in DB can exceed K×R if you’ve run the same
    run_id with different cache_keys over time

    - One run_id links to many rows in samples. Each row is a unique cached sample keyed by cache_key (includes claim, model, prompt_version_full,
    prompt_sha256, replicate_idx, max_output_tokens).

Design:
What things are “knobs” you optimize

- Claim/model/prompt: choose what you evaluate and which prompt bank to use.
- Templates: yes, a knob. You control:
    - prompt_version/prompts_file: the template bank itself (you can edit paraphrases and bump version).
    - T: how many templates to include from the bank.
    - Optional next step: add template_include/template_exclude to pick exact templates.
- K/R: sampling plan
    - K: breadth across templates (more slots per template set → tighter CI).
    - R: depth within template (replicates; useful if provider has randomness).
- B/seed: CI precision/reproducibility
- max_output_tokens: provider behavior/compliance; included in cache identity.

What a “sample” is vs a “run”

- Sample: one atomic evaluation for a specific template+replicate with specific settings (claim, model, prompt_version_full, token cap). It’s the
smallest unit of work.
- Run: a plan that collects many samples (K slots × R replicates across T templates), then aggregates to p/CI/stability.

Why we cache at sample level

- Re-running the same plan (same sample ingredients) shouldn’t pay provider cost again. Caching replaces repeated identical samples with a lookup — but
it doesn’t change which samples the run uses or how we aggregate them.
- R is a knob: it controls how many replicate indices exist. replicate_idx is an internal label so we can uniquely cache each replicate.

Why this structure supports “clear, comparable evals”

- Every execution writes a JSON artifact that is the canonical record (what ran, what was used, the outputs). You can line up files for A/B and train
on them.
- The DB persists:
    - runs: latest summary for a run_id (the recipe: claim|model|prompt_version|K|R).
    - samples: reusable atomic results keyed by exact sample identity (cache_key). This is for speed and audit, not your primary “per-execution” record.

What to do when you change things

- Change prompts/templates: edit the YAML and bump version; or (future) use template_include. That’s a real optimization knob.
- Change K/T/R: tighten precision/consistency (K/T), or capture within-template randomness (R).
- Keep per-execution history: rely on the JSON artifact (–out). If you also want per-execution rows in DB, we can add an executions table and link
exactly which cached samples were used (I can implement this next if you want).

Key mental model

- Run_id = the recipe definition (claim|model|prompt_version|K|R).
- Samples = the ingredient measurements (template+replicate outputs) reused for performance.
- JSON artifact = the execution record (what you compare/learn from).
- Aggregation uses only the samples collected/valid in that execution; caching only decides whether we call the provider or reuse — it doesn’t change the math.

CONCURRENCY (ENV VAR)

- HERETIX_CONCURRENCY (int; default 0/off): parallelize provider calls with a bounded thread pool.
  - Recommended: 6–8. Increase cautiously based on provider limits.
  - Determinism & identity: replicate indices, prompt hashes, and cache keys are computed before dispatch; DB writes occur on the main thread.
  - Estimator/DB schema unchanged. Same inputs and seed → same p/CI/stability.
  - Token cap tip: for long claims, use `max_output_tokens: 768–1200` to avoid truncated JSON under parallel load.

- ARTIFACT CAPTURE (ENV VAR)
  - `HERETIX_ARTIFACT_BACKEND`: `local` (default), `gcs`, or `disabled`.
    - `local`: writes manifests + compressed payloads under `HERETIX_ARTIFACT_PATH` (defaults to `runs/artifacts`).
    - `gcs`: upload to Google Cloud Storage; requires `HERETIX_ARTIFACT_BUCKET` and optional `HERETIX_ARTIFACT_PREFIX`.
    - `disabled`: skips artifact creation.
  - `HERETIX_ARTIFACT_PATH`: filesystem root for the local backend (auto-created).
- CLI/API responses include `web_artifact.manifest` when capture is enabled.
- Export helper: `uv run python scripts/export_web_artifacts.py --artifact-root runs/artifacts --out runs/exports`.
- CLI inspection helper: `uv run heretix artifact --run-id <RUN_ID>` or `--claim "<claim text>"`.
