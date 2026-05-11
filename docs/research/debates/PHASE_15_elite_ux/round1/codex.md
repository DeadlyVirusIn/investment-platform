# Phase 15 Elite UX Debate - Round 1 - Codex

## 1. Overview (`/overview`, default `PicksPage`; legacy `?view=working`)

1. **Current UX score: 7.8/10.**
2. **Biggest strengths:** The default page now has a real executive surface: canonical NAV/return/posture subtitle is composed from fetched command-bar data, not invented copy (`apps/web/src/pages/PicksPage.tsx:119-135`); it pairs PageChapter, PortfolioSnapshot, TodayPanel, launcher grid, and NextStepCard in a coherent briefing sequence (`PicksPage.tsx:156-165`, `PicksPage.tsx:177-238`, `PicksPage.tsx:264-273`). PortfolioSnapshot explicitly sources secondary metrics from `/api/paper/summary` (`apps/web/src/components/portfolio/PortfolioSnapshot.tsx:93-99`), which is the right trust posture.
3. **Biggest weaknesses:** The route has too many historical personalities behind query params. `OverviewRouteSwitch` preserves working, stream, conviction, copilot, living, legacy, and default views (`apps/web/src/pages/copilot/OverviewRouteSwitch.tsx:35-46`). That is useful for research, but it weakens product confidence because "Overview" is not one clear object.
4. **Desktop-specific issues:** The default page is strong on desktop, but the hierarchy can still double-hero: PortfolioSnapshot uses a large NAV hero (`PortfolioSnapshot.tsx:58-84`) while PageChapter can also render a NOW hero (`PicksPage.tsx:156-164`).
5. **Mobile-specific issues:** Phase 14 mobile work is real: launcher grid and today panel collapse under mobile CSS (`apps/web/src/lib/picks/picks.css:4289-4297`, `picks.css:4811-4816`), and density/filter controls have mobile treatment (`picks.css:4868-4889`). The concern is vertical load: TopStrip, ticker/status, PageChapter, snapshot, TodayPanel, "Today's read," launchers, empty state/error, NextStep, and footer make the first decisive action too far down on phones.
6. **Novice-user issues:** The 4 launchers help, but "Signal Lab" is intentionally removed from Overview while the flow still sends Action Queue to Signal Lab later (`PicksPage.tsx:197-200`, `apps/web/src/lib/ui/page_flow.ts:37-44`). A novice may not understand why validation sits after action review.
7. **Expert-user issues:** Experts may want the dense working overview; it exists at `?view=working` (`OverviewRouteSwitch.tsx:39`) and contains many advanced details, but discoverability is weak unless linked from elsewhere.
8. **Storyline / navigation issues:** Page-flow says Overview -> Events -> Action Queue (`page_flow.ts:27-40`), and the page supports this with launchers and NextStep. The query-param gallery is the main storyline leak.
9. **Recommended structural changes:** Make default Overview the canonical product view; move experiment variants to a clearly labeled internal lab route or hidden dev menu. Add a small "advanced terminal view" link only if it serves active operators.
10. **Recommended visual changes:** Reduce the visual competition between PageChapter NOW and PortfolioSnapshot NAV by making Snapshot the numeric hero and PageChapter the route-context rail.
11. **Recommended interaction changes:** Add one top-level primary action that changes with state: "Review recommendations," "Check catalysts," or "Inspect risk," derived from real counts already available.
12. **Priority:** P1 high ROI.
13. **Complexity:** Medium. Mostly route IA and small layout edits.
14. **Regression risk:** Medium because Overview has archived variants and many users may rely on query links.

## 2. Events & Catalysts (`/events`)

1. **Current UX score: 7.0/10.**
2. **Biggest strengths:** The page is simple and honest: it fetches picks, derives symbols, hands them to MarketEvents, and renders PageChapter plus NextStep (`apps/web/src/pages/EventsResearchPage.tsx:16-65`). MarketEvents handles loading, not-connected, empty, and ready states explicitly (`apps/web/src/components/portfolio/MarketEvents.tsx:53-109`).
3. **Biggest weaknesses:** It is still mostly a delegated component. The page subtitle says "why behind signal changes" (`EventsResearchPage.tsx:44-46`), but it does not summarize the top catalyst theme before showing symbol cards.
4. **Desktop-specific issues:** MarketEvents cards include counts, earnings, expiry, filing, and news links (`MarketEvents.tsx:127-186`), but there is no global sorting by urgency or impact. Desktop users get a grid, not a narrative.
5. **Mobile-specific issues:** The page inherits the picks mobile shell, but event cards can become repetitive stacks. The short E/N/F/X pill pattern is now title-backed (`MarketEvents.tsx:131-147`) but still requires hover/title affordance that is weak on touch.
6. **Novice-user issues:** "SEC filings" and "options expirations" are useful, but the page should translate whether each item matters today. The labels exist, but the consequence layer is missing.
7. **Expert-user issues:** Experts likely want filters: earnings-only, filings-only, affected action group, freshness window. The current page feeds all symbols from picks, without visible controls.
8. **Storyline / navigation issues:** Strong chain placement: Overview -> Events -> Action Queue is encoded in PageChapter/NextStep (`page_flow.ts:27-40`; `EventsResearchPage.tsx:52-57`).
9. **Recommended structural changes:** Add a top "Catalyst brief" section: top 3 upcoming/changed catalysts, affected symbols, and which action buckets they touch.
10. **Recommended visual changes:** Replace or expand compact event count pills with readable labels on mobile.
11. **Recommended interaction changes:** Add filter chips for catalyst type and urgency; keep the raw cards below.
12. **Priority:** P1 high ROI.
13. **Complexity:** Low to medium.
14. **Regression risk:** Low if derived from existing `EventsState`.

## 3. Action Queue (`/action-queue`)

1. **Current UX score: 8.0/10.**
2. **Biggest strengths:** This is one of the most product-like surfaces. It has persisted density (`apps/web/src/pages/ActionQueuePage.tsx:36`, `ActionQueuePage.tsx:87-100`), PageChapter, skeleton state, FetchError, "Why no buys?" panel, FilterBar, HealthRail, ActionQueue, and NextStep (`ActionQueuePage.tsx:103-217`). The FilterBar now uses honest button-group semantics with `aria-pressed` rather than fake tabs (`apps/web/src/components/picks/FilterBar.tsx:38-56`).
3. **Biggest weaknesses:** The page groups by action, but it does not yet explain dominant shared causes per group. PickBox has per-card rationale and tags (`apps/web/src/components/picks/PickBox.tsx:80-101`), but group-level synthesis would reduce scanning cost.
4. **Desktop-specific issues:** The grid is usable, but the visual weight of action colors can become noisy when many cards are present. The action queue grid is optimized by CSS, but it still depends on many repeated cards (`apps/web/src/components/picks/ActionQueue.tsx:78-95`).
5. **Mobile-specific issues:** Phase 14 improved mobile: filter bar scrolls horizontally (`apps/web/src/lib/picks/picks.css:4878-4889`), pick boxes become one-column with reaffirmed tap targets (`picks.css:4943-5007`), and the no-buys panel has mobile padding (`picks.css:5173-5178`). Remaining issue is thumb reach after long filter + health + why panel stack.
6. **Novice-user issues:** "No buy setups passed thresholds" is plain enough (`ActionQueuePage.tsx:147-164`), but "thresholds" could still be translated into "price, trend, risk, and catalyst checks."
7. **Expert-user issues:** Experts need sort controls: confidence, freshness, catalyst, risk, and portfolio impact. Current filters are action-only.
8. **Storyline / navigation issues:** It is well-positioned as the execution candidate queue and points onward to Signal Lab (`page_flow.ts:37-44`).
9. **Recommended structural changes:** Add per-action group rationale derived from most common tags/features.
10. **Recommended visual changes:** Reduce saturated action accents inside dense groups; keep color on action pill and left rail only.
11. **Recommended interaction changes:** Add sort and "show only changed since last run" controls.
12. **Priority:** P1 high ROI.
13. **Complexity:** Medium.
14. **Regression risk:** Medium because Action Queue is performance-sensitive and should not regress card rendering.

## 4. Signal Lab (`/signal-lab`)

1. **Current UX score: 6.7/10.**
2. **Biggest strengths:** It now has FetchError, persisted density, PageChapter, ExpertDetails, and NextStep (`apps/web/src/pages/SignalLabPage.tsx:63-75`, `SignalLabPage.tsx:92-141`, `SignalLabPage.tsx:187-189`). The readiness formula is no longer always exposed; it is behind an expert collapse (`SignalLabPage.tsx:133-141`).
3. **Biggest weaknesses:** The page remains abstract. Readiness `/100` (`SignalLabPage.tsx:129-131`) is useful only if the user knows what to do when it is 42 vs 83. There is still not enough bridge from validation to decisions.
4. **Desktop-specific issues:** The page can feel under-filled relative to its conceptual importance: a big readiness score plus smaller distributions does not yet feel like a lab.
5. **Mobile-specific issues:** The mobile stack is likely readable because it uses picks-root responsive rules, but the readiness score consumes first-screen attention without a clear next tap.
6. **Novice-user issues:** "Readiness" needs an interpretation band: "safe to inspect," "use caution," "data incomplete," or "do not act," derived honestly from coverage/freshness.
7. **Expert-user issues:** Experts need drill-down per feature family and stale symbol list. If event-feature fetch is incomplete, the page should surface which symbols are missing.
8. **Storyline / navigation issues:** Flow sends Action Queue -> Signal Lab -> Decisions (`page_flow.ts:37-48`). That is coherent for experts but unintuitive for novices who expect "why this pick" immediately after a card.
9. **Recommended structural changes:** Turn readiness into a 3-part health rail: coverage, freshness, action distribution, with the composite as secondary.
10. **Recommended visual changes:** Make the score less like a grade and more like an operational status.
11. **Recommended interaction changes:** Link readiness issues directly to filtered Action Queue or Decisions rows.
12. **Priority:** P1.
13. **Complexity:** Medium.
14. **Regression risk:** Low to medium.

## 5. Decisions (`/decisions`)

1. **Current UX score: 6.8/10.**
2. **Biggest strengths:** The page has PageChapter (`apps/web/src/pages/Decisions.tsx:88`), a novice start-here card, calm interpretation card, source disclosure, and a strong three-column decision narrative grid (`Decisions.tsx:103-198`, `Decisions.tsx:206-269`). It is careful about paper-trade account path distinctions (`Decisions.tsx:427-442`).
3. **Biggest weaknesses:** It remains a legacy dense page. Many sections use older Card/Pill primitives (`Decisions.tsx:14`, `Decisions.tsx:455-526`) and raw tables/diagnostics can dominate the experience.
4. **Desktop-specific issues:** The 360px / fluid / 420px three-column layout is appropriate for terminals (`Decisions.tsx:206-206`), but the right and middle panels can become a wall of production inputs, blocking logic, and diagnostic snapshot (`Decisions.tsx:499-526`).
5. **Mobile-specific issues:** The `xl:overflow-y-auto` usage only activates on xl (`Decisions.tsx:242`, `Decisions.tsx:262`, `Decisions.tsx:269`), so the prior mobile scroll trap appears addressed. However, the page still has `px-8 py-8` on the root (`Decisions.tsx:86`), which is heavy on narrow phones unless global CSS overrides it.
6. **Novice-user issues:** "Engine A/B" and production input vocabulary remains exposed in details. The fallback "Engine fired" label is still technical (`Decisions.tsx:1053-1057`).
7. **Expert-user issues:** Experts benefit from detail but need faster diffing: what changed since prior decision, which factor moved, what blocked.
8. **Storyline / navigation issues:** PageChapter gives route context, but there is no bottom NextStepCard import/use in this page, so the chapter thread is incomplete compared with newer pages (`Decisions.tsx:24-25`).
9. **Recommended structural changes:** Collapse Production inputs, Blocking logic, Diagnostic snapshot, and engineering source into ExpertDetails by default.
10. **Recommended visual changes:** Modernize legacy cards toward the picks/page-chapter visual system without changing data hooks.
11. **Recommended interaction changes:** Add "compare to previous decision" and "show blockers only" toggles.
12. **Priority:** P1.
13. **Complexity:** Medium.
14. **Regression risk:** Medium due to complex existing decision rendering.

## 6. Strategies (`/strategies`)

1. **Current UX score: 7.2/10.**
2. **Biggest strengths:** Strategies has a clean picks-root implementation, persisted density, FetchError, PageChapter, collapsed strategy education, TradeLifecycle, PremiumIncome, StrategyModules, and NextStep (`apps/web/src/pages/StrategiesPage.tsx:27-36`, `StrategiesPage.tsx:63-116`). The education section now uses ExpertDetails and a corrected h2 hierarchy (`StrategiesPage.tsx:85-101`).
3. **Biggest weaknesses:** It still feels more like a library of modules than a strategy decision desk. It says "How a signal becomes a trade" (`StrategiesPage.tsx:67-69`) but does not start with "today, no/these strategies are active because..."
4. **Desktop-specific issues:** Trade lifecycle and premium modules are valuable, but the structural priority between strategy education, lifecycle, income, and modules could be clearer.
5. **Mobile-specific issues:** Collapsing education helps mobile. The remaining risk is tables from TradeLifecycle, though that component has a table wrapper and screen-reader caption (`apps/web/src/components/portfolio/TradeLifecycle.tsx:117-123`).
6. **Novice-user issues:** Options strategy names need short "why you care" copy next to each strategy, not only in the collapsed education.
7. **Expert-user issues:** Experts need strategy filters tied to actual open positions, premium, and risk contribution.
8. **Storyline / navigation issues:** Flow sends Strategies -> Options (`apps/web/src/lib/ui/page_flow.ts:51-58`), which is correct, but the page should more visibly explain when to continue to Options versus Portfolio.
9. **Recommended structural changes:** Add a top current-state card: active strategies, inactive strategies, blocked strategies.
10. **Recommended visual changes:** Make strategy modules less equal-weight; emphasize active/relevant modules.
11. **Recommended interaction changes:** Add "show active only" and "show eligible today" filters.
12. **Priority:** P2/P1 boundary.
13. **Complexity:** Medium.
14. **Regression risk:** Low to medium.

## 7. Options (`/options/*`, 12 tabs)

1. **Current UX score: 5.9/10 overall.**
2. **Biggest strengths:** The surface is disciplined about disclaimers. OptionsLayout renders paper-only and data-availability banners before content (`apps/web/src/pages/options/OptionsLayout.tsx:36-44`), and advanced tabs repeat observation/evaluation/support/framing disclaimers as needed (`OptionsDecisionSupportPage.tsx:49-53`, `OptionsDecisionFramingPage.tsx:56-61`). The overview landing explicitly says read-only, paper only, no orders (`apps/web/src/pages/options/OptionsOverviewPage.tsx:104-124`).
3. **Biggest weaknesses:** Twelve peer tabs are too much. The tab list is a flex-wrapped nav (`OptionsLayout.tsx:48-64`), so on mobile it becomes a multi-row control wall. The implementation also remains heavily Tailwind/zinc-based across pages and components (`OptionsChainPage.tsx:50-74`, `OptionsStrategyDiagnosticsPage.tsx:122-157`, `OptionsEvaluationScoreTable.tsx:55-57`), which feels separate from picks-root.
4. **Desktop-specific issues:** Desktop experts can use the tabs, but the IA is flat: Chain, Features, Trades, Risk, Observatory, Performance, Diagnostics, Replay, Evaluation, Decision Support, Decision Framing all compete as siblings (`OptionsLayout.tsx:19-32`).
5. **Mobile-specific issues:** Many controls are flex-wrap forms (`OptionsDecisionFramingPage.tsx:79-124`, `OptionsStrategyEvaluationPage.tsx:55-95`), some selects are `w-[28rem] max-w-full` (`OptionsDecisionFramingPage.tsx:146-165`), and drawers are fixed full-height side panels (`apps/web/src/components/options/OptionsReviewDetailDrawer.tsx:16`, `OptionsTradeDetailDrawer.tsx:16`). Tables are inconsistently wrapped: some use `overflow-x-auto` (`OptionsTradesTable.tsx:42-43`), some use `u-table-wrap` (`OptionsRiskDashboardPage.tsx:48-67`), while others are raw table components (`OptionsPerformanceTables.tsx:11-45`, `OptionsReplayTimeline.tsx:78`).
6. **Novice-user issues:** Options Overview helps, but the tab list immediately exposes pro concepts. Decision Support and Decision Framing sound actionable despite disclaimers.
7. **Expert-user issues:** Experts need the depth, but they also need task grouping: "Observe market," "Review paper trades," "Evaluate strategy," "Diagnostics." Current tabs require memorizing the entire feature map.
8. **Storyline / navigation issues:** Page-flow treats `/options/*` as one step (`page_flow.ts:55-58`, `page_flow.ts:91-95`), but the nested product has its own large flow that is not reconciled with the main journey.
9. **Recommended structural changes:** Replace 12 peer tabs with 4 grouped sections and secondary tabs inside each: Market data, Paper trades, Evaluation, Diagnostics. Keep `/options/overview` as a novice landing.
10. **Recommended visual changes:** Tokenize zinc-heavy components to `--pi-*`/`--fg-*` and align cards/banners with shell/picks visual language.
11. **Recommended interaction changes:** On mobile, use a segmented group/dropdown for Options subroutes and convert drawers to bottom sheets or full-screen detail routes.
12. **Priority:** P0 for mobile/IA; P1 for tokenization.
13. **Complexity:** High.
14. **Regression risk:** High because this is a broad nested app with many tables, drawers, and route links. Sub-tab callouts: Overview is the best novice entry; Chain/Features are utilitarian; Paper Trades/Risk/Performance are useful but table-heavy; Diagnostics/Evaluation/Decision Support/Decision Framing are expert-only and should be grouped or collapsed.

## 8. Portfolio (`/portfolio`)

1. **Current UX score: 6.9/10.**
2. **Biggest strengths:** PortfolioTerminal is explicit about data sources and mark discipline: executed trades/open positions come from executed endpoints, strategy logs are separate, and exposure uses summary positions value without deriving marks from stale data (`apps/web/src/pages/PortfolioTerminal.tsx:3-15`, `PortfolioTerminal.tsx:67-85`). It reads `/api/paper/summary` through `usePaperSummary` (`PortfolioTerminal.tsx:33`).
3. **Biggest weaknesses:** The default route still returns the dense working terminal, while a brief view exists only at `?view=brief` (`apps/web/src/pages/copilot/PortfolioRouteSwitch.tsx:17-22`). The default experience therefore favors operators over novices.
4. **Desktop-specific issues:** Desktop has strong financial detail, but there are several unwrapped `u-table` instances in PortfolioTerminal (`PortfolioTerminal.tsx:316`, `PortfolioTerminal.tsx:387`, `PortfolioTerminal.tsx:473`, `PortfolioTerminal.tsx:532`). If the global `.u-table-wrap` is not applied around these, wide tables can stress the layout.
5. **Mobile-specific issues:** The root uses `px-8 py-8` (`PortfolioTerminal.tsx:101`) and dense tables. Mobile users likely need the brief view by default, with terminal as a secondary route.
6. **Novice-user issues:** The page explains focus and calm state (`PortfolioTerminal.tsx:121-206`), but then drops into terminal tables quickly.
7. **Expert-user issues:** Experts will like the detail and replay separation; the include-replay checkbox appears around the replay availability block (`PortfolioTerminal.tsx:159-179`).
8. **Storyline / navigation issues:** Page-flow says Options -> Portfolio -> Risk (`apps/web/src/lib/ui/page_flow.ts:55-68`), but PortfolioTerminal itself does not use PageChapter/NextStepCard. That makes the main journey weaker here than on picks-root pages.
9. **Recommended structural changes:** Make brief holdings the default for `/portfolio`, with a "Terminal" toggle for dense mode once mobile quality is verified.
10. **Recommended visual changes:** Wrap all terminal tables consistently and align summary cards to the PortfolioSnapshot language.
11. **Recommended interaction changes:** Add sticky section jump controls only after the brief summary, not before it.
12. **Priority:** P1.
13. **Complexity:** Medium.
14. **Regression risk:** Medium because this is canonical paper account truth.

## 9. Risk (`/risk`)

1. **Current UX score: 7.0/10.**
2. **Biggest strengths:** Risk has excellent honest-data posture in comments and UI: it refuses to fabricate marks (`apps/web/src/pages/RiskDashboard.tsx:3-6`), prioritizes mark-unavailable over other narratives (`RiskDashboard.tsx:171-184`), and wraps concentration tables in `u-table-wrap` (`RiskDashboard.tsx:482-535`, `RiskDashboard.tsx:536-565`, `RiskDashboard.tsx:570-635`).
3. **Biggest weaknesses:** It is still a legacy page with PageChapter but no NextStepCard, and it mixes calm copy with dense concentration tables.
4. **Desktop-specific issues:** The top KPI grids work (`RiskDashboard.tsx:305-353`), but advanced tables under details can still be visually heavy.
5. **Mobile-specific issues:** Table wrapping is now present, which is a major improvement. The remaining issue is vertical density from intro, focus card, calm card, KPIs, concentration tables, and advanced section.
6. **Novice-user issues:** "Mark unavailable" is honest but should be phrased as "live price not yet available" in primary copy while retaining raw wording in expert/source text.
7. **Expert-user issues:** Experts need sticky risk thresholds and sort-by-exposure controls; the page currently reads more static than investigative.
8. **Storyline / navigation issues:** It sits correctly after Portfolio and before Alpha Lab (`page_flow.ts:61-74`), but no bottom CTA means the handoff to Research is implicit.
9. **Recommended structural changes:** Add NextStepCard to Research; collapse full breakdowns more aggressively.
10. **Recommended visual changes:** Give risk severity a clearer hierarchy: current blocker, watch item, informational.
11. **Recommended interaction changes:** Add sorting/filtering by exposure, mark availability, and portfolio.
12. **Priority:** P1.
13. **Complexity:** Low to medium.
14. **Regression risk:** Low if source semantics are preserved.

## 10. Alpha Lab (`/research`)

1. **Current UX score: 6.1/10.**
2. **Biggest strengths:** PageChapter exists (`apps/web/src/pages/ResearchLab.tsx:32`), and the page uses cards, tabs, research/performance hooks, and empty states. It positions Alpha Lab as research/backtest/experimentation after Risk (`page_flow.ts:71-74`).
3. **Biggest weaknesses:** It remains a developer/researcher surface. The local nav is Tailwind utility tabs (`ResearchLab.tsx:50-62`), and the page has many cards/grids without a top "what did we learn?" summary (`ResearchLab.tsx:132-161`, `ResearchLab.tsx:377-450`).
4. **Desktop-specific issues:** Desktop has enough space for research cards, but hierarchy is flat: runs, patterns, execution summaries, and empty states compete.
5. **Mobile-specific issues:** Multiple grids collapse, but the page is likely long and passive on phones. There is no sticky local context or bottom NextStepCard to Ops.
6. **Novice-user issues:** "Alpha Lab" is not self-explanatory. A novice needs "this is where the system learns from paper results; it does not change trades automatically unless promoted."
7. **Expert-user issues:** Experts need provenance, run recency, and promotion status up front.
8. **Storyline / navigation issues:** Good placement after Risk, but weak story inside the page. It does not clearly answer "what should change because of this research?"
9. **Recommended structural changes:** Add a research verdict panel: latest finding, confidence/data sufficiency, whether it affects production.
10. **Recommended visual changes:** Move from old tab-card feel toward the page-chapter/picks token system.
11. **Recommended interaction changes:** Add filters by production vs shadow, open vs closed trades, and timeframe.
12. **Priority:** P2/P1 boundary.
13. **Complexity:** Medium.
14. **Regression risk:** Medium if research semantics are touched; low for visual shell improvements.

## 11. Ops (`/ops`)

1. **Current UX score: 6.4/10.**
2. **Biggest strengths:** Ops has PageChapter, a start-here focus card, calm operational interpretation, source disclosure, sticky section nav, and a wide set of operational cards (`apps/web/src/pages/Ops.tsx:48-143`, `Ops.tsx:287-311`). It is honest about paper trading and ingestion status in its calm copy (`Ops.tsx:370-423`).
3. **Biggest weaknesses:** It is card sprawl. Many ML/engine/replay/promotion cards appear as top-level siblings (`Ops.tsx:210-256`), which makes the page feel internal rather than premium.
4. **Desktop-specific issues:** Sticky section nav is useful for long desktop pages (`Ops.tsx:287-311`), but it adds another navigation layer below global nav and PageChapter.
5. **Mobile-specific issues:** Sticky local nav plus TopStrip can crowd mobile. The long sequence of cards is likely tiring and hard to resume after scrolling.
6. **Novice-user issues:** Terms like Engine B, B2 vs V2, shadow ML, promotion trigger, replay training readiness are operationally valid but should not be equal-weight for novices.
7. **Expert-user issues:** Experts need exactly this detail, but grouped by operational question: Is it running? Is data fresh? Is ML safe? Can we recover/replay?
8. **Storyline / navigation issues:** It is the final flow step (`page_flow.ts:75-78`) and has no next step. That is fine, but it should close the loop back to Overview if healthy or Risk if unhealthy.
9. **Recommended structural changes:** Group cards into collapsible sections: Live system, ML/shadow, engine promotion, replay/history, scheduler/config.
10. **Recommended visual changes:** Make health/failure state the page hero; demote long-tail experimental cards.
11. **Recommended interaction changes:** Add "show only warnings" and "copy ops snapshot" controls.
12. **Priority:** P1.
13. **Complexity:** Medium.
14. **Regression risk:** Medium because Ops components may be independently owned.

## A. Cross-Product Findings

The shell is materially stronger than the prior architecture: skip link and `main-content` exist (`apps/web/src/components/shell/Shell.tsx:47-83`), mobile drawer state, Escape close, body scroll lock, and overlay are implemented (`Shell.tsx:12-75`), SideNav has a fixed 220px desktop rail and mobile drawer target (`apps/web/src/components/shell/SideNav.tsx:19-34`), and TopStrip mobile hides lower-priority slots (`apps/web/src/components/shell/TopStrip.tsx:18-29`; `apps/web/src/index.css:1653-1685`). The mobile sticky relaxation is also real: CSS pins only TopStrip on mobile (`apps/web/src/index.css:1766-1783`).

The biggest inconsistency is not one missing component; it is mixed product eras. Newer picks-root pages have density, PageChapter, NextStepCard, FetchError, and mobile-specific CSS (`apps/web/src/lib/picks/picks.css:3210-3361`, `picks.css:4013-4117`, `picks.css:4485-4540`). Legacy pages use `u-card`/Tailwind layouts and only partially adopt PageChapter. Options has its own dense Tailwind/zinc ecosystem with many hard-coded colors and tables. This creates an "adjacent product" feel exactly where trust matters most.

Typography and density are also uneven. Density is strong on picks-family pages through `readInitialDensity` and root `data-density` (`apps/web/src/components/portfolio/DensityToggle.tsx:13-47`), but PortfolioTerminal, Decisions, Risk, Alpha Lab, and Ops do not participate in the same density contract. Interaction semantics are better than before: FilterBar is a proper button group, skip link exists, and table captions exist in some components, but Options and Portfolio tables remain inconsistent.

## B. Elite-Gap Analysis

This is not yet a world-class AI-native investing product, but it is moving from "dashboard collection" toward "operating system." The best surfaces, Overview and Action Queue, tell a stateful story with real data, paper-trading disclaimers, error states, density modes, and explicit next steps. The trust posture is unusually good: PortfolioSnapshot and PortfolioTerminal avoid fake marks, Risk refuses to fabricate exposure, and Options repeats paper-only boundaries.

The elite gap is coherence. Premium AI-native products make every screen feel like one guided conversation with different levels of depth. This app still exposes its build history: query-param overview variants, a dense terminal Portfolio default, a 12-tab Options sub-app, and legacy research/ops pages. It often shows all truthful information rather than the next truthful decision. That is safer than inventing AI states, but it is not yet elite.

The second gap is mobile. The shell and picks pages have serious mobile work, but the product-wide journey is only as good as its weakest deep page. Options drawers, wide tables, flat tab nav, PortfolioTerminal tables, and long Ops/Research scrolls are not yet iPhone-first experiences.

The third gap is role clarity. Novices need "what changed, what matters, what should I inspect next." Experts need provenance, drill-down, and controls. The app often gives both at once. ExpertDetails is the right pattern, but it is underused on Decisions, Risk, Research, Ops, and Options diagnostics.

## C. Final Ranked Roadmap

**Phase 15 - Coherent Journey + Mobile Foundations**

1. Replace Options 12 peer tabs with grouped IA and a mobile route picker. Highest impact because Options is the biggest cognitive and mobile failure.
2. Complete PageChapter + NextStepCard threading on PortfolioTerminal, Risk, Alpha Lab, Ops, and Decisions where missing.
3. Make `/portfolio?view=brief` the default mobile-first portfolio view, with terminal as an explicit expert mode.
4. Add group-level rationales to Action Queue and catalyst brief to Events.
5. Normalize all wide tables into a single responsive table wrapper pattern, including PortfolioTerminal and remaining Options components.

**Phase 16 - Novice Clarity + Expert Collapse**

1. Expand ExpertDetails across Decisions diagnostics, Risk full breakdowns, Alpha Lab research internals, Ops long-tail cards, and Options diagnostics/evaluation/support pages.
2. Add plain-English state bands: Signal Lab readiness interpretation, Risk severity hierarchy, Strategy active/blocked state, Research verdict.
3. Tokenize Options zinc-heavy components into the shared color system.
4. Add mobile bottom-sheet/fullscreen detail behavior for Options drawers.
5. Add "show warnings only," "changed since last run," and "active only" controls where they reduce scanning.

**Phase 17 - Premium Polish Without Fake Signals**

1. Unify density contract beyond picks-root.
2. Refine visual hierarchy: fewer equal-weight cards, clearer numeric heroes, quieter repeated disclaimers after the first page-level boundary.
3. Add safe microinteractions already represented in CSS patterns: focus-visible, active press, restrained hover lift.
4. Build a closed-loop end state: Ops healthy routes back to Overview; Ops unhealthy routes to Risk or Diagnostics.
5. Only consider richer AI-native narrative if every sentence is derived from existing canonical fields.

## Explicit Answers to the 12 Brief Questions

1. **Coherent story page-to-page?** Partly. `page_flow.ts` defines a coherent chain from Overview to Ops (`apps/web/src/lib/ui/page_flow.ts:24-78`), and PageChapter/NextStep make it visible on newer pages. Portfolio, Risk, Alpha Lab, Ops, and Decisions still only partially complete the story.
2. **Navigation linear or fragmented?** Fragmented in two places: Overview query-param variants (`apps/web/src/pages/copilot/OverviewRouteSwitch.tsx:35-46`) and Options 12-tab nav (`apps/web/src/pages/options/OptionsLayout.tsx:19-64`).
3. **Guided Overview -> Catalysts -> Decisions -> Execution -> Portfolio -> Risk?** The encoded flow is Overview -> Events -> Action Queue -> Signal Lab -> Decisions -> Strategies -> Options -> Portfolio -> Risk (`page_flow.ts:27-68`). It is logically stronger than before, but the user can still lose the thread inside Options and Portfolio.
4. **Dead/passive pages?** Alpha Lab and Ops feel most passive; Events can feel passive without a catalyst summary. Signal Lab is useful but abstract.
5. **Sections to collapse?** Decisions diagnostics/inputs, Risk full breakdowns, Alpha Lab internals, Ops ML/promotion/replay groups, and Options Diagnostics/Evaluation/Decision Support/Decision Framing.
6. **Sections to make sticky?** Keep TopStrip sticky only on mobile. On desktop, consider sticky local route pickers for Options and sticky "warnings only" controls in Ops/Risk. Avoid more sticky blocks on phones.
7. **Noisy cards?** Action Queue repeated action-color cards, Options disclaimer stacks, Ops engine/ML card sprawl, and PortfolioTerminal repeated dense table cards.
8. **Under-emphasized cards?** "Why no buys?" in Action Queue, mark-unavailable truth in Portfolio/Risk, Options Overview read-only explanation, and Research verdict/provenance.
9. **Wasted vertical space?** Overview first-screen stack on mobile, Options repeated banners on every subtab, PortfolioTerminal intro plus dense terminal transition, Ops long card sequence.
10. **Too-dense sections?** Options Diagnostics/Evaluation/Decision pages, Decisions detail panels, PortfolioTerminal tables, Ops ML/engine section.
11. **Mobile-broken pages?** Options is the biggest failure risk; PortfolioTerminal and Ops are next; Decisions is improved but still heavy.
12. **Developer-built feel?** Options, Alpha Lab, Ops, and parts of Decisions. Overview and Action Queue feel closest to premium product.

