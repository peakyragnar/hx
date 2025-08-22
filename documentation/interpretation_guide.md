Here’s how to read that Auto‑RPL run and why it escalated.

Interpretation

- Final estimate: p_RPL≈0.312 with CI95=[0.268, 0.364] (width≈0.096). Uncertainty is reasonably tight.
- Stability: 0.413 (medium). This reflects paraphrase sensitivity (IQR of per‑template means) and is below the 0.70 gate.
- Balance: imbalance=1.00. The balanced sampler kept template counts equal; no bias from template overuse.

Gates by Stage

- Stage 1 (T=8,K=8,R=2): width=0.113 (passes ≤0.20), stability=0.201 (fails ≥0.70) → escalate.
- Stage 2 (T=16,K=16,R=2): width=0.103 (passes), stability=0.138 (fails) → escalate.
- Stage 3 (T=16,K=16,R=3): width=0.096 (passes), stability=0.413 (still below 0.70) → stop_limits (max stage reached).
What it means

- The CI width gate passed early, so uncertainty from decode noise is under control.
- Stability stayed below threshold even after doubling templates and adding replicates. That means the model’s belief varies meaningfully across
paraphrases (wording sensitivity), not that the estimate is numerically wild.
- The final p rose slightly across stages (0.289 → 0.300 → 0.312) as more templates/replicates were included, but remained in the same band; the robust
aggregator handled outliers.

Helpful follow‑ups

- Inspect paraphrase behavior: uv run heretix-rpl inspect --run runs/rpl_auto.json (prints per‑template means, IQR, counts). Look for templates with
notably higher/lower means driving the medium stability.
- If you need to proceed with this prior: report p and CI prominently and note “stability gate not met (medium; paraphrase‑sensitive)”.
- Re‑run later to check provider drift or prompt version effects; use monitor/summarize for weekly health checks.

Note on “is_stable”

- In single runs, aggregates.is_stable refers only to CI width ≤ 0.20. Auto‑RPL adds stricter gates (width, stability≥0.70, imbalance) for stage
decisions; that’s why it escalated despite the CI gate passing.