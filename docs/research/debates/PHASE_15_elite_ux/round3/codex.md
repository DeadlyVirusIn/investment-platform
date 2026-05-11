## 1. Final per-page scores

| # | Page | Final score | One-line justification |
|---|---|---:|---|
| 1 | /overview | 7.2 | Strong executive surface, but competing heroes, query-param variants, and repeated NAV/posture facts prevent a singular first read. |
| 2 | /events | 5.8 | Honest event component, but fetch failure can look empty and catalysts are not joined to active signal consequences. |
| 3 | /action-queue | 8.1 | Best product surface: skeleton, no-buys explanation, density, and action cards work; it still needs group rationale and better sort/change controls. |
| 4 | /signal-lab | 5.1 | ExpertDetails and readiness inputs are sound, but the uncalibrated score plus "Not yet wired" backtest block hurts trust. |
| 5 | /decisions | 6.7 | Calm card and audit story are strong, while dense legacy layout, narrow detail column, and mobile review flow keep it short of premium. |
| 6 | /strategies | 6.7 | Education collapse helped, but the page lacks a top active/blocked/eligible strategy answer. |
| 7 | /options/* | 4.7 | Deep and disciplined about paper-only boundaries, but 12 peer tabs, zinc/amber styling, drawers, and tables make it the largest IA/mobile liability. |
| 8 | /portfolio | 6.4 | Data truth is strong, but the route defaults to dense terminal while the premium brief view is URL-hidden. |
| 9 | /risk | 6.5 | Honest mark handling and table wrapping are good, but small bespoke controls and missing bottom journey CTA leave it legacy-feeling. |
| 10 | /research | 5.2 | Alpha Lab has a useful transparency concept, but static fallback rows and weak verdict framing are trust and clarity gaps. |
| 11 | /ops | 5.1 | Operational transparency exists, but hardcoded job statuses and 15+ ungrouped cards make it both untrustworthy and developer-built. |

## 2. Final elite-gap thesis

The single most important reason this is not yet a 9-10/10 elite product is that it shows truthful information without enough discipline about hierarchy, provenance, and the next meaningful decision. The app has the right primitives: PageChapter, NextStepCard, ExpertDetails, calm cards, density, paper-only boundaries, and canonical paper-summary discipline. But the user still feels build history: Options as a sub-app, Portfolio as terminal-first, legacy u-card pages beside picks-root pages, and a few static or silent states that undermine trust. Elite here means one clear answer per page, with raw detail available only when the user asks for it.

## 3. Final unanimous-or-strong-consensus findings

- ✓ Options 12-tab flat nav is the biggest IA/mobile failure and must be visually collapsed or grouped.
- ✓ Portfolio should expose a Brief / Working toggle and stop hiding the brief view behind `?view=brief`.
- ✓ Mixed design eras (picks-root, u-card/Tailwind, Options zinc, copilot tokens) make the product feel stitched together.
- ✓ Signal Lab's "Not yet wired" backtest block should not remain as a prominent production surface.
- ✓ Ops needs grouped/collapsible sections; the current card stack is not a premium operational page.
- ✓ Action Queue is the strongest current page, especially the no-buys explanation pattern.
- ◐ Static or silent truth risks are Phase 15 material: Ops `JobRow`, Research fallback rows, Events fetch swallow, and possibly Options guardrail toggle.
- ◐ Mobile shell work is real, but Options, PortfolioTerminal, Ops, and Decisions remain desktop-first inside the page body.
- ◐ PageChapter/NextStepCard are the correct narrative spine but adoption is incomplete.
- ◐ DensityToggle is over-deployed where it has little visible effect or must be made genuinely global.

## 4. Final disagreements that did NOT converge

- DensityToggle: one side says keep it visible as global preference; the other says hide inert controls. My final position: keep only where visible behavior exists in Phase 15, then make density genuinely global later.
- Overview launcher order: one side wants strict `page_flow.ts`; the other defends action-first executive reading. My final position: keep action-first order, but fix contradictory NextStep copy and reduce duplicated metrics.
- Header unification timing: one side wants a single PageChapter header now; the other wants narrower patches first. My final position: Phase 15 adds missing journey anchors without a broad header migration.
- Action Queue bulk actions: one side wants pro multi-select/keyboard power; the other worries about bypassing review discipline. My final position: add keyboard navigation and compare/pin later, not bulk execution.
- AI presence: one side proposes serif/ambient motion; the other rejects atmosphere. My final position: no serif and no fake liveness; use motion only on real state changes.

## 5. Phase 15 roadmap (next phase to ship)

1. **Fix Ops static job truth** — `apps/web/src/pages/Ops.tsx:263`; Effort: S; Regression risk: low; why 15 not 16: hardcoded "ok" is a trust violation.
2. **Label or hide Alpha Lab fallback registry** — `apps/web/src/pages/ResearchLab.tsx:84`; Effort: S; Regression risk: low; why 15 not 16: static rows must not look live.
3. **Restore Events fetch error visibility** — `apps/web/src/pages/EventsResearchPage.tsx:27`; Effort: S; Regression risk: low; why 15 not 16: failed data must not render as clean emptiness.
4. **Remove or collapse Signal Lab tombstone** — `apps/web/src/pages/SignalLabPage.tsx:170`; Effort: S; Regression risk: low; why 15 not 16: it is the most visible credibility leak on the page.
5. **Fix Options mobile nav presentation** — `apps/web/src/pages/options/OptionsLayout.tsx:48`; Effort: S/M; Regression risk: low; why 15 not 16: phones cannot start with a wrapped 12-route wall.
6. **Verify Options guardrail toggle** — `apps/web/src/pages/options/OptionsLayout.tsx:44`; Effort: S; Regression risk: low; why 15 not 16: a nonfunctional safety toggle would be worse than no toggle.
7. **Add Portfolio mode toggle** — `apps/web/src/pages/copilot/PortfolioRouteSwitch.tsx:17`; Effort: S; Regression risk: low; why 15 not 16: users need to discover brief vs terminal immediately.
8. **Flip Portfolio default to brief after QA** — `apps/web/src/pages/copilot/PortfolioRouteSwitch.tsx:20`; Effort: S; Regression risk: medium; why 15 not 16: current default hides the product's clearest novice portfolio story.
9. **Add Portfolio route narrative anchor** — `apps/web/src/pages/PortfolioTerminal.tsx:101` and `CopilotHoldings`; Effort: S/M; Regression risk: low; why 15 not 16: Portfolio currently breaks the PageChapter/NextStep journey.
10. **Add Risk/Research/Decisions bottom next-step CTAs where missing** — `RiskDashboard.tsx`, `ResearchLab.tsx`, `Decisions.tsx`; Effort: S; Regression risk: low; why 15 not 16: this completes the existing journey without redesign.
11. **Calibrate Signal Lab readiness** — `apps/web/src/pages/SignalLabPage.tsx:129`; Effort: S; Regression risk: low; why 15 not 16: a score without an interpretation band is novice-hostile.
12. **Remove off-tone Decisions empty emoji** — `apps/web/src/pages/Decisions.tsx:355`; Effort: S; Regression risk: low; why 15 not 16: decision audit pages need restrained tone.
13. **Fix small Risk controls** — `apps/web/src/pages/RiskDashboard.tsx:115`; Effort: S; Regression risk: low; why 15 not 16: "Explain this view" and replay controls are trust affordances, not polish.
14. **Make non-default Overview variants explicit** — `apps/web/src/pages/copilot/OverviewRouteSwitch.tsx:35`; Effort: S; Regression risk: low; why 15 not 16: alternate overview modes currently feel like product indecision.

## 6. Phase 16 roadmap (after Phase 15)

1. **Collapse Options IA to grouped sections while preserving deep links** — `OptionsLayout.tsx`; Effort: L; Regression risk: high; why 16 not 15: broader than the urgent mobile nav patch.
2. **Tokenize Options out of zinc/amber styling** — `apps/web/src/pages/options/*`; Effort: L; Regression risk: high; why 16 not 15: visual unification should follow truth/mobile fixes.
3. **Group Ops into collapsible super-sections** — `apps/web/src/pages/Ops.tsx:210`; Effort: M; Regression risk: medium; why 16 not 15: the honesty fix comes first, then structure.
4. **Add Events catalyst brief with affected symbols** — `EventsResearchPage.tsx` and `MarketEvents.tsx`; Effort: M; Regression risk: low; why 16 not 15: requires derived synthesis, not just error handling.
5. **Add Action Queue group rationale and changed/sort controls** — `ActionQueuePage.tsx`, `ActionQueue.tsx`; Effort: M; Regression risk: medium; why 16 not 15: high value, but not a truth blocker.
6. **Expand ExpertDetails to legacy advanced content** — Decisions, Risk, Research, Ops, Options diagnostics; Effort: M; Regression risk: medium; why 16 not 15: progressive disclosure should be systematic.
7. **Add top state panels** — Strategies active/blocked/eligible, Research verdict, Ops warnings-only; Effort: M; Regression risk: medium; why 16 not 15: requires product copy and derived states.
8. **Normalize table wrappers in PortfolioTerminal and Options** — table components across both areas; Effort: M; Regression risk: medium; why 16 not 15: important, but less urgent than route/default blockers.

## 7. Phase 17 roadmap (last phase)

1. **Unify the product design system** — picks-root, u-card, copilot, and Options tokens; Effort: XL; Regression risk: high; why 17 not 15: too broad for a trust-fix phase.
2. **Mobile-native deep-page IA** — Options, Decisions, PortfolioTerminal; Effort: XL; Regression risk: high; why 17 not 15: needs Phase 16 grouping first.
3. **Temporal "what changed" layer** — Overview, Events, Action Queue, Portfolio, Risk; Effort: L; Regression risk: medium; why 17 not 15: requires session/run comparison semantics.
4. **Scoped AI explanation affordance** — current-page drawer or inline "Why?" tied to real data; Effort: XL; Regression risk: high; why 17 not 15: must wait until provenance and stale-state gates are consistent.
5. **Single motion vocabulary** — CSS motion tokens tied only to real data changes; Effort: M; Regression risk: low; why 17 not 15: polish after hierarchy and truth are stable.

## 8. Final answer to the 12 brief questions

1. The app tells a partially coherent story because `page_flow.ts` is right, but incomplete adoption and sub-app detours fragment the lived path.
2. Navigation is intelligent in the shell and fragmented inside pages, especially Options, Alpha Lab, Decisions, and query-param modes.
3. The Overview to Risk journey is possible, but Options and Portfolio currently interrupt it with too many modes and too little route-level narration.
4. Events, Signal Lab, Alpha Lab, and Ops feel most passive or dead because they expose data/status without enough synthesis.
5. Collapse Signal Lab's backtest block, Decisions diagnostics, Risk full breakdowns, Research internals, Ops card groups, and Options advanced diagnostics.
6. Keep mobile sticky minimal; use sticky affordances mainly for desktop Options local nav, Decisions timeline, and warning filters.
7. The noisiest cards are PortfolioSnapshot secondary metrics, Options tabs/disclaimers, Ops card stacks, and Decisions chip rails.
8. The under-emphasized surfaces are Portfolio brief mode, Risk explanation, Research verdict, Events top catalyst, and Action Queue group rationale.
9. Wasted vertical space comes from Overview repeated first-fold framing, Signal Lab tombstone, Ops preamble/card stack, and repeated Options banners.
10. Options, PortfolioTerminal, Decisions detail, and Ops ML/engine sections are too dense.
11. Options fails mobile most clearly, followed by PortfolioTerminal, Ops, and Decisions review flow.
12. Options, Ops, Alpha Lab, Signal Lab's lower half, and pockets of Risk/Decisions still feel developer-built.

## 9. The one thing you would NOT change

Do not undo the PageChapter / NextStepCard narrative spine; incomplete adoption is the problem, not the motif itself.
