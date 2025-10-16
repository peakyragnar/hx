# Web-Informed Lens (WEL) Structure Guide

This document explains how the Web-Informed Lens works end-to-end after the latest upgrades. It covers the main modules, how they interact, where resolution happens, and how results propagate to the API/UI.

---

## 1. Overview

WEL augments the Raw Prior Lens (RPL) by pulling web evidence, adjudicating each source, and blending it (or short-circuiting it) with the model’s prior. The current stack adds:

- **Publish date enrichment** for each snippet.
- **Resolved fact engine** that can deliver 0/1 outcomes with citations when consensus is clear.
- **Fusion short-circuiting** so resolved outcomes aren’t diluted by the prior.

---

## 2. Module Map

| Module | Purpose |
|--------|---------|
| `heretix_wel/providers/tavily.py` | Fetch top documents (URL, title, snippet). |
| `heretix_wel/date_extract.py` | Download page HTML, extract publish dates (JSON-LD, OpenGraph, `<time>`, URL patterns, body heuristics, headers), and cache a trimmed article body (`Doc.page_text`) for downstream use. Provides confidence scores. |
| `heretix_wel/claim_parse.py` | Lightweight parser to classify relation families (identity, event outcome, etc.) and detect time sensitivity. |
| `heretix_wel/doc_verdict.py` | Runs a quote-required LLM prompt to classify each document’s stance and extract a supporting quote/value. |
| `heretix_wel/resolved_engine.py` | Weights evidence and decides whether the claim is resolved. Returns truth, support/contradict scores, and citations. |
| `heretix_wel/evaluate_wel.py` | Orchestrates retrieval, enrichment, resolution, and (if unresolved) probabilistic sampling. |
| `heretix_api/routes_checks.py` | Calls `evaluate_wel`, builds the API-ready web block (including resolution metadata), and fuses with the prior. |
| `heretix_api/fuse.py` | Applies the short-circuit: if resolved, combined result = web; otherwise blend prior and web using weights. |
| `api/schemas.py` | Exposes resolution fields in the API response. |
| `ui/serve.py` | Local harness: same short-circuit logic and extra UI text for resolved runs. |
| `ui/results.html` | Displays a “Resolved Fact” block with citations when applicable. |
| `heretix/db/models.py` + `db/migrations/V004_add_resolved_columns.sql` | Persist resolution flags, support, citations, and confidence metrics. |

---

## 3. Execution Flow

1. **Fetch & Deduplicate**  
   `evaluate_wel` retrieves documents (`k_docs`), dedupes by URL, and caps per domain.

2. **Enrich Publish Dates**  
   `enrich_docs_with_publish_dates` downloads each page, extracts timestamps (JSON-LD → OG → `<time>` → URL → body heuristics → headers).  
   Stores `published_at`, detection method, confidence (0–1), and a trimmed `page_text` (used by the resolver).

3. **Claim Classification**  
   `parse_claim` identifies relation family, explicit years, and time stance (future/past, present). Used by the resolver to decide if the claim should be resolvable today.

4. **Attempt Resolution**  
   - `try_resolve_fact` runs per-doc quote-required prompts (`evaluate_doc`) on the cached article text (`page_text` fallback to snippet/title).
   - Each doc returns `stance` (support/contradict/unclear), a verbatim quote, and field/value.
   - Votes are weighted (domain weight + recency + quote bonus).
   - If support ≥ 2.0, contradict ≤ 0.5, and ≥ 2 distinct domains → Resolved True.  
     If contradict ≥ 2.0, support ≤ 0.5, and ≥ 2 distinct domains → Resolved False.  
     Else unresolved (falls back).
   - Collects citations (URL, domain, quote, stance, weight, publish date).

5. **Resolved Path (short-circuit)**  
   - If resolved, `evaluate_wel` returns `p ≈ 0.999` (true) or `0.001` (false), no bootstrap, and metrics including support/contradict totals, domain count, citation list, date confidence metrics.  
   - `fuse_prior_web` detects `resolved=True` and returns combined = web, weights = 1.0.  
   - Raw prior remains in the response for bias visibility but is not fused.

6. **Probabilistic Path**  
   - If unresolved, WEL runs the standard replicate sampling, LLM scoring, and logit aggregation.  
   - Metrics include `median_age_days`, `n_confident_dates`, `date_confident_rate`, etc.

7. **Persistence**  
   `api/main.py` writes:
   - Prior statistics.
   - Web statistics (docs, domains, recency, etc.).
   - Combined probability & CI.
   - Weight diagnostics.
   - Resolution fields (`resolved_flag`, `resolved_truth`, `resolved_reason`, `support/contradict`, `citations` JSON).

8. **API Response**  
   - `web` block: probability, CI, evidence metrics, resolved metadata.
   - `combined` block: probability & CI; if resolved, contains citations and reason.
   - `weights`: If resolved → `{w_web:1}`; else standard recency/strength weight.
   - `provenance`: includes WEL seed & config.

9. **UI Rendering**  
   - Baseline prior always shown.
   - Unresolved: “Combined probability blends…” with web stats.
   - Resolved: “Resolved by consensus”, `Resolved Fact` badge with top 2–3 quotes/domains, listing of support/contradict scores, no averaging with the prior.

---

## 4. Data Fields (Post-Migration)

`checks` table now contains:

| Column | Description |
|--------|-------------|
| `p_prior`, `ci_prior_lo`, `ci_prior_hi`, `stability_prior` | Raw Prior summary. |
| `p_web`, `ci_web_lo`, `ci_web_hi`, `n_docs`, `n_domains`, `median_age_days`, `web_dispersion`, `json_valid_rate`, `date_confident_rate`, `n_confident_dates` | Web evidence stats. |
| `p_combined`, `ci_combined_lo`, `ci_combined_hi` | Final outcome. |
| `w_web`, `recency_score`, `strength_score` | Fusion diagnostics. |
| `resolved_flag`, `resolved_truth`, `resolved_reason` | Resolution state. |
| `resolved_support`, `resolved_contradict`, `resolved_domains` | Consensus weights. |
| `resolved_citations` | JSON array of citations (URL, domain, quote, stance, value, weight, published_at). |

SQLite UI DB mirrors the relevant fields.

---

## 5. Usage Notes

- **Timeouts**: HTML fetches default to 6 s per doc (configurable via `WEL_FETCH_TIMEOUT`).
- **Confidence threshold**: median recency uses only docs with `published_confidence ≥ 0.5`; fallback is the retrieval window (`recency_days`) when none are available.
- **Resolution thresholds**: set in `heretix_wel/resolved_engine.py` (`THRESH_SUPPORT = 2.0`, `THRESH_OPPOSE = 0.5`, `MIN_DISTINCT_DOMAINS = 2`). Adjust there if you need stricter consensus.
- **Unresolved fallback**: WEL still returns probabilistic estimates when evidence is mixed or insufficient. Fusion weight falls back to recency/strength blend.
- **UI**: When resolved, the prior is still shown for context, but the top-line verdict is derived entirely from the consensus.

---

This guide should give you a clear view of how WEL now operates, from retrieval to API/UI. For tweaks—domain weights, consensus thresholds, query templates—look in `resolved_engine.py`, `claim_parse.py`, and `routes_checks.py`. For UI text adjustments, see `ui/serve.py` and `ui/results.html`.
