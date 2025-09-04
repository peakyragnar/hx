SQLite basics

- Show 5 samples for the last run JSON file:
    - sqlite3 -header -column runs/heretix.sqlite "SELECT run_id,prompt_sha256,paraphrase_idx,replicate_idx,prob_true,logit,json_valid FROM samples WHERE
run_id='$(jq -r '.runs[0].run_id' runs/k12_r3_mock_v2.json)' LIMIT 5;"
- See all rows for a run (be careful if large):
    - sqlite3 -header -column runs/heretix.sqlite "SELECT * FROM samples WHERE run_id='$RUN_ID';"
- Interactive mode:
    - sqlite3 runs/heretix.sqlite
    - .headers on
    - .mode column
    - SELECT ...;
    - .exit

Common queries

- Latest runs (summary):
    - sqlite3 -header -column runs/heretix.sqlite "SELECT run_id,datetime(created_at,'unixepoch') ts,claim,prompt_version,K,R,T,ROUND(prob_true_rpl,3)
p,ROUND(ci_lo,3) lo,ROUND(ci_hi,3) hi,ROUND(ci_width,3) w,ROUND(stability_score,3) s FROM runs ORDER BY created_at DESC LIMIT 10;"
- All attempts for a run:
    - sqlite3 -header -column runs/heretix.sqlite "SELECT prompt_sha256,paraphrase_idx,replicate_idx,prob_true,logit,json_valid FROM samples WHERE
run_id='$RUN_ID' ORDER BY paraphrase_idx,replicate_idx;"
- Valid vs dropped:
    - sqlite3 runs/heretix.sqlite "SELECT json_valid,COUNT(*) FROM samples WHERE run_id='$RUN_ID' GROUP BY json_valid;"
- Per-template counts and mean logit:
    - sqlite3 -header -column runs/heretix.sqlite "SELECT prompt_sha256,COUNT(*) n,SUM(json_valid) valid,ROUND(AVG(logit),3) avg_logit FROM samples WHERE
run_id='$RUN_ID' GROUP BY prompt_sha256 ORDER BY n DESC;"
- Planned counts (from run row):
    - sqlite3 runs/heretix.sqlite "SELECT counts_by_template_json FROM runs WHERE run_id='$RUN_ID';"
- Full run aggregates:
    - sqlite3 -header -column runs/heretix.sqlite "SELECT
run_id,prob_true_rpl,ci_lo,ci_hi,ci_width,stability_score,imbalance_ratio,rpl_compliance_rate,cache_hit_rate FROM runs WHERE run_id='$RUN_ID';"

Export to CSV (for Excel/Sheets)

- Samples:
    - sqlite3 -header -csv runs/heretix.sqlite "SELECT run_id,prompt_sha256,paraphrase_idx,replicate_idx,prob_true,logit,json_valid FROM samples WHERE
run_id='$RUN_ID'" > runs/samples_$RUN_ID.csv
- Runs:
    - sqlite3 -header -csv runs/heretix.sqlite "SELECT * FROM runs" > runs/runs_export.csv

Tip

- Keep SQL on one line or close quotes properly; if you see dquote>, you have an unclosed "…". Use .exit to leave interactive mode.

Samples table (all columns)

- run_id: deterministic ID for the run (joins to runs).
- cache_key: unique key for caching/dedup (claim|model|prompt_version|prompt_sha256|replicate_idx|max_output_tokens).
- prompt_sha256: hash of the exact prompt text (system + schema + user) for this sample; identifies the template cluster.
- paraphrase_idx: index of the paraphrase in the YAML bank used for this run (after rotation/selection).
- replicate_idx: replicate number for this template (now unique across slots; equals occurrence*R + r).
- prob_true: numeric probability parsed from provider JSON; None if invalid.
- logit: logit(prob_true), used for aggregation; None if invalid.
- provider_model_id: provider’s reported model ID (e.g., gpt-5, gpt-5-MOCK).
- response_id: provider response identifier (for provenance).
- created_at: Unix timestamp when the sample row was created.
- tokens_out: token count if available (may be null with current adapter).
- latency_ms: request latency in milliseconds.
- json_valid: 1 if the sample complies with RPL policy (strict JSON, numeric prob_true, no URLs/citations), else 0.

Why these fields

- Caching/dedup: cache_key, prompt_sha256, replicate_idx.
- Aggregation: prob_true, logit, json_valid (only valid rows contribute).
- Provenance: provider_model_id, response_id, created_at.
- Ops/metrics: latency_ms, tokens_out (when available).
- Joins/filtering: run_id, paraphrase_idx.

Runs table (summary row per run)

- Identity/inputs: run_id, created_at, claim, model, prompt_version, K, R, T, B, seed, bootstrap_seed.
- Aggregates: prob_true_rpl, ci_lo, ci_hi, ci_width, stability_score, template_iqr_logit, imbalance_ratio, rpl_compliance_rate, cache_hit_rate.
- JSON blobs: config_json (exact inputs), sampler_json (T_bank/T/seq/tpl_indices), counts_by_template_json (valid counts per template).
- artifact_json_path: reserved pointer to the JSON artifact (optional).

Handy queries

- All columns (samples): sqlite3 -header -column runs/heretix.sqlite "SELECT * FROM samples WHERE run_id='$RUN_ID' LIMIT 5;"
- All columns (runs): sqlite3 -header -column runs/heretix.sqlite "SELECT * FROM runs WHERE run_id='$RUN_ID';"
- Schema info: sqlite3 runs/heretix.sqlite "PRAGMA table_info(samples);" and "PRAGMA table_info(runs);"

This structure keeps the DB minimal but complete for reproducibility (what ran), aggregation (what was used), and performance (how it behaved).