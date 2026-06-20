# Investor-Demo Experience Audit

**Date:** 2026-06-20 · Lens: first-time investor / innovation-fund reviewer seeing ArthOS cold. Reviewed: Landing, Discover, Top Idea, Bull vs Bear, Recommendation Trace, Integrity Card, Reflection Loop, My Portfolio, Model Portfolios, Options Practice, Methodology. Scope of fixes: presentation / clarity / trust / demo quality only — no new features, data, models, or backend.

## Surface verdicts (investor-ready unless flagged)

- **Landing / onboarding** — honest, clear copy ("nothing real is at stake… we promise literacy"). **Weakness:** on desktop the hero sits top-left with ~60% empty viewport → reads unfinished. **P0.**
- **Discover** — strong masthead ("Ideas you can follow and prove"), real Buy top idea, plain-English plan. Investor-ready.
- **Top Idea / Briefing** — hero card + honest empty-desk ("Cash is the call"). Investor-ready.
- **Bull vs Bear / Recommendation Trace / Integrity Card / Reflection Loop** — polished last sprint; investor-ready.
- **My Portfolio** — clean "Practice portfolio", honest breakdown, "source: live". Investor-ready.
- **Model Portfolios** — clear thesis + track record + "Is this for me?". Minor wording ("flatters the past"). P1.
- **Methodology** — polished editorial, trust-positive. Investor-ready.
- **Options Practice** — user surfaces use options jargon (iron condor, DTE, delta/theta/IV) without inline definitions; the `/v2/options` **diagnostics** page is raw developer tooling (version strings, scheduler counts, observation_id). Diagnostics is NOT in primary nav (only reachable by direct URL), so not demo-reachable. P1.

## Per-page debug/unfinished leaks found

- **PickPage Fundamentals** (`PickPage.tsx:386-395`) — "Company fundamentals … are coming soon … stays empty until the data is wired in." Renders an empty "coming soon" section on **every** idea detail → unfinished-MVP signal. **P0.**
- **MentorProfile** (`MentorProfile.tsx:265-267`) — `ID: {pattern.rule_key}` raw developer metadata shown to users. **P0.**
- Honest empty-state pages — FieldNotes / Catalysts / Watchlist ("not yet connected"). Honest but read unfinished; not core demo surfaces. P1.
- No `console.log`, no `data-testid`, no fabricated metrics, no raw composite_score/snapshot_hash/engine_version rendered. Clean.

## Prioritized list

### P0 — must fix before investor meetings (presentation-only, implementing now)
1. Remove the PickPage "Fundamentals — coming soon" placeholder section.
2. Remove the raw `ID: {pattern.rule_key}` footer on MentorProfile pattern cards.
3. Balance the Landing hero so desktop no longer looks unfinished (centered/constrained, optional trust strip from existing copy).

### P1 — nice improvements
- Options jargon: inline plain-language definitions (iron condor, DTE, delta/theta/vega, IV, assignment, breakeven, POP).
- Guard/hide the `/v2/options` diagnostics route from users (not in nav today; keep out of demo).
- Model Portfolios wording: "flatters the past" → "overstates past returns"; add a one-line "$10,000 practice account to match real-world sizing" note.
- Hide or polish "not yet connected" secondary pages (FieldNotes / Catalysts / Watchlist) from nav during demo.
- Clarify market ticker when closed (currently "+0.00%" across the board reads as dead data).

### P2 — future work
- Wire real fundamentals data (then restore a real Fundamentals section).
- Options greeks education layer.
- Configurable practice starting capital.
- Simplify the day-P&L reconciliation copy on My Portfolio.

## Implementation note

Only P0 is implemented this sprint, each as a separate commit with before/after desktop + mobile screenshots.
