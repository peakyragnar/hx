# Front-End Next Steps

## Goals
- Give consumers a clear idea of what Heretix does in one glance.
- Minimize steps between landing on the site and running a claim.
- Keep advanced details available but optional so casual users are not overwhelmed.

## Page Flow Overview
1. **Landing / Home**: Explain the promise, show the product in action, invite the user to start a claim.
2. **Run in Progress**: Reassure the user while the system collects internal model responses.
3. **Result / Output**: Deliver a readable verdict with concise reasoning and clear re-entry points.
4. **Supporting Surfaces**: Provide lightweight learning and trust content without distracting from the main flow.

## Page Details

### Landing / Home
- **Hero Module**
  - Headline: "Understand the AI answering your questions."
  - Subtext: one sentence describing the Raw Prior Lens ("We ask GPT-5, with no web search, what it already believes about your claim.").
  - Primary action: inline claim input + "Test a claim" button.
- **Quick How-It-Works Strip**
  - Three steps (Ask → We query GPT-5 internally → You read why) with short tooltips or hover copy.
  - Optional 10-second looping demo/GIF of the run → result cycle.
- **Live Example / Social Proof**
  - Show a current or recent result card with percent, verdict, and two-sentence reasoning to anchor expectations.
  - Badges for "No retrieval", "Model: GPT-5", privacy reassurance.
- **FAQ Accordion (inline)**
  - Answer top 4 questions: "What does the percentage mean?", "Is this political?", "Does it store my claim?", "Where do explanations come from?"
  - Link to a full Learn page if more depth later.
- **Footer CTAs**
  - Persistent "Start a claim" button, minimal navigation (Home, Examples, Learn, Account if needed).

### Run in Progress
- **Claim Header**
  - Display the submitted claim verbatim with status tagline ("Checking how GPT-5 already feels about this...").
- **Progress Indicator**
  - Three friendly stages: "Planning the wordings", "Asking GPT-5", "Summarizing why".
  - Animated bar or checklist lighting up as stages complete.
- **Human-Friendly Narration**
  - Show sample count in plain language ("12 variations asked so far").
  - Provide optional "Show advanced details" toggle for enthusiasts displaying sampling counts/seed info.
- **Support Copy**
  - Reassure: "No web browsing, just internal knowledge"; note expected timing.

### Result / Output
- **Headline Verdict**
  - Large percent + textual verdict ("GPT-5 thinks this is likely false (11%).").
  - Single-sentence interpretation translating percent to plain English.
- **Reasoning Card**
  - 3–4 bullet explanations written for everyday users ("Why it leans this way").
  - Secondary button to expand advanced metrics (CI, stability) if desired.
- **Context Card**
  - Model + mode disclosure ("Model: GPT-5 · Mode: Internal knowledge only").
  - Sub copy about no retrieval / cached answers.
- **Next Actions**
  - Primary CTA: "Ask another claim".
  - Secondary: share/copy link, download PDF/JSON for enthusiasts.
  - Optional "Explore other examples" linking back to gallery.

### Supporting Surfaces
- **Examples Gallery**
  - Curated list of recent claims with verdicts to help new users understand outputs before submitting.
- **Learn Page (optional expansion)**
  - Longer-form explanation, product philosophy, data privacy, methodology blurb.
  - Link from footer and from FAQ accordion "See more".
  - Implemented as `/how.html` for a simple, consumer-friendly walkthrough.
- **Trust & Safety**
  - Persistent footer links: Privacy, Terms, Contact.
  - Mention content policy (no personal data, etc.).

## Next Steps Checklist
- [ ] Align copywriting tone with consumer audience (plain language, low jargon).
- [ ] Wireframe landing hero, progress screen, and result card using layout above.
- [ ] Draft FAQ answers and reasoning bullet templates.
- [ ] Define optional "advanced details" component for power users.
