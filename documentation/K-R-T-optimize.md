# K/R/T Optimization Plan — Fast, Clear, Repeatable

This document shows exactly how to tune K, R, and T to reduce wall‑time and cost while keeping precision, agreement, and integrity strong. It assumes you use the same mixed cohort of claims (highly likely, highly unlikely, and 0.4–0.6) for every run.

## Goals
- Minimize wall‑time and network cost (K×R calls per claim).
- Keep cohort precision and integrity strong (gates below).
- Produce an “operating K/R/T” that all prompt A/Bs will use.

## Fixed Inputs (parity across tests)
- Cohort: the same claims file (e.g., `cohort/claims.txt`, 50 claims for iteration).
- Prompt version: keep constant while testing K/R/T (e.g., `rpl_g5_v2`).
- Model and decode: keep constant.
- Seed policy: set `HERETIX_RPL_SEED=42` (deterministic bootstrap decisions).
- Max output tokens: keep constant.
- DB routing: LIVE → `runs/heretix.sqlite`, MOCK → `runs/heretix_mock.sqlite` (automatic).

## What K, R, T Control
- `K` (slots): how many template slots we fill across `T` templates. More K → narrower CI, more calls.
- `R` (replicates): repeats per slot. More R → smoother per‑slot noise, diminishing returns beyond ~2–3.
- `T` (templates): how many paraphrases we include from the bank. Keep `T ≥ 5` so 20% trimming engages.

Balance rule (to keep counts equal): choose `K` as a multiple of `T` so the planned imbalance ratio ≈ 1.
- Planned imbalance ratio = ceil(K/T) ÷ floor(K/T). With `K=12, T=8` the planned ratio is 2 (expected).

## Gates (must pass on the cohort)
- Compliance (mean): ≥ 0.98
- Stability (median): ≥ 0.25
- CI width (median): ≤ 0.20 (≤ 0.10 is great)

Tie‑breakers: narrower median CI width → higher median Stability → higher median PQS → lower runtime.

## Test Grid (small, decisive)
Use your current prompt (v2) on the same 50‑claim cohort:

- Baseline (record only): your current K/R/T.
- Candidate A (balanced, faster): `K=16, R=2, T=8` (32 calls/claim, K multiple of T).
- Candidate B (very fast preview): `K=12, R=2, T=8` (24 calls/claim).

If you need one more point:
- Candidate C (tighter): `K=16, R=3, T=8` (48 calls/claim).

> Keep `T=8` unless you have template disagreement problems; then try `T=12` with `K=24` for balance.

## How To Run (one line each)
- Baseline (example):
  - `uv run python scripts/sweep.py --claims-file cohort/claims.txt --config runs/rpl_example.yaml --prompt-version rpl_g5_v2 --out-html runs/reports/cohort_v2_50_baseline.html`
- Candidate A:
  - Edit `runs/rpl_example.yaml` to `K: 16`, `R: 2`, `T: 8` (keep other knobs fixed).
  - Run the same command, change the output name (e.g., `cohort_v2_50_A.html`).
- Candidate B:
  - Set `K: 12`, `R: 2`, `T: 8` and run again → `cohort_v2_50_B.html`.
- Candidate C (optional):
  - Set `K: 16`, `R: 3`, `T: 8` → `cohort_v2_50_C.html`.

Open each HTML and write down: median CI width, median Stability, mean Compliance, and rough runtime.

## Decision
1) Apply gates. Drop any candidate that fails.
2) Among passing candidates, pick the fastest whose median CI width is within ~0.01–0.02 of Baseline.
3) If none are close enough, try `K=16, R=3, T=8`. If still not close, keep Baseline for “final” runs and use Candidate A for previews.

Freeze the winner as your **operating K/R/T**. Use it for all prompt A/Bs to isolate prompt effects.

## What To Check (when something looks off)
- CI width too wide:
  - Increase `K` or `R` a notch (prefer raising K), or increase `T` to include more paraphrases (then make K a multiple of the new T).
  - If the claim is very broad (“significantly”, no timeframe/region), accept that wider CIs reflect true uncertainty.
- Stability low:
  - If CI is tiny and p_RPL is near 0 or 1 → boundary effect; accept as benign.
  - Otherwise consider increasing `T` (and `K` to keep balance) or unifying/removing the few paraphrases that diverge (prompt change, separate task).
- Compliance < 0.98:
  - That’s a paraphrase issue (inviting sources or long outputs), not a K/R/T issue. Fix the template text, then re‑test.
- Imbalance ratio high:
  - Compare to the planned ratio (ceil(K/T)/floor(K/T)). If observed ≈ planned → OK. If much higher, some templates failed JSON/URL checks — tighten or exclude those templates.

## Runtime & Cost Estimate
- Calls per claim = `K × R`.
- Total calls = `N_claims × K × R`.
- Approx time (no concurrency) = `total calls × avg per‑call latency`.
  - Example (50 claims, A: K=16,R=2): 50×32=1600 calls. At ~1.5 s/call ≈ 40 minutes.
  - Baseline (K=18,R=3): 50×54=2700 calls → ~68 minutes.

> Bootstrap B runs on CPU and is negligible compared to network time. Keep `B=5000` for final; use `B=1000` only for quick previews.

## Keep Your Mix of Claims
- Do not filter out 0.4–0.6 claims. A stable 0.50 with tight CI is valuable: the model is consistently “on the fence.”
- Investigate only when width is wide or Stability is low without the boundary effect.

## After K/R/T Is Fixed
- Use the operating K/R/T for prompt A/B.
- Only revisit K/R/T if you have new runtime/cost constraints or the cohort profile changes materially.

## Quick Checklist (print‑and‑use)
- [ ] Same cohort, same prompt, same model, same seed policy
- [ ] Run Baseline, A, B (and C if needed)
- [ ] For each: write down median CI width, median Stability, mean Compliance, runtime
- [ ] Apply gates (Compliance ≥ 0.98; Stability ≥ 0.25; CI width ≤ 0.20)
- [ ] Pick the fastest passing config within ~0.01–0.02 width of Baseline
- [ ] Freeze as operating K/R/T and use for all prompt A/Bs

---

### Notes & Nuance
- Boundary effect: near p≈1 or p≈0, tiny Δp across templates becomes large logit spread; Stability can look low while CI is tiny. Accept as benign.
- Tuning T: Keep `T ≥ 5` so trimming engages. If you exclude weak paraphrases, adjust `K` to keep `K % T == 0` for balance.
- Caching: second runs of the same config should be much faster. If cache hit rate stays low, check for tiny config deltas (e.g., max_output_tokens).
- Concurrency: can cut wall‑time further, but add it after K/R/T is fixed (separate change).
