Great—let’s make this digestible and doable. You’ve got four goals:
	1.	Faster UX
	2.	Add other LLM providers (Gemini, Grok, Claude, DeepSeek)
	3.	Design for future RL/ML
	4.	Integrate Kalshi

You don’t need to do all at once. Here’s a clean sequence that keeps you oriented, with exact deliverables and “done” criteria. Anything marked (parallel‑able) can be given to your coding assistant while you work on the next step.

⸻

Phase 1 — Speed First (no new vendors yet)

Why first: Improves user experience immediately and reduces cost. No change to your math.

1.1 Instrumentation (baseline)
	•	Add timing & cost probes around: provider call, JSON validate, aggregation, bootstrap.
	•	Log tokens and $ estimate per run.
	•	Done when: A single run prints a timing & token table; totals ≈ sum of parts.

1.2 Concurrency
	•	Bounded thread pool for RPL/WEL work units, e.g. HERETIX_RPL_CONCURRENCY=8.
	•	Deterministic work list (seeded by claim|model|prompt_version) to keep reproducibility.
	•	Done when: Wall‑time scales down roughly 3–5× for K×R, with no rate‑limit errors.

1.3 Caching
	•	Raw replicate cache (per paraphrase×replicate) and aggregated run cache.
	•	Web snippet cache (short TTL: 15–60 min).
	•	Done when: Re‑running a claim shows high raw/agg cache hit rates in logs.

1.4 Fast‑then‑Final CI
	•	Return CI with B=1000 immediately; compute B=5000 in the background from the same logits.
	•	Done when: UI shows result fast; polling returns identical final CI for same seed.

⸻

Phase 2 — Provider Abstraction (add others safely)

Why second: Paves the road for Claude/Gemini/etc. without touching the math or UI.

2.1 Provider interface
	•	Define ProviderAdapter with call_rpl() and call_wel_scoring() returning your existing JSON shapes.
	•	Register GPT‑5 as the first adapter; keep it default.
	•	Done when: Swapping the registry list from [gpt5] to [gpt5] (same) changes nothing.

2.2 Add one new provider (Claude or Gemini)
	•	Implement adapter with timeouts, retries, max‑parallel.
	•	Feature‑flag it: PROVIDERS=openai,anthropic.
	•	Done when: A/B bench shows equivalent behavior within tolerances; cache keys include provider name.

(Parallel‑able with Phase 1.3/1.4 once the interface is defined.)

⸻

Phase 3 — RL/ML‑Ready Logging (no learning yet)

Why third: Capture the right data now so you can train later, without changing behavior.

3.1 “Fat row” per forecast run
	•	Add a row (Parquet or Postgres) with:
claim_id, timestamp, mode, provider, K,R,B, prior_p/CI, web_p/CI, combined_p/CI, w_web, web_evidence_counts (docs, domains), dispersion, recency_score, strength_score, tokens_in/out, cost_usd, seed, prompt_version, knobset_json, policy_version
	•	Done when: Each run writes one self‑contained record you can query without scraping logs.

3.2 RL trace table (optional now)
	•	state_json, action, reward, policy_version. Reward can be empty for now.
	•	Done when: Schema exists and is written (reward NULL).

(Parallel‑able with Phase 2.2.)

⸻

Phase 4 — Kalshi (read‑only first)

Why fourth: Lets you see edges without the complexity of placing orders. You can trade manually.

4.1 Market data ingest
	•	Add a markets table and quotes table (market_id, symbol, bid/ask/mid, updated_at).
	•	Build read‑only Kalshi client (or simple cron job) to fetch current quotes for markets you care about.
	•	Done when: You can fetch & store bids/mids on a schedule; a simple screen shows “Combined p vs market p (mid)” and the edge.

4.2 Claim↔Market linking
	•	A small mapping table claim_id ↔ market_id with a “resolution function” hint (Y/N binary, or threshold if needed).
	•	Done when: A run result can display “Market: 0.62, Ours: 0.48, Edge: −0.14”.

(Polymarket can come later via the same adapter shape.)

⸻

What you can run in parallel (if you want to leverage Codex/cloud workers)
	•	Parallel A: While you add concurrency/caching (Phase 1), your assistant can stub the ProviderAdapter and port GPT‑5 into it (Phase 2.1).
	•	Parallel B: While you do Kalshi read‑only (Phase 4), your assistant can wire fat‑row logging (Phase 3.1) and the RL trace schema (3.2).

Keep merges small: one PR per phase step, each with a tiny “Define of Done”.

⸻

The minimal data model to support all goals

(You already have checks—extend, don’t replace)
	•	checks (each user run)
id, user_id, claim_text, mode, provider_set, K,R,B, prior_p, prior_ci_lo/hi, web_p, web_ci_lo/hi, combined_p, combined_ci_lo/hi, w_web, docs_count, domains_count, dispersion, recency_score, strength_score, tokens_in, tokens_out, cost_usd, seed, prompt_version, created_at
	•	forecast_runs (parquet or postgres) — copy of the “fat row” above (for analytics/RL).
	•	markets — market_id, venue (kalshi|polymarket), question, type, settlement_rules
	•	market_quotes — market_id, ts, bid, ask, mid
	•	claim_market_link — claim_id, market_id, mapping_notes
	•	rl_traces (later) — run_id, state_json, action, reward, policy_version

This keeps user‑facing ops in Postgres while giving you an analytics table that’s perfect for ML/RL later.

⸻

Simple UI/UX changes (keep it minimal)
	•	Mode buttons: Baseline (Model Only) and Web‑Informed.
	•	Baseline shows prior only.
	•	Web‑Informed shows prior | web | combined + Bias gap.
	•	When Kalshi is available: show Market vs Ours with edge.

⸻

Default budgets (fast & predictable)
	•	Baseline (RPL): K=8, R=2, fast CI→final CI
	•	Web‑Informed (WEL): 12–20 docs, 2 reps, then fuse with RPL (same K,R).
	•	Keep these static until you profile; avoid auto‑escalation while you’re adding providers.

⸻

“Why this order?”
	•	Phase 1 makes everything cheaper/faster (users feel it immediately).
	•	Phase 2 unblocks new models without refactors later.
	•	Phase 3 ensures you’re collecting the data you’ll need for RL—no rework.
	•	Phase 4 closes the loop with real market prices, so you can see edge and decide on next investments.

⸻

Crisp “Define of Done” checklist
	•	A single run prints timings & tokens; CI fast→final without extra provider calls.
	•	Concurrency on; caches in place; reproducible seeds.
	•	ProviderAdapter wired; GPT‑5 works via adapter; 2nd provider behind a flag.
	•	Each run emits a fat row suitable for ML/RL later.
	•	Kalshi quotes stored; screen shows Market vs Ours vs Edge.

When those are green, you’re ready to: (a) flip on an additional provider to A/B; (b) start collecting RL trajectories; (c) later, automate bet sizing.

If you want, I can turn this into a ticket list (one per bullet) with suggested file paths and stub signatures your coding assistant can fill in.