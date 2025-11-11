# Optimizing and Simplifying the Output: Design Guide

This document explains the design choices and operating principles behind the new “Simple View” explanation, how it fits with Deeper and Advanced sections, and how we iterate toward consistently clear outputs for any claim.

The goal is durable clarity: a short, coherent explanation every time, no stitched snippets, and a single source of truth. The UI renders; the backend thinks.

---

## Objectives

- Coherent by default: Simple View reads like a short rationale, not a list of fragments.
- Single ownership: the backend composes the Simple View; the UI only renders it.
- Clean and non‑technical: no brands/domains/URLs/numbers in Simple View.
- Separation of concerns:
  - Simple View: 2–3 content sentences + 1 final summary (verdict tie‑in)
  - Deeper: structured reasoning and “Sources: …” (friendly names)
  - Advanced: technicals (prior/web %, weights, CI, doc/domain counts, recency)
  - Resolved: only Resolved Fact + Advanced; hide Simple/Deeper
- Deterministic and testable: same inputs → same Simple View; easy to validate.

---

## Architecture Overview

- Backend (source of truth):
  - Composer: `heretix/simple_expl.py` produces `simple_expl = {title, lines, summary}`.
  - Sanitizer: strips brands/domains/URLs/HTML entities; normalizes punctuation; softens distracting numerics.
  - Pipeline: attaches `simple_expl` to run JSON (skips for `resolved=true`).
- UI (SSR + SPA):
  - Prefer `simple_expl` from the backend; render `title`, each `lines[i]`, then `summary` last.
  - If `resolved=true`: hide Simple/Deeper; show only Resolved Fact + Advanced.
  - Fallback: SPA has a local composer only as a last resort; will be removed once the backend is stable.

---

## Output Layers

- Simple View (reader‑first):
  - 2–3 content sentences + 1 summary sentence; summary always last.
  - No domains, brands, URLs, or numeric weights.
  - No references to “model/sources/weights”; no stitched bullets.
- Deeper Explanation:
  - 2–4 structured reasoning points and a one‑line “Sources: Name, Name, Name”.
  - Friendly source names (no raw domains); no numeric weights.
- Advanced Details:
  - Combined %, CI and width; prior/web %, weights (w_web/recency/strength), doc/domain counts, recency metrics, dispersion.
  - Collapsed by default; for power users and QA only.
- Resolved Fact (`resolved=true`):
  - Only the resolved card (quote‑backed); Simple/Deeper are suppressed.
  - Advanced can still show technicals.

---

## The Composer (Backend)

A generic skeleton is used for every claim. We do not hand‑code topic templates. The composer draws from:
- Claim frame (actor, action, object, timeframe, quantifiers) — via the claim text.
- Evidence gist (direction, decisiveness, constraint) — via sanitized WEL replicate bullets.

Composition steps:
1) Bar to clear (sentence 1)
   - What would have to be true for the claim to hold, optionally by the stated timeframe.
   - Examples: “A ban would require formal approval by the owners…”, “Reaching 50% by 2026 would need rapid build‑out of…”.
2) Evidence gist (sentence 2)
   - Neutral synthesis: what recent reporting says and how decisive it is.
   - Examples: “Recent reporting describes debate and expectations of a vote, not a finalized decision.”, “Reporting notes projects are starting, not yet at scale.”
3) Key constraint (sentence 3)
   - The most salient missing prerequisite (approvals; capacity/supply; lease/contracts; timelines; supply‑chain/bottlenecks; regulatory/permits). One crisp line.
   - Example: “This still depends on formal approval and signed agreements.”
4) Summary (last sentence)
   - Verdict tie‑in only: “Taken together, these points suggest the claim is likely true/false/uncertain.”
   - No stance/weights/numbers.

Notes:
- If claim parsing lacks a timeframe/quantifier, omit it; still produce 2–3 sentences.
- If evidence is sparse, produce a concise neutral gist (“reporting discusses X; formal decisions are not cited”).
- Exactly 3 content sentences max; never more. Summary always last.

---

## Sanitization Rules

Applied uniformly in the backend before assembling lines:
- Remove: `domain.tld:` prefixes; `BrandName:` prefixes; “BrandName reports/says…” constructions.
- Remove bracketed/parenthetical source hints (e.g., `(source.com)`, `[source.com]`).
- Replace heavy numerics (`$`, `3T/4T`, raw large counts) with qualitative phrasing (e.g., “a high value”, “a large figure”) unless intrinsic to the bar (e.g., “50% by 2026”).
- Normalize punctuation and entities; ensure sentences end with a period.

---

## UI Contract

- Run JSON includes:
  ```json
  {
    "runs": [
      {
        "simple_expl": {
          "title": "Why the web‑informed verdict looks this way",
          "lines": ["…", "…", "…"],
          "summary": "Taken together, … likely false."
        },
        "resolved": false
      }
    ]
  }
  ```
- UI renders `simple_expl` verbatim; does not compose or add stance lines.
- For `resolved=true`, UI hides Simple/Deeper; renders only Resolved Fact + Advanced.

---

## Iteration and QA

- Minimal test harness (recommended):
  - Feed ~20 varied claims (ban, %‑by‑year, valuation‑by‑year, cost impact, relocation, outsell‑by‑year, generic) with synthetic replicates.
  - Assert:
    - `1 ≤ len(lines) ≤ 3` and `summary` present
    - No brands/domains/URLs in lines
    - No percents/$ in lines (except when from the claim frame)
    - `summary` is last; no duplicate lines
- Telemetry (optional): log which cues were used (evidence gist, chosen constraint) for internal QA.

Why tests help: they do not lock in content — they enforce structure and cleanliness so Simple stays readable as we refine phrasing.

---

## Rollout Plan

1) Backend produces `simple_expl`; UI prefers it (done).
2) Validate manually across a battery of claims; remove the SPA fallback composer.
3) (Optional) Add the small backend test harness to prevent regressions.
4) Expand constraint vocabulary incrementally (e.g., approvals → capacity → contracts → timelines → supply‑chain) based on real claims.
5) Document the `simple_expl` contract in the README or API docs.

---

## Troubleshooting

- Simple View shows domains/brands: sanitizer not applied or a UI path bypassed the backend. Ensure UI uses `simple_expl` and does not stitch replicate bullets.
- Summary not last / duplicated: verify UI does not append a second “summary” and that the backend caps content lines to three before adding summary.
- Resolved claim shows Simple View: ensure `resolved=true` is checked and Simple/Deeper are suppressed.
- Feels generic: add a constraint cue driven by actual replicate signals (e.g., approvals or capacity) without introducing topic templates.

---

## FAQ

- Why no numbers or sources in Simple View?
  - The goal is quick understanding without cognitive load; numbers/sources live in Advanced/Deeper.
- Is this approach “template‑based”?
  - No. It’s a generic skeleton (bar → gist → constraint → summary). It uses signal cues from evidence, not topic templates.
- What if a claim is oddly phrased?
  - The composer still falls back to a neutral gist (“reporting discusses X; decisions not cited”) + summary. Deeper shows details; Advanced shows numbers.

---

## Example (illustrative)

Claim: “The NFL will move the Jacksonville Jaguars to London in 2027.”

Simple View (example):
- A permanent relocation would require league approval and finalized stadium/lease arrangements; doing this by 2027 is a tight window.
- Recent reporting centers on expanded London games and international strategy, not a formal relocation decision.
- Ongoing stadium renovation and local commitments suggest the Jaguars remain in Jacksonville in the near term.
- Taken together, these points suggest the claim is likely false.

Deeper: list quotes and friendly source names (e.g., team statements, league reporting).
Advanced: prior/web %, CI, doc counts, weight, recency.

---

## Bottom Line

- The backend composes one short narrative. The UI renders it.
- Simple View is always clean, always summary‑last, and never a stitched set of snippets.
- Deeper carries sources; Advanced carries numbers. Resolved shows only the resolved card.
- Small, incremental improvements to the composer (constraint cues and phrasing) raise quality without fragmenting logic or adding topic‑specific template debt.

