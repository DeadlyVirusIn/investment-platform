# Phase 15 Elite UX Debate - Round 2 - Codex

## 1. Convergence

All four Round 1 audits agree on the important shape of the product.

First, the product is materially better than Phase 12, especially where the newer picks-root surfaces are in control: Overview, Action Queue, Events, Signal Lab, and Strategies all have stronger narrative scaffolding than the legacy pages. PageChapter, NextStepCard, FetchError, DensityToggle, ExpertDetails, calm cards, and honest paper-trading disclaimers are the right primitives.

Second, Action Queue is the strongest execution surface. Every panelist called out the "Why no buys?" panel and skeleton as unusually good product UX. We differ on its exact score, but not on the fact that it is closest to premium.

Third, Options is the biggest IA and mobile liability. Twelve peer routes are not a premium navigation model, and `OptionsLayout.tsx:19-32` confirms the flat tab list. The nav wraps with `flex-wrap` at `OptionsLayout.tsx:48`, so this is not just theoretical: on phones, the first interaction inside Options becomes a wall of route choices.

Fourth, the app still has mixed product eras. Picks-root, u-card/Tailwind legacy pages, copilot tokens, and Options zinc-heavy screens create visible discontinuity. This is not a color-polish issue; it affects trust because the user feels the product switching dialects between serious financial contexts.

Fifth, mobile is improved at the shell level but not solved in the deep surfaces. Shell drawer, TopStrip sticky relaxation, ticker compression, and tap-target work matter, but Options, PortfolioTerminal, Ops, and Decisions still carry desktop-first information architecture.

Sixth, the biggest elite gap is not missing decoration. It is hierarchy, progressive disclosure, and "what changed / what matters next" synthesis derived from real data.

## 2. Divergence and My Position

The biggest disagreement is whether Phase 15 should focus on broad visual unification or targeted trust/mobile fixes first. I take the targeted position. A single design language matters, but it is too broad for the next move. The first Phase 15 work should remove truth risks and mobile blockers with narrow, testable patches: Events error handling, Ops hardcoded jobs, Research fallback labeling, Portfolio view discoverability, and Options mobile navigation.

I disagree with Gemini's P0 on FilterBar keyboard behavior. That critique appears stale. The current implementation explicitly converted the control away from fake tabs to a button group: `role="group"` at `apps/web/src/components/picks/FilterBar.tsx:45`, `aria-label` at `:46`, and `aria-pressed` on each button at `:52`. It is not an arrow-key tablist, and it should not pretend to be one.

I also disagree with Opus's push for a single PageChapter-first header migration in Phase 15. The critique is correct, but the sequencing is too risky. Header unification across Decisions, Risk, Portfolio, Ops, Research, and Options would touch many pages at once. Phase 15 should instead apply PageChapter/NextStep where missing and reduce duplicate heroes only on Overview, where the confusion is most visible.

I agree with Sonnet and Opus more than my own Round 1 on truth debt. I underweighted the severity of silent or static states. `EventsResearchPage.tsx:27` still swallows fetch errors and clears loading; `Ops.tsx:263-266` still renders scheduled job rows with literal `"ok"` / `"skipped"` props; `ResearchLab.tsx:84-128` still replaces an empty shadow registry with static known signals. Those are more urgent than visual tokenization.

## 3. Concessions

Opus was right that Ops has a P0 honesty issue. My Round 1 treated Ops primarily as card sprawl. The hardcoded `JobRow` values at `apps/web/src/pages/Ops.tsx:263-266` are worse than clutter because they can display "ok" independent of live scheduler truth.

Opus was also right that Research's fallback registry deserves a trust fix. I noted Alpha Lab felt developer-built but did not call out that `ResearchLab.tsx:128` silently chooses `knownSignals` when `shadow` is empty. Because those rows render inside the same "Shadow Signal Registry" card at `ResearchLab.tsx:132-135`, the fallback needs an explicit static-baseline label or a true empty state.

Sonnet was right that the Decisions empty filter includes an emoji at `apps/web/src/pages/Decisions.tsx:355-360`. It is small, but in this product's trust posture, casual emoji in a decision audit page is off-tone.

Opus was right on Events fetch failure. My Round 1 praised `MarketEvents` states but missed the wrapper-level `.catch(() => setLoading(false))` at `EventsResearchPage.tsx:27`. A failed picks fetch should not become a clean empty catalysts page.

## 4. Pushback

Gemini's FilterBar P0 is refuted by the current file. The component is not using non-standard tab semantics now; it says in code that Phase 13d converted from tabs to a button group (`FilterBar.tsx:38-40`) and implements that with `role="group"` plus `aria-pressed` (`FilterBar.tsx:45-52`). There may still be label and grouping improvements, but this is not the critical keyboard defect.

Sonnet's statement that Risk has NextStep pointing to `/research` is not supported by the implementation I see. Risk imports and renders PageChapter (`apps/web/src/pages/RiskDashboard.tsx:23`, `:45-47`), but there is no `NextStepCard` import or render in the checked lines. Page flow defines Risk's next as Research at `apps/web/src/lib/ui/page_flow.ts:65-68`; the bottom CTA is missing.

Gemini's statement that Portfolio's brief view is the most elite part of the product may be directionally plausible, but it cannot justify scoring the route as if users naturally see it. `/portfolio` still defaults to `PortfolioTerminal`: the router comment says no query param preserves terminal default (`apps/web/src/pages/copilot/PortfolioRouteSwitch.tsx:3-6`), and the code returns `CopilotHoldings` only for `view === "brief"` (`:20-22`).

## 5. Still Missed

We collectively underweighted temporal context. Opus named "what changed," but none of us made it central enough. A premium investing OS should answer "new since last run," "flipped since yesterday," and "stale because source unavailable" on almost every page. This can be honest if derived from existing timestamps and action deltas.

We also underweighted route-level discoverability. Query-param variants (`/overview?view=working`, `/portfolio?view=brief`) may be strategically preserved, but if they are product modes, they need visible toggles. If they are lab modes, they should be labeled as such.

Finally, we underweighted "one control should matter." DensityToggle appears on pages where it has little visible effect. That weakens trust in controls generally. A premium product does not show inert-seeming controls.

## 6. Refined Page Scores

1. **Overview: 7.5/10.** Strong executive briefing, but too many competing heroes and hidden working variants keep it below elite.
2. **Events & Catalysts: 6.2/10.** The component states are honest, but the wrapper swallows fetch errors and lacks event-to-signal prioritization.
3. **Action Queue: 8.1/10.** Still the strongest surface; needs group rationale, better filter taxonomy, and sort/changed controls rather than a semantics fix.
4. **Signal Lab: 5.8/10.** ExpertDetails is right, but the readiness score lacks calibration and the backtest placeholder harms credibility.
5. **Decisions: 6.6/10.** The calm card and audit model are strong, but the layout remains dense, legacy-styled, and awkward on mobile.
6. **Strategies: 7.0/10.** Education collapse helped; the page still needs an active/blocked strategy state before module stacks.
7. **Options: 5.0/10.** Deep and disciplined about disclaimers, but 12 peer tabs and mobile ergonomics are a product-level failure.
8. **Portfolio: 6.5/10.** Data truth is strong, but defaulting to the dense terminal while the brief view is query-hidden is the wrong default experience.
9. **Risk: 6.8/10.** Honest mark handling and wrapped tables are good; missing bottom journey CTA and small bespoke controls keep it legacy.
10. **Alpha Lab: 5.6/10.** Useful research concept, but static fallback registry rendering must be labeled and the page needs a verdict.
11. **Ops: 5.2/10.** Card sprawl is bad, but hardcoded scheduled job statuses make this a trust P0.

## 7. Refined Roadmap

**Phase 15 - Truth, discoverability, and mobile blockers**

1. Add real error handling to Events picks fetch using the existing FetchError pattern; do not let a failed fetch look empty (`EventsResearchPage.tsx:27`).
2. Replace Ops hardcoded scheduled jobs with real data or label them as static placeholders inside expert-only disclosure (`Ops.tsx:263-266`).
3. Label or hide ResearchLab static fallback rows when `shadow` is empty (`ResearchLab.tsx:84-128`).
4. Add visible Portfolio mode toggle and make brief default on mobile first; preserve terminal as expert mode (`PortfolioRouteSwitch.tsx:20-22`).
5. Replace Options 12-tab mobile presentation with a route picker or grouped control; full IA collapse can wait, but the phone interaction cannot.
6. Remove the Decisions emoji and other off-tone microcopy from decision/risk surfaces.
7. Add missing NextStepCard to Risk, Research, Portfolio, and Decisions where it is absent.

**Phase 16 - Coherent IA and progressive disclosure**

1. Collapse Options into 4 grouped sections with secondary navigation.
2. Add "what changed" derived pills to Overview, Events, Action Queue, Portfolio, and Risk.
3. Expand ExpertDetails to Decisions diagnostics, Risk advanced tables, Research internals, Ops long-tail cards, and Options diagnostics/evaluation.
4. Add top-level state panels: Signal Lab readiness band, Strategy active/blocked, Research verdict, Ops warnings-only summary.
5. Normalize table wrappers across PortfolioTerminal and remaining Options components.

**Phase 17 - Premium product feel**

1. Unify density behavior across the product and hide DensityToggle where it does not apply.
2. Tokenize Options and legacy pages into one visual grammar.
3. Add safe, scoped AI explanation affordances using existing data only.
4. Build mobile-native variants for Options, Portfolio, and Decision review rather than only responsive desktop stacks.

## 8. The 12 Questions, Re-answered

1. **Coherent story page-to-page?** Partly. `page_flow.ts:24-78` is coherent, but implementation gaps and route variants fragment it.
2. **Navigation linear or fragmented?** Fragmented inside Options, Portfolio, and Overview variants; strongest in SideNav/PageChapter.
3. **Natural Overview -> Catalysts -> Decisions -> Execution -> Portfolio -> Risk?** The encoded flow is close, but actual flow detours through Signal Lab and a large Options sub-app before Portfolio.
4. **Dead/passive pages?** Events, Signal Lab, Alpha Lab, and Ops; each shows information without enough "what changed / what to do."
5. **Sections to collapse?** Signal Lab backtest placeholder, Decisions diagnostics, Risk advanced details, Alpha Lab internals, Ops card groups, Options diagnostics/evaluation/support.
6. **Sections to make sticky?** Keep mobile sticky minimal. Desktop can use sticky Options section nav, Decisions timeline, and warning filters in Risk/Ops.
7. **Visually noisy cards?** PortfolioSnapshot secondary metrics, Options disclaimers/tabs, Ops card stack, Decisions chip rails.
8. **Under-emphasized cards?** Portfolio brief mode, Risk explanation, Research verdict, Events top catalyst, Action Queue group rationale.
9. **Wasted vertical space?** Overview first-fold repetition, Signal Lab empty backtest block, Ops preamble plus 16-card stack, Options repeated banners.
10. **Too dense?** Options, PortfolioTerminal, Decisions desktop grid, Ops ML/engine/replay sections.
11. **Mobile failures?** Options first, then PortfolioTerminal, Ops, and Decisions review flow.
12. **Developer-built feel?** Options, Ops, Alpha Lab, Signal Lab lower half, and pockets of Risk/Decisions.

## Final Position

Round 2 changes my priority order. I still believe Options IA is the largest product problem, but Phase 15 should first clear truth debt and discoverability defects that can be fixed safely. After that, collapse Options and add temporal "what changed" context. Visual unification matters, but it should follow the trust fixes, not precede them.
