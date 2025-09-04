






****************************
Step 1: Preview the current run plan (no changes, no network)

- Run: uv run heretix describe --config runs/rpl_example.yaml

This prints the effective config and sampling plan (K/R/T, prompt version, rotation, planned counts). Reply “done” and, if you can, paste the output so
we can walk through it together.

T_bank: 16: there are 16 paraphrases in the prompt YAML.
T: 8: you chose to include 8 of those 16 for this run.
rotation_offset: 0: deterministic rotation for fairness; 0 means “no rotation” for this claim/version.
tpl_indices: [0..7]: the 8 templates selected (after rotation). Different claims can pick a different contiguous 8.
K: 8 → seq: [0..7]: K “slots” are balanced across the 8 selected templates: one slot per template.
R: 2 → total attempts: K × R = 16: each slot is sampled twice, so each template is attempted 2 times.
planned_counts: eight 1’s: per-template slot counts (before replicates). With R=2, expect ~2 valid samples per template.
planned_imbalance_ratio: 1.0: the plan is perfectly balanced (each template gets the same number of slots).