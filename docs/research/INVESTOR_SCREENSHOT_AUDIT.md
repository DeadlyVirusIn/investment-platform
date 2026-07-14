# Investor Screenshot Audit

**Date:** 2026-06-20 · Task 3. Rank every screenshot-worthy surface: **A** = investor-presentation ready · **B** = acceptable · **C** = hurts credibility. Implement only A→A+ improvements. Captured on the seeded demo device (NAV ~$105K, 30 open, 62 resolved, +5.21%).

## Ranking

| Surface | Grade | Notes |
|---|---|---|
| Landing / onboarding | **A** | Centered hero + 3-up trust strip (this sprint). Clean first impression. |
| Discover | **A** | "Ideas you can follow and prove" masthead, real Buy top idea, plain plan. |
| Top Idea / Briefing | **A** | Hero card + honest empty-desk fallback. |
| Idea detail (Pick) | **A+** | Now leads with Why-now → Bull/Bear → caveat → holding → See-the-working. Dense with proof, all premium cards. |
| Bull vs Bear | **A+** | Bordered "vs" card, count pills, accented verdict — flagship screenshot. |
| Recommendation Trace | **A** | Clean audit trail in a container; plain adjustment labels. |
| Track Record Integrity Card | **A+** | Contained trust card, hero stats, honesty bands. Strong diligence shot. |
| Reflection Loop | **A** | Per-idea cards, accented "what we learned". |
| My Portfolio | **A** | "Practice portfolio", honest breakdown, source: live. |
| Model Portfolios | **A** | Thesis + track record + "Is this for me?". |
| Methodology + Workflow Diagram | **A+** | Workflow timeline (this sprint) makes the pipeline legible on one screen. |
| Options Setup Detail | **B** | Clean but options jargon (iron condor / DTE / greeks) undefined — P1, keep out of a beginner demo. |
| Options Visibility (`/v2/options`) | **C** (not in nav) | Raw diagnostics (version strings, scheduler counts). NOT reachable in guided demo; do not screenshot. |
| FieldNotes / Catalysts / Watchlist | **B** | Honest "not yet connected" empty states; fine but not demo highlights. |

## A→A+ improvements implemented this sprint

- **Idea detail / Bull-vs-Bear** → A+ via the new **Why-now** card (Task 1): the page now opens with a timeliness hook before the both-sides case.
- **Methodology** → A+ via the new **Workflow diagram** (Task 2): the end-to-end pipeline is now a single screenshot-worthy visual.

No further A→A+ *code* changes are warranted — the remaining A surfaces are already presentation-clean (polished in prior sprints), and gratuitous restyling would risk regressions for no investor gain.

## Keep out of the demo (credibility)

- `/v2/options` diagnostics (C) — direct-URL only, not in nav. Never screenshot.
- Options Practice detail (B) — only show if the investor asks; jargon undefined (P1).
- FieldNotes / Catalysts / Watchlist (B) — "not yet connected" reads unfinished; skip on the guided tour.

## Screenshot shot-list for the deck

Idea detail (Why-now + Bull/Bear) · Recommendation Trace (expanded) · Track Record Integrity Card · Reflection Loop · Methodology Workflow diagram · Landing trust strip · Discover top idea · My Portfolio. All verified at desktop (1440) and mobile (391).
