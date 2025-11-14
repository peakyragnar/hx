# Output Review Guide — Heretix RPL (Simple, Click‑First)

This guide tells you, step by step, how to review results and know what to do next. It uses the HTML reports you already generate and plain actions in your DB viewer. No SQL or scripts required.

## What You Open First
- Cohort summary (one prompt version): `runs/reports/cohort_<version>.html`
- A/B compare (two prompt versions on the same claim): `runs/reports/ab.html`
- Per‑run report (one claim, deepest details): `runs/report.html`
- DB (optional): open `runs/heretix.sqlite` in DB Browser for SQLite to sort columns or inspect rows if needed.

## The Order To Review (Most Important → Support)

1) Precision (CI width)
- What it is: the 95% confidence interval width for p_RPL, in probability space.
- Where to see it: in every report row ("Width") and in the per‑run "Aggregates" block.
- How to read it:
  - Excellent: ≤ 0.10
  - Good: ≤ 0.20
  - Acceptable: ≤ 0.30
  - Action if wide: see Investigation Steps below — check template agreement and claim ambiguity. Consider raising K/T, unifying paraphrases, or clarifying the claim.

2) Template Agreement (Stability)
- What it is: how much the paraphrase templates agree (computed from the spread of per‑template means in logit space).
- Where: shown as "Stability" in reports; cohort summary shows median Stability.
- How to read it (rule of thumb):
  - High (≥ 0.35): strong agreement
  - OK (0.25–0.35): acceptable agreement
  - Low (< 0.25): review this claim (see Investigation Steps)
- Important nuance: near‑certain truths (p_RPL very close to 0 or 1) can show low Stability even when CI width is tiny. That’s the "boundary effect". Treat those as benign if CI is tight and all template means are extreme in the same direction.

3) Integrity (Compliance)
- What it is: fraction of attempted samples that produced strict JSON and no URLs/citations.
- Where: "Compliance" in reports; cohort summary shows mean Compliance.
- How to read it:
  - Goal: ≥ 0.98 (99%+ is common with the current prompt)
  - If lower: some templates invite sourcing or break JSON — see Investigation Steps (fix wording or drop the offending paraphrase(s)).

4) Probability (p_RPL)
- What it is: the aggregated prior the model assigns to the claim being true, after robust aggregation across templates.
- Where: "p_RPL" in every row.
- How to read it:
  - Use with CI width. A high p_RPL with a wide CI means uncertainty remains; a high p_RPL with a tiny CI is strong evidence of consensus.

5) PQS (Prompt Quality Score)
- What it is: a 0–100 summary of precision + stability + integrity. It helps rank prompts/runs after gates are met.
- Where: shown in A/B and per‑run reports; stored in the DB.
- How to read it: higher is better (≥ 65 is solid). Use after you’ve checked the gates above.

6) Supporting Diagnostics
- Counts by template ("counts_by_template"): confirms how many valid samples each paraphrase contributed to aggregation. Use the per‑run report’s table to see per‑template counts and means at a glance.
- Imbalance ratio ("imbalance_ratio"): how uneven the valid sample counts are across templates (max count ÷ min count). 
  - How to read it: ≈1 is ideal; ≤1.3 is fine; >1.5 needs a look.
  - What to do if high: check which templates had fewer valid samples (often due to JSON/URL failures). Tighten those paraphrases or temporarily reduce T so only reliable templates are included; you can also raise K to smooth division across T.
- Template IQR ("template_iqr_logit"): the inter‑quartile range of per‑template mean logits; Stability is a calibrated transform of this value.
  - How to read it: smaller is better. 
    • IQR_logit ≤ 0.2 → very consistent templates (high Stability)
    • 0.2–0.6 → moderate agreement
    • > 0.6 → low agreement (review templates)
  - Important nuance: near p≈0 or p≈1, tiny probability differences become large logit differences. If CI is tiny and all template means are extreme, a large IQR_logit can be a benign boundary effect.
- Cache hit rate: high on re‑runs; close to 0 on the first run. Good for confirming cached reuse.
- Prompt char length (prompt_char_len_max): ensure under your configured cap.
- Provenance: prompt_version, provider model id, bootstrap seed, template hashes.

---

## Investigation Steps (When Something Looks Off)

A) CI width is wider than you expect (precision issue)
1. Open the per‑run report for the claim (`runs/report.html`).
2. Look at "Per‑Template Stats": do most templates cluster together, or do some sit clearly lower/higher?
3. If a few templates diverge:
   - Unify their wording to match the rest (keep concise “estimate P(true)” phrasing), or temporarily exclude them by reducing T.
   - Re‑run the same claim and check that Stability rises and CI width narrows.
4. If all templates are clustered but the claim is broad/ambiguous (“significantly”, no timeframe/region): accept the wider CI as true uncertainty (or test a more specific claim in your cohort).

B) Stability is low
1. Check CI width first:
   - If CI is tiny and p_RPL is near 0 or 1, and all template means in "Per‑Template Stats" are extreme in the same direction → boundary effect; accept as benign.
   - If CI is not tiny, continue.
2. In "Per‑Template Stats", identify the lowest/highest templates:
   - If one or two paraphrases are repeatedly lowest across similar claims in the cohort, rewrite or drop those.
   - Keep changes minimal; re‑run A/B on the same claim to confirm improvement.

C) Compliance dips below 0.98
1. Per‑run report → "Integrity" block: confirm how many attempts were valid vs attempted.
2. Understand behavior: the harness never lets bad outputs skew p_RPL — non‑JSON/URL samples are marked invalid and excluded. Compliance drops because attempted includes them while valid does not.
3. Check "Per‑Template Stats": if invalids cluster in a few templates, valid counts for those will be lower, and imbalance_ratio may rise above the planned level. If invalids are uniform, imbalance may not move.
4. Read the lowest‑performing paraphrases’ text (prompt YAML or the prompts table): look for wording that invites sourcing ("according to", "cite") or long outputs that risk JSON breakage.
5. Tighten wording or drop that paraphrase. Re‑run to confirm Compliance ≥ 0.98 and imbalance returns to the planned level (given your K/T).

D) Prompt length exceeds cap
1. Per‑run report shows `prompt_char_len_max`.
2. If over cap: either raise the cap in your config or shorten system/user/paraphrase text (prefer brevity).

---

## A/B Decision (Which Prompt Version Wins?)
Use `runs/reports/ab.html` for a single‑claim comparison.
- Gates (must pass for both):
  - Compliance ≥ 0.98
  - Stability ≥ 0.25
  - CI width ≤ 0.30 (≤ 0.20 preferred)
- Winner rule:
  1) Narrower CI width
  2) Higher Stability
  3) Higher PQS
  4) Shorter prompt (if still tied)
- "What changed?" section shows exactly which prompt text or config knobs differ.

## Cohort Decision (Does it Generalize?)
Use `runs/reports/cohort_<version>.html` and the cohort compare page.
- Look at:
  - Median CI width (lower is better)
  - Median Stability (higher is better)
  - Mean Compliance (≥ 0.98)
  - Median PQS (higher is better)
- Accept a new prompt if:
  - All gates pass at the cohort level, and
  - Median CI width improves by a meaningful margin (e.g., ≥ 0.01), and
  - No material drop in Compliance.

---

## What Each Metric Means (Why It Exists)
- p_RPL: the belief (used for decisions). Aggregated probability after robust template weighting.
- CI95 & CI width: the uncertainty around p_RPL. You can’t trust a point estimate without its width.
- Stability score: template agreement. Flags paraphrase‑driven variance you might want to fix.
- Compliance rate: integrity guard. Ensures the prior is measured without retrieval/URLs and with strict JSON.
- PQS: a compact quality rank once gates pass (precision + stability + integrity together).
- Counts by template & imbalance ratio: confirms we achieved balanced sampling across paraphrases — important to avoid bias.
- Cache hit rate: operations signal. High on re‑runs means you’re saving cost/time correctly.
- Prompt char length: guardrail to keep prompts efficient and consistent.
- Seeds & provenance: auditability. Same inputs → same bootstrap decisions; easy to trace what ran.

---

## Practical Tips
- Use the per‑run HTML first — it already shows per‑template stats and integrity; only open the DB if you want to sort/filter rows.
- Don’t chase single‑claim noise: edit paraphrases only when they underperform across many similar claims.
- Keep prompts lean and consistent; push uncertainty into the JSON fields (belief.prob_true near 0.50, uncertainties/flags) — not into long instructions.
- Raise K/T for precision, unify/drop outlier paraphrases for stability, and keep Compliance ≥ 0.98.

This process keeps reviews fast and decisions auditably boring: check precision, check agreement, confirm integrity, and only tune what systematically drifts.
