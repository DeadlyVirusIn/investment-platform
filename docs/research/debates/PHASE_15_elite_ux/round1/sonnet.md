# Phase 15 Elite UX Debate — Round 1 (Sonnet / Pragmatic Implementer)

**Perspective:** Pragmatic Implementer — the person who builds the recommendations, debugs them at 2am, and ships them without regressions.

**Methodology:** Audited all 11 page TSX files, shell components, picks.css (5178 lines), index.css (1789 lines), and page_flow.ts. All citations are file:line references to verified code.

---

## Page-by-Page Audit

---

### Page 1a: Overview (PicksPage.tsx) — the AI launcher

**Score: 7.5/10**

**Biggest strengths:**
- Executive briefing subtitle at PicksPage.tsx:122–136 is honest and composable — it gracefully degrades from "NAV · return · posture" to "N live signals" to "Loading…" without fabricating values.
- 4-card launcher grid (PicksPage.tsx:201–241) clearly maps the cognitive journey: signals → catalysts → strategies → risk. Each card has an eyebrow, metric, and body.
- Empty state (PicksPage.tsx:245–262) is complete: icon, title, body, and a freshness timestamp when available. No blank screen.
- `FetchError` component present and wired (PicksPage.tsx:167–173).

**Biggest weaknesses:**
- The page duplicates work with Overview.tsx. Two separate "Overview" experiences at `/overview` and `/overview?view=working` create a split-brain problem: which is canonical? The `PicksPage` is the default but Overview.tsx is more data-dense. A novice landing on `/overview` sees launchers; a power user who bookmarks `/overview?view=working` gets a completely different page. There is no UI affordance on PicksPage to discover the working view.
- `LauncherCard` (PicksPage.tsx:43–55) has no hover state beyond CSS — no skeleton on metric load, so if `commandBar` is slow, the metric cell just shows "Wheel · CC · CSP · LEAPS" fallback while the Strategies card is the only one not showing a real number.
- The `DensityToggle` at the top right of the header affects card density but the launcher grid itself has no density-responsive behavior — at "spacious" density the launcher grid still renders at the same size.

**Desktop-specific issues:**
- Launcher grid uses `launcher-grid` class (CSS-defined, not audited inline here). At wide viewports the 4 cards likely do a 2×2 or 4×1 grid. Without explicit max-width constraints on each card there is a risk of oversized cards at 1800px+.
- `TodayPanel` (PicksPage.tsx:177–186) is rendered before the "Today's read" line and launcher grid. On a 1440px display, TodayPanel likely takes substantial vertical space before the user sees the launchers.

**Mobile-specific issues:**
- Phase 14f-D set 44px tap targets for PickBox — this is good. However the `LauncherCard` is a `<Link>` wrapping arbitrary content; its tap target size depends entirely on `picks.css` `.launcher-card` rules.
- Mobile header flex-wrap (picks.css line ~83: `flex-wrap: wrap`) should handle the DensityToggle moving below the title, but the gap between the title and DensityToggle on small screens may not be visually calibrated.
- The `picks-frame` padding is `clamp(40px, 6vw, 72px)` vertical at picks.css:80 — on a 390px iPhone the vertical padding is ~23px which is reasonable, but the horizontal padding `clamp(20px, 4vw, 56px)` gives ~16px at 390px which is tight but workable.

**Novice-user issues:**
- No tooltip or explanation on the confidence metric shown in LauncherCard metric field. A novice seeing "3 buy · 1 sell" doesn't know what that means without clicking through.
- "Today's read" (PicksPage.tsx:192–196) is derived from `briefing.headline` but there is no explanation of what makes today's read different from the launcher cards.

**Expert-user issues:**
- Experts cannot get directly to the raw signal view from the Overview launcher — they click "Action Queue" and then filter. The launcher is optimized for novices.
- No keyboard shortcut hint on the Overview page itself. The SideNav shows hotkeys (e.g., "O" for Overview) but nothing on the page body.

**Storyline/navigation issues:**
- The flow from Overview → Events → Action Queue is implied by the launcher ordering but the launchers go signals → catalysts → strategies → risk, which differs from the FLOW order in page_flow.ts (overview → events → action-queue → signal-lab → decisions → ...). This ordering mismatch creates narrative dissonance: the launcher says "review signals first" but the flow says "check events first."
- NextStepCard at PicksPage.tsx:264–272 correctly points to the next chapter but renders at the bottom after the disclaimer footer visual, which means it may not be visible without scrolling on mobile.

**Recommended structural changes:**
- Reorder launcher cards to match page_flow.ts: Overview → Events & Catalysts → Action Queue → Strategies. Currently the order is action-queue → events → strategies → portfolio.
- Add a discrete "Advanced view" link on the Overview page pointing to `/overview?view=working` so the dual-page isn't hidden.

**Recommended visual changes:**
- Add loading shimmer to the `metric` prop of LauncherCard when `commandBar` is null.
- DensityToggle should be in a sticky bar or collapsed into an overflow menu on mobile instead of appearing in the header.

**Recommended interaction changes:**
- Make the `LauncherCard` have a subtle scale or border-glow on hover/focus to feel interactive vs static.

**Priority:** P1 — launcher order mismatch with page_flow is a real navigation story break. The dual-overview split is P2 complexity.

**Implementation complexity:** S (launcher reorder) / M (dual-overview reconciliation)

**Regression risk:** Low for launcher reorder; Medium for dual-overview (PicksPage and Overview.tsx are independently rendered, touching routing logic).

---

### Page 1b: Overview.tsx (working view)

**Score: 7.0/10**

**Biggest strengths:**
- The `deriveCalmState` function (Overview.tsx:576–631) provides a clean novice-first interpretation: warming up → needs attention → cautious → operating normally. This is excellent honest-data UX.
- `AdvancedDetails` usage is well-disciplined: RegimeHeatmap, intelligence grid, and trade blotter are all gated behind expanders (Overview.tsx:360–532), keeping the primary surface clean.
- `ExecutionStatusCard` at Overview.tsx:138 resolves the common "why didn't the system trade?" confusion.

**Biggest weaknesses:**
- The "Start here" ordered list (Overview.tsx:100–129) and the calm-state card (Overview.tsx:148–215) are both shown simultaneously on every page load, even for expert users. Two instructional blocks before any data is visible creates a "wall of guidance" before content.
- The 70/30 grid layout (`lg:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]` at Overview.tsx:308) gives the right column a very narrow column at normal laptop widths. The right column contains AlphaCoreStatus, TopCatalysts, Engine Attribution, Current Risk, and Next Step — five cards in a 30% column is severely cramped.
- `RecentActivity` section at Overview.tsx:403–481 uses raw column headers ("Date", "Eng", "Regime") that still read as engineering vocabulary despite other clean-up work.

**Desktop-specific issues:**
- The NAV strip grid at Overview.tsx:234 uses `gridTemplateColumns: "2.2fr 1fr 1fr 1fr 1fr"` with `gap: "44px"` — at 1440px with a 220px sidebar, that 44px gap may push the stat cells too far apart leaving visible empty horizontal runs.

**Mobile-specific issues:**
- The `lg:grid-cols-[...]` layout collapses to single column on mobile which is correct. But the ordering of sections on mobile matters: ReadinessStrip → ExecutionStatusCard → calm state → DailyActivity → "Today's numbers" anchor → NAV strip → "Charts & insights" anchor → the massive chart grid. The chart is below a lot of context, which is appropriate, but on a 390px iPhone the user scrolls significantly before seeing account value.
- The `u-nav-strip` NAV section at Overview.tsx:231 uses `gridTemplateColumns: "2.2fr 1fr 1fr 1fr 1fr"` with inline style — on mobile this becomes a horizontal scroll or overflow, not a stacked layout.

**Novice issues:**
- Both "Start here" and "System diagnostics" (inside AdvancedDetails) may confuse a novice about which they should look at first.

**Expert issues:**
- The AdvancedDetails expanders use `+` / `−` as toggle indicators (ExpertDetails.tsx:29–32) — this is minimal but not discoverable. No animation, no chevron.

**Storyline/navigation issues:**
- Overview.tsx has no `NextStepCard` or PageChapter at its bottom. The only narrative rail is the inline `PageChapter` at the very top of PicksPage. Since Overview.tsx is a separate route (`/overview?view=working`), it lacks the chapter navigation.

**Recommended structural changes:** Consolidate the two Overview experiences or make Overview.tsx explicitly the "System" view, PicksPage explicitly the "Portfolio" view, with a toggle visible on both.

**Recommended visual changes:** Reduce inline style usage — the `style={{ padding: "12px 16px" }}` at Overview.tsx:101 and similar inline padding overrides should be abstracted into CSS classes.

**Priority:** P1 (NAV strip mobile overflow), P2 (start-here density)

**Implementation complexity:** M

**Regression risk:** Medium — Overview.tsx uses 8+ hooks; any structural change risks race conditions.

---

### Page 2: Events & Catalysts (EventsResearchPage.tsx)

**Score: 5.5/10**

**Biggest strengths:**
- Clean delegation to `MarketEvents` component (EventsResearchPage.tsx:54) — the page itself is thin and testable.
- PageChapter and NextStepCard are both wired (lines 52, 56–63).
- DensityToggle present.

**Biggest weaknesses:**
- The page is almost entirely pass-through. It fetches picks to derive symbols, then passes symbols to `MarketEvents`. The page itself has no opinionated layout, no hierarchy, no concept of "most important catalyst today." Every symbol is equal.
- The subtitle "SEC filings, news momentum, and earnings windows — the 'why' behind signal changes" is good copy but the `MarketEvents` component (not audited in detail but referenced) presumably shows a flat list. There is no visible prioritization or prominence for the most urgent catalyst.
- The `nowText` (EventsResearchPage.tsx:33–37) is generic: "N symbols from active recommendations · SEC EDGAR feed live · provider news where keys configured." The phrase "where keys configured" is visible user-facing engineering-speak.

**Desktop-specific issues:**
- The page is purely a wrapper. Any desktop layout issues are in `MarketEvents`, which is not audited here. Risk: if `MarketEvents` uses a wide table, the density toggle may not affect its layout.

**Mobile-specific issues:**
- The `picks-frame` horizontal padding clamp will apply. But if `MarketEvents` renders a table, horizontal overflow is a real risk on a 390px viewport.
- No skeleton loading state is visible on the page (unlike ActionQueue which has explicit skeletons at ActionQueuePage.tsx:115–128). The `loading` state just resolves to empty `nowText`.

**Novice issues:**
- A novice doesn't know the difference between "SEC filings" and "news momentum." No explanatory text distinguishes the feed types.
- The page has no "What should I do with this information?" guidance.

**Expert issues:**
- No ability to filter catalysts by type (SEC only, news only, earnings only).
- No way to see the raw impact score or signal-change delta for each catalyst.

**Storyline/navigation issues:**
- The PageChapter NEXT points to `/action-queue` — correct per the flow. But the Events page doesn't explain HOW a catalyst connects to a specific action-queue signal. The link between "this SEC filing → that buy signal" isn't surfaced.

**Recommended structural changes:**
- Add a skeleton loader that mirrors `MarketEvents` structure.
- Replace "provider news where keys configured" with "News feed active" or simply remove conditional copy.
- Add prominent "highest-priority catalyst today" hero area at top.

**Priority:** P1 (skeleton), P2 (catalyst prioritization hero)

**Implementation complexity:** M

**Regression risk:** Low — wrapper page with no data owned.

---

### Page 3: Action Queue (ActionQueuePage.tsx)

**Score: 8.0/10**

**Biggest strengths:**
- Phase 14c skeleton loader (ActionQueuePage.tsx:115–128) is excellent — 3 ghost group cards with aria-busy and sr-only text.
- "Why no buys?" panel (ActionQueuePage.tsx:146–170) is a genuine UX innovation. It surfaces the posture without fabrication.
- `HealthRail` sidebar and `FilterBar` create a genuine two-panel layout.
- `FetchError` wired properly.

**Biggest weaknesses:**
- The FilterBar sits ABOVE the "Why no buys?" panel in the JSX (ActionQueuePage.tsx:139–144), but the "Why no buys?" panel explains why there are no results for a certain filter. The panel should appear in context, not before the filter that triggered it.
- The `queue-layout` div (ActionQueuePage.tsx:172) uses a CSS class for the sidebar layout. On mobile, whether `HealthRail` stacks above or below the main queue isn't controlled in the TSX — it's entirely CSS. This is fine but means mobile behavior can't be audited from the TSX alone.
- No per-card confirmation that a signal is "fresh" vs "stale" without clicking into the modal.

**Desktop-specific issues:**
- The queue-main + HealthRail sidebar layout: if `HealthRail` is a fixed-width sidebar, it may not collapse gracefully at 1024px breakpoint where the SideNav (220px) + content area becomes narrow.

**Mobile-specific issues:**
- The skeleton has 3 ghost cards which is good. On mobile at 390px, the 3-card skeleton stacks vertically.
- FilterBar has `overflow-x` behavior per Phase 14f-C, which should prevent horizontal overflow of filter pills.

**Novice issues:**
- "AI decision desk · balanced posture" in the subtitle is jargon. "Balanced posture" is defined nowhere on the page.

**Expert issues:**
- No ability to sort cards by confidence descending within an action group.
- No bulk select / copy to clipboard for the picks list.

**Storyline/navigation issues:**
- NextStepCard at ActionQueuePage.tsx:208–214 reads "Validate model quality before acting on N live signals" → points to Signal Lab. This is a good narrative link.

**Priority:** P1 (FilterBar/why-no-buys ordering), P2 (confidence sort)

**Implementation complexity:** S (FilterBar reorder), M (sort)

**Regression risk:** Low — ActionQueue component is a stable consumer.

---

### Page 4: Signal Lab (SignalLabPage.tsx)

**Score: 5.0/10**

**Biggest strengths:**
- The readiness composite formula (SignalLabPage.tsx:43–55) is honest and its weights are documented in code and exposed to users via ExpertDetails.
- ExpertDetails wraps the formula properly (SignalLabPage.tsx:133–142).
- Action distribution and freshness buckets are real metrics.

**Biggest weaknesses:**
- The "Backtest validation" section (SignalLabPage.tsx:171–184) is permanently empty with "Not yet wired" status. This is a tombstone occupying screen real estate with no data. A novice user reading "Walk-forward results, IC decay curves, and feature contribution charts appear here once /api/recommendations/diagnostics surfaces those metrics" sees an engineering backlog ticket, not product.
- The readiness score (a single integer 0-100) is the entire hero metric. Without context for what a "good" score looks like (is 72 good? what does 45 mean?), the number has no interpretive value.
- The page uses `ps-snapshot` / `ps-hero` / `ps-secondary` CSS class names (picks.css-referenced) but not the `picks-root` / `picks-frame` standardized layout pattern that other pages use.

**Desktop-specific issues:**
- The `ps-secondary` grid (SignalLabPage.tsx:144–167) — a row of 5 metrics — may not reflow cleanly at intermediate widths between 768px and 1200px.

**Mobile-specific issues:**
- Phase 14f-C set `ps-secondary` to 2-col mobile. Good. But the hero section (`ps-hero`) still has `ps-nav-value` (a large number) and `ps-nav-delta-pct` which haven't been audited for mobile font size degradation.

**Novice issues:**
- The readiness score label is "Model readiness" with no explanation of what "model" means in this context. The ExpertDetails is collapsed by default — the label should have a one-line explainer visible without expansion.
- "Event coverage" (SignalLabPage.tsx:163–165) shows `featAvail/totalSyms` — novices don't understand what "event coverage" means for trading.

**Expert issues:**
- No per-symbol freshness breakdown — only aggregate counts.
- No ability to drill down into which symbols are stale or which lack event features.

**Storyline/navigation issues:**
- Signal Lab sits between Action Queue and Decisions in the flow. Its job is "validate before acting." But the page currently validates the model state, not the individual signals. The connection between "readiness 72/100" and "should I act on AAPL buy?" is entirely left to the user.

**Recommended structural changes:**
- Replace the empty "Backtest validation" section with a concrete "No backtest data yet" empty state explaining what will appear and when, or remove the section entirely until the endpoint exists.
- Add a band (e.g., 0-40 = red, 41-70 = amber, 71-100 = green) around the readiness score with a one-line interpretation.

**Priority:** P0 (remove/replace empty tombstone section), P1 (readiness band + interpretation)

**Implementation complexity:** S (tombstone removal), S (readiness band)

**Regression risk:** Low — no downstream consumers of this page's state.

---

### Page 5: Decisions (Decisions.tsx)

**Score: 7.0/10**

**Biggest strengths:**
- The 3-column audit workstation is conceptually strong: Timeline → Decision Detail → Outcome + Pattern Context (Decisions.tsx:206–278).
- `DecisionsCalmCard` (Decisions.tsx:1108–1211) is exemplary — branches by priority, humanizes all states, avoids engineering speak.
- `humanReasoning` (Decisions.tsx:701–738) generates plain-English reasoning from structured data.
- Factor attribution mini-chart (Decisions.tsx:499–502) adds genuine signal.

**Biggest weaknesses:**
- The 3-column layout uses `h-[calc(100vh-240px)] min-h-[680px]` (Decisions.tsx:207). On mobile (≤768px) this collapses to single column via `grid-cols-1 xl:grid-cols-[...]` — but the columns all have `xl:overflow-y-auto` which means on desktop they scroll independently. Users may not discover that column 2 scrolls if column 1 is already scrolling the page.
- The "Start here" card (Decisions.tsx:103–135) adds good guidance but the same `u-card-tight` + ordered list pattern appears on Overview, Risk, and Ops — the experience becomes repetitive across all pages. This pattern needs to feel differentiated per page.
- The `EmptyFilter` function (Decisions.tsx:355–363) uses an emoji "🌱" — this violates the no-emoji discipline referenced in global instructions.

**Desktop-specific issues:**
- The column widths `360px_minmax(0,1fr)_420px` (Decisions.tsx:206) are fixed at 360px and 420px. At 1366px common laptop width with 220px sidebar, the available width is 1146px. Col 1 = 360px, Col 3 = 420px, Col 2 = 1146 - 360 - 420 - gaps = ~320px. That middle column (Decision Detail) is narrower than the outer columns.

**Mobile-specific issues:**
- On mobile, the 3-column grid collapses. The user first sees Timeline (Col 1), then if they click a row, they need to scroll far to see the Decision Detail (Col 2) and then scroll further for Pattern Context (Col 3). There is no scroll-into-view behavior on selection.
- Timeline filter buttons are small (`text-[11px]`) — this is below the 44px tap target in terms of text readability, though the button padding likely makes them tappable.

**Novice issues:**
- "Recovered" filter label (Decisions.tsx:37: `{ id: "replay", label: "Recovered" }`) is better than "replay" but a novice still doesn't understand what "recovered" means without tooltip context.

**Expert issues:**
- No date range filter or export functionality.
- Pattern context (Col 3) only compares same-engine same-regime peers — no cross-engine comparison.

**Storyline/navigation issues:**
- `PageChapter` is rendered at Decisions.tsx:88–90 inside a `picks-root picks-root-inline` wrapper. This is a structurally odd mix of two layout systems on the same page.

**Priority:** P1 (mobile scroll-into-view on selection), P0 (emoji removal), P2 (column width calibration)

**Implementation complexity:** S (emoji), M (mobile selection scroll)

**Regression risk:** Low for emoji fix. Medium for scroll behavior (affects keyboard navigation).

---

### Page 6: Strategies (StrategiesPage.tsx)

**Score: 6.5/10**

**Biggest strengths:**
- Phase 14f-E correctly collapsed the education list behind ExpertDetails (StrategiesPage.tsx:92–101). Repeat visitors no longer scroll through the same content.
- The h2 hierarchy fix is in place: `<h2 className="strategy-edu-title">` inside ExpertDetails (StrategiesPage.tsx:93) correctly follows h1.
- `NextStepCard` rationale is data-driven: mentions open trade count (StrategiesPage.tsx:109–111).
- `PAPER_ONLY_NOTE` disclaimer is used appropriately.

**Biggest weaknesses:**
- The page is composed of three opaque component imports: `TradeLifecycle`, `PremiumIncome`, `StrategyModules` (StrategiesPage.tsx:103–105). Without auditing those components, the page structure is a black box. From a regression standpoint, any of those three components could have independent layout, heading hierarchy, or mobile issues.
- The subtitle "How a signal becomes a trade · paper trading guidance" is functional but not compelling. Compare to Action Queue's "AI decision desk · N signals" which carries a real-time number. Strategies subtitle is static.
- `connectedStrategies` is defined (StrategiesPage.tsx:49) and appears in the `nowText` but there's no headline metric visible in the page header.

**Desktop-specific issues:**
- Three large component blocks (TradeLifecycle, PremiumIncome, StrategyModules) stacked vertically with no intermediate navigation or anchor. On a tall page this requires significant scrolling.

**Mobile-specific issues:**
- If TradeLifecycle or PremiumIncome render tables, they will need the same horizontal overflow treatment that Phase 13d applied to other tables.

**Novice issues:**
- Even with the ExpertDetails collapsed, a novice landing on Strategies sees three component blocks without knowing which to read first. There is no "Start here" guidance card (unlike Overview, Risk, Ops, Decisions which all have them).

**Expert issues:**
- No way to link a specific strategy template to a specific signal from the Action Queue.

**Storyline/navigation issues:**
- The page is in the "execution" section correctly. The NextStepCard points to Options, which is correct.

**Priority:** P1 (add Start-here guidance card for novices), P2 (dynamic subtitle)

**Implementation complexity:** S

**Regression risk:** Low — guidance card is additive.

---

### Page 7: Options (OptionsLayout.tsx + 12 sub-pages)

**Score: 4.5/10**

**Biggest strengths:**
- The OptionsOverviewPage landing (per its code) correctly redirects users from the chain density to a summary-first overview. Good UX intervention.
- `OptionsPaperOnlyBanner` and `OptionsDataAvailabilityBanner` are displayed at the top of every options page (OptionsLayout.tsx:10–15, 37–38), providing persistent disclaimers.
- `GuardrailsToggleButton` is available globally.

**Biggest weaknesses:**
- 12 tabs in a horizontal nav row (`TABS` in OptionsLayout.tsx:19–32) is overwhelming. At any viewport, this is 12 clickable items with labels like "Strategy Observatory," "Scenario Replay," "Decision Framing" — these are engineering terms disguised as tab labels.
- The tab nav uses `flex-wrap` (OptionsLayout.tsx:48) which means tabs overflow to a second line on smaller screens. The NavLink active state is a bottom amber border — this is inconsistent with the rest of the app which uses accent blue for active states.
- The OptionsLayout uses raw inline `p-4` Tailwind padding (OptionsLayout.tsx:36) and `space-y-3` — no picks-root / picks-frame / u-card system. This makes Options the most visually divergent section of the entire app.
- From the OptionsOverviewPage code (line 24 onward), the `_TAB_GUIDE` describes Chain as "Most beginners never need this" and Features as "Safe to ignore." If those tabs can be ignored, they should be hidden behind an "Advanced" toggle, not promoted to top-level tabs.

**Desktop-specific issues:**
- 12 tabs on desktop at 1440px minus 220px sidebar = 1220px for tab row. At ~80px per tab this works, but tabs like "Strategy Observatory" (21 chars) and "Decision Framing" will require wider cells, and the row may still wrap.
- Tab content height is unbounded — each sub-page determines its own layout without a shared container height. This creates jarring reflow as users switch tabs.

**Mobile-specific issues:**
- `flex-wrap` on the tab nav means 12 tabs wrap into 3-4 lines on a 390px viewport. The user has to scroll through the tab header before reaching the content. This is a P0 mobile failure.
- The `p-4` padding gives 16px on all sides on mobile, which is acceptable, but the header (`h1` at font-size `text-xl`) is not the standardized `picks-title` size.
- No drawer/accordion alternative for the tab nav on mobile.

**Novice issues:**
- Landing on `/options/overview` is the correct first step, but the 12-tab nav is immediately above the overview content, creating decision paralysis. Beginners will click random tabs (like "Chain" or "Decision Framing") and find dense data with no explanation.
- No "you probably don't need this" label on most sub-tabs from within the tab itself (only in the OverviewPage tab guide).

**Expert issues:**
- No keyboard navigation between tabs (standard keyboard Tab should move focus between NavLinks, but there is no roving tabindex or arrow-key navigation per the tab ARIA pattern).

**Storyline/navigation issues:**
- Options sits between Strategies and Portfolio in the FLOW. The `why` is "Construct and observe options trades in detail." But the Options section has 12 sub-tabs, many of which duplicate concepts from other pages (e.g., OptionsRiskDashboard vs /risk, OptionsPaperPerformance vs /portfolio). This redundancy dilutes the story.

**Recommended structural changes:**
- Collapse 12 tabs to 4-5 primary tabs: Overview, Paper Trades, Performance, Chain (Advanced), Risk (Advanced). Put the remaining 7 behind an "Advanced" toggle or a secondary tab group.
- Make tab nav a scrollable single-line row with horizontal overflow (not flex-wrap) on mobile.

**Priority:** P0 (mobile tab wrap), P1 (tab count reduction), P1 (visual consistency with rest of app)

**Implementation complexity:** M (tab reorganization), L (full visual port to picks-root system)

**Regression risk:** High — 12 sub-pages each with independent data and routing. Any layout change risks page-specific regressions. Test all 12.

---

### Page 8: Portfolio (PortfolioRouteSwitch → PortfolioTerminal / CopilotHoldings)

**Score: 6.5/10**

**Biggest strengths:**
- The route switch (PortfolioRouteSwitch.tsx:17–23) is clean and correctly reads `?view` from URL params. No state management needed.
- PortfolioTerminal handles the dual data stream (executed vs. strategy-log) with explicit separation to avoid the "0 trades" false positive (PortfolioTerminal.tsx comment at line 11).
- `CopilotHoldings` brief view uses a clean prose layout with `max-w-[1100px]` and sensible spacing.

**Biggest weaknesses:**
- There is NO visible UI affordance for switching between brief (`?view=brief`) and working (`?view=working`) views. A user landing on `/portfolio` gets PortfolioTerminal by default but cannot discover CopilotHoldings without knowing the URL param. This is a significant discoverability failure.
- `PortfolioTerminal.tsx` uses `PageGuide` / `AdvancedDetails` (novice components) but `CopilotHoldings.tsx` uses its own copilot token system (`--copilot-*` vars). The two views are built in different design systems with no visual consistency.
- The route default is still `PortfolioTerminal` (working view) despite the comment at PortfolioRouteSwitch.tsx line 8: "Phase F is when the default flips to brief." This flip has not happened yet — the dense terminal is still the default.

**Desktop-specific issues:**
- PortfolioTerminal.tsx (line 32 onward) mixes `usePaperSummary`, `usePaperTrades`, `usePerformance`, `useCurrentState`, `usePaperEquity`, `useExecutedSummary`, `useExecutedTrades`, `useExecutedPositions` — 8 concurrent data fetches on page load. If any one is slow, portions of the page show "—" indefinitely with no consolidated loading state.

**Mobile-specific issues:**
- PortfolioTerminal is built as a "trading terminal" — by definition it's a desktop-first experience. The NAV strip with 5 columns (`gridTemplateColumns: "2.2fr 1fr 1fr 1fr 1fr"`) will overflow on mobile.
- `CopilotHoldings` with `max-w-[1100px] px-6` gives appropriate mobile padding but the `PositionStoryCard` components inside may have their own desktop-first assumptions.

**Novice issues:**
- Both views exist but novices land on PortfolioTerminal (the dense one) by default. The "Phase F flip" should be prioritized.

**Expert issues:**
- No CSV export of positions or P&L in either view.

**Storyline/navigation issues:**
- Portfolio's NextStep points to `/risk`. The Risk page is the natural continuation. This is correct.

**Priority:** P0 (view toggle discoverability — add a visible tab/toggle), P1 (flip default to brief view), P1 (loading state consolidation)

**Implementation complexity:** S (view toggle UI), S (default flip), M (loading state)

**Regression risk:** Medium — default flip changes what all users see first; brief the QA process.

---

### Page 9: Risk Dashboard (RiskDashboard.tsx)

**Score: 6.0/10**

**Biggest strengths:**
- Honest mark handling: `markUnavailable` flag (referenced at RiskDashboard.tsx:27+) prevents fabricated $0 values.
- PageGuide with plain-English subtitle present.
- "Start here" focus card directs users to Account value → Percent invested → Biggest drop.
- `InsightDrawer` for narrative generation is operator-gated (not auto-fetched), which is correct.

**Biggest weaknesses:**
- `AdvancedDetails label="Where this data comes from"` (RiskDashboard.tsx:107) contains raw SQL: `paper_equity_snapshot.positions_value`. This is appropriate for technical transparency but should be gated or styled differently from the novice-facing content.
- The "Generate explanation" button (RiskDashboard.tsx:124–133) uses `rounded border border-b1 px-2 py-1 text-[11px]` inline Tailwind. At 11px the button text is below accessible size. This button is non-standard compared to the rest of the app.
- The replay checkbox toggle (RiskDashboard.tsx:116–123) is a raw `<input type="checkbox">` without custom styling — it will render as a native OS checkbox, inconsistent with the rest of the app's design system.

**Desktop-specific issues:**
- `max-w-[1480px]` container with the 220px sidebar leaves 1260px max for content — appropriate.
- The page uses `space-y-5` between cards, which is consistent with the u-card system.

**Mobile-specific issues:**
- The controls row (replay checkbox + generate button) at RiskDashboard.tsx:115 uses `flex-wrap items-center justify-end gap-3`. On mobile this should align correctly, but the visual hierarchy puts these controls AFTER the AdvancedDetails expander, meaning a mobile user scrolling down hits the raw SQL expander before the controls.
- Native checkbox on mobile has an OS-specific appearance that may be undersized for touch.

**Novice issues:**
- "Biggest drop from peak" is a novice-friendly term but "max drawdown" appears nowhere, which is good. However the actual displayed drawdown metric (from `fmtPct(summary?.max_drawdown_pct)`) may show a large negative number without context for whether that's normal.

**Expert issues:**
- No sector-level or strategy-level concentration breakdown visible at page-level (likely in subcomponents).
- The "Generate explanation" narrative feature is on Risk but not other pages where it would also be useful (e.g., Decisions, Action Queue).

**Storyline/navigation issues:**
- PageChapter is wired (`pathname="/risk"`) and NextStep points to `/research`. Correct.

**Priority:** P1 (checkbox styling), P1 (generate button size), P2 (SQL in AdvancedDetails formatting)

**Implementation complexity:** S

**Regression risk:** Low — styling changes only; no data logic affected.

---

### Page 10: Alpha Lab (ResearchLab.tsx)

**Score: 5.5/10**

**Biggest strengths:**
- The 4-tab structure (Signals, Top Wins, Top Losses, Patterns) is appropriate scope.
- The `u-lab-chip` "experimental" badge (ResearchLab.tsx:39) correctly labels the page's status.
- PageChapter is wired.

**Biggest weaknesses:**
- ResearchLab.tsx uses the `max-w-[1440px] mx-auto px-6 py-6` Tailwind layout, not the `picks-root` / `picks-frame` pattern used by the primary pages. The page header uses `u-lab-mode` + `u-title-lg` — a different visual system. This creates visible inconsistency: tab buttons here use `px-4 py-2.5 text-[13px] border-b-2` while Options tabs use `px-3 py-1 text-sm`. Neither uses the standardized FilterBar pattern from ActionQueue.
- The tabs have no `aria-selected`, no `role="tab"`, no `role="tablist"`. These are `<button>` elements acting as tabs — an accessibility gap.
- From the code comments: "No empty states." But if `useShadowSignals` returns nothing (no data), the SignalsTab presumably renders an empty container.

**Desktop-specific issues:**
- The header has `flex items-start justify-between` with only the left side populated (ResearchLab.tsx:35–47) — the right side is empty. This creates an odd asymmetry at wide viewports.

**Mobile-specific issues:**
- Tab buttons with `px-4 py-2.5` and labels like "Top Wins" and "Top Losses" should be 44px-tall enough, but the font is `text-[13px]` which may be readable at arm's length.
- The `mb-6` spacer div after the nav (ResearchLab.tsx:64) is 24px — combined with the tab nav, there's a lot of empty space before content on mobile.

**Novice issues:**
- No "What is Alpha Lab?" explanation. The subtitle "Observatory for candidate signals, winning/losing pattern mining, and ideas under evaluation" uses "candidate signals" and "pattern mining" which are expert terms.
- No connection between Alpha Lab content and the Action Queue or Decisions page — a novice doesn't know how shadow signals relate to their live recommendations.

**Expert issues:**
- The tabs show derived data (wins, losses, patterns) but there is no ability to filter by date range, regime, or engine.

**Priority:** P1 (add role="tablist"/role="tab" accessibility), P2 (visual consistency with rest of app)

**Implementation complexity:** S (ARIA), M (visual port)

**Regression risk:** Low

---

### Page 11: Ops (Ops.tsx)

**Score: 6.0/10**

**Biggest strengths:**
- UX-1 Commit I correctly reframes "Ops" as "System status" for novices (Ops.tsx:53–69).
- The `deriveOpsCalm` function (referenced at Ops.tsx:43) provides a single-chip health summary.
- The `PageGuide` subtitle "Most users do not need to read this page — it exists for transparency" is honest and appropriately discouraging for novices.

**Biggest weaknesses:**
- Ops.tsx imports 16 card components (Ops.tsx:21–36): MLResearchCard, HistoricalReplayCard, ReplayTrainingReadinessCard, ShadowMLCard, ShadowStrategyCard, EngineBTransitionCard, B2vsV2ComparisonCard, V2PromotionTriggerCard, HybridAdvisorCard, HybridReadinessCard, DailyLoopHealthCard, MLReadinessProgressCard, SystemHealthCard, SystemImprovementsCard, SystemAdjustmentsCard, ContextAdjustmentsCard. This is 16 independent components on one page with no hierarchy, no grouping, and no way to scan what matters.
- The page is 80 lines of preamble (PageGuide, Start-here card, calm-state) before the first actual operational content. That's appropriate framing but it's 3+ screens of scrolling to reach the operational cards.
- No collapse mechanism for inactive cards. A card that shows "not yet active" or "training ready: false" still occupies full card space.

**Desktop-specific issues:**
- `max-w-[1440px] px-8 py-8 space-y-6` with 16 cards stacked vertically is a very tall scroll page on desktop.

**Mobile-specific issues:**
- 16 cards on mobile requires extensive scrolling. The Start-here card and PageGuide take up the first 3-4 screens. The operational cards don't appear until ~800px of scroll.
- Each card's internal layout is determined by its own component — mobile behavior is unaudited.

**Novice issues:**
- Even with the "most users don't need this" disclaimer, the 16 cards visible once the user scrolls create a false sense that they must understand all of them.

**Expert issues:**
- No way to pin or collapse individual cards. No page-level health badge visible in the TopStrip that would tell experts "Ops has 2 degraded cards" without visiting the page.

**Storyline/navigation issues:**
- Ops is the last page in the FLOW chain (no `next` defined in FLOW). The NextStepCard renders null. This is correct behavior but the page ends abruptly — no "return to Overview" or "you're up to date" closure.

**Priority:** P1 (add section grouping for 16 cards), P2 (end-of-flow closure card)

**Implementation complexity:** M (card grouping), S (closure card)

**Regression risk:** Low — purely additive layout.

---

## A. Cross-Product Findings

### Design System Inconsistencies

1. **Two layout systems in active use:** The "picks-*" system (picks-root, picks-frame, picks-title, picks-header, picks-subtitle) used by Overview/Events/ActionQueue/SignalLab/Strategies and the "u-card / max-w-[...] mx-auto" Tailwind system used by Overview.tsx/Decisions/Risk/AlphaLab/Portfolio/Ops. Options uses neither — it uses raw `space-y-3 p-4` Tailwind. A user navigating across these pages notices three different layout densities and typography scales.

2. **Tab pattern inconsistency:** ActionQueue uses FilterBar with styled filter buttons; Alpha Lab uses `border-b-2` tab buttons; Options uses NavLink-based tabs with amber border. These are three different tab implementations for the same UI pattern.

3. **Loading state inconsistency:** ActionQueue has an explicit skeleton loader. SignalLab shows "Loading…" text. Overview.tsx shows nothing (hooks load async). EventsResearchPage has no loading indicator. No unified skeleton/spinner pattern.

4. **Typography inconsistency:** picks-title uses `clamp(28px, 3.4vw, 36px)` while Overview.tsx uses `u-title-lg` (CSS-defined). Options h1 uses `text-xl font-semibold`. Risk uses `PageGuide` title. Four different heading presentations for page-level h1.

5. **Inline style overrides:** Multiple pages use `style={{ padding: "12px 16px" }}` and similar inline styles (Overview.tsx:101, Decisions.tsx:109, RiskDashboard.tsx:75). These break the token system and make global density or theme changes harder.

### Navigation Inconsistencies

- `PageChapter` appears on 9 of 11 pages — missing from Options (nested routes don't use it) and PortfolioTerminal (uses its own heading system).
- `NextStepCard` appears on 6 of 11 pages — missing from Overview.tsx, PortfolioTerminal, RiskDashboard (it has it via PageChapter NEXT cell, not NextStepCard), AlphaLab, Ops.

### Accessibility Gaps

- Alpha Lab tabs lack `role="tablist"` / `role="tab"` / `aria-selected`.
- Options tab nav uses NavLink which renders as `<a>` elements — semantically correct for page navigation but the pattern is not a tab panel, it's a navbar. No `aria-current="page"` on the active link.

---

## B. Elite-Gap Analysis

The platform has made genuine progress toward "world-class" since Phase 12. The honest-data discipline is excellent. The calm-state interpretation pattern is genuinely innovative. The PageChapter narrative rail is a strong IA concept.

What keeps it from elite status right now:

1. **No unified design language.** Bloomberg Terminal has a single visual grammar. Linear has one. This app has three (picks-*, u-card, copilot-*). Until they merge, the app feels like three different products stitched together.

2. **Options is the weak link.** 12 tabs with engineering labels, amber active borders, raw Tailwind padding — it reads like a separate prototype. For a platform positioning toward "premium AI-native investing OS," Options is a liability.

3. **Mobile is functional but not polished.** The shell drawer, tap targets, and sticky behavior are all wired. But the actual page content (tables, NAV strips, 5-column grids) is still desktop-first. The picks-frame padding works; the data layouts inside don't always reflow gracefully.

4. **Signal Lab has a visible tombstone.** "Not yet wired" on a user-facing page at SignalLabPage.tsx:174 is a production smell that reduces trust. Elite products don't show their backlog.

5. **Dual-overview problem.** Two "Overview" experiences with no toggle between them is a navigational defect. Until the route architecture is resolved (via explicit view toggle or consolidation), the navigation story breaks at the very first page.

6. **Loading state poverty.** ActionQueue's skeleton is excellent. The rest of the app doesn't have it. Blank or "Loading…" loading states feel unfinished next to the polished skeleton.

---

## C. Final Ranked Roadmap

### Phase 15 (Ship first — highest UX impact, lowest regression risk)

| # | Item | Impacted Pages | Priority | Complexity | Regression |
|---|------|---------------|----------|------------|-----------|
| 1 | Remove "Not yet wired" tombstone from Signal Lab | Signal Lab | P0 | S | Low |
| 2 | Fix mobile Options tab nav (horizontal scroll instead of flex-wrap) | Options | P0 | S | Low |
| 3 | Remove emoji from Decisions EmptyFilter | Decisions | P0 | S | Low |
| 4 | Add visible view toggle on Portfolio (brief ↔ working) | Portfolio | P0 | S | Low |
| 5 | Flip Portfolio default to brief (CopilotHoldings) | Portfolio | P1 | S | Medium |
| 6 | Add loading skeleton to Events & Catalysts | Events | P1 | S | Low |
| 7 | Add readiness score interpretation band to Signal Lab (0-40/41-70/71-100) | Signal Lab | P1 | S | Low |
| 8 | Reorder launcher cards on PicksPage to match page_flow.ts order | Overview | P1 | S | Low |
| 9 | Style the Risk replay checkbox to match app design system | Risk | P1 | S | Low |
| 10 | Add `role="tablist"` / `role="tab"` / `aria-selected` to Alpha Lab | Alpha Lab | P1 | S | Low |

### Phase 16 (High ROI, medium risk)

| # | Item | Impacted Pages | Priority | Complexity | Regression |
|---|------|---------------|----------|------------|-----------|
| 1 | Reduce Options tabs from 12 to 5 primary + "Advanced" overflow | Options | P1 | M | High |
| 2 | Unify loading pattern: extend skeleton from ActionQueue to all pages | All | P1 | M | Medium |
| 3 | Port Options to the picks-root / picks-frame visual system | Options | P1 | L | High |
| 4 | Add section grouping to Ops (group 16 cards into 4 sections) | Ops | P1 | M | Low |
| 5 | Consolidate Overview route (add "Switch to working view" on PicksPage) | Overview | P1 | M | Medium |
| 6 | Add "Start here" guidance card to Strategies page (like Overview/Decisions/Risk/Ops) | Strategies | P1 | S | Low |
| 7 | Fix Decisions 3-col layout: Col 2 (detail) should be widest, not narrowest | Decisions | P1 | S | Low |
| 8 | Calibrate Overview.tsx right column (5 cards in 30% width) | Overview (working) | P1 | M | Medium |

### Phase 17 (Polish — lower urgency, higher complexity)

| # | Item | Impacted Pages | Priority | Complexity | Regression |
|---|------|---------------|----------|------------|-----------|
| 1 | Merge picks-* and u-card systems into one canonical layout | All | P2 | XL | Very High |
| 2 | Unify tab/filter component across ActionQueue, AlphaLab, Options | Multiple | P2 | L | High |
| 3 | Add scroll-into-view on Decisions timeline selection (mobile) | Decisions | P2 | M | Medium |
| 4 | Add end-of-flow closure card on Ops | Ops | P2 | S | Low |
| 5 | Mobile-responsive NAV strip in Overview.tsx (stacked layout) | Overview (working) | P2 | M | Medium |
| 6 | Catalyst-to-signal linking (Events → Action Queue by symbol) | Events | P2 | L | Medium |

---

## Answers to the 12 Specific Questions

1. **Coherent story page-to-page?** Partially. The PageChapter rail creates a narrative thread but the launcher order on PicksPage contradicts the page_flow.ts order. The dual-overview split breaks coherence at page 1.

2. **Navigation linear/intelligent?** The SideNav hotkeys and "next" indicator (SideNav.tsx:68–72) are genuinely helpful. The FLOW definition in page_flow.ts is the right architecture. But the launcher card ordering (PicksPage.tsx:207–240: action-queue → events → strategies → portfolio) diverges from that FLOW.

3. **Natural Overview → Catalysts → Decisions → Execution → Portfolio → Risk flow?** Yes, with the caveat that Overview and Overview.tsx are two different pages. The single-page PicksPage launcher hits: signals → catalysts → strategies → portfolio (skipping decisions). A user would need to visit Action Queue → Signal Lab → Decisions separately.

4. **Dead pages?** Signal Lab feels dead due to the "not yet wired" backtest section. Events & Catalysts feels passive — it shows data but gives no guidance on what to do with it.

5. **Sections that should become collapsible?** On Overview.tsx: the "Start here" card (already collapsible would be better than always-visible). The 16 Ops cards should be grouped and collapsible by group. Signal Lab's empty backtest section should be collapsed/hidden until wired.

6. **Sections that should become sticky?** The FilterBar on ActionQueue should be sticky on scroll (it's the primary navigation control for a long list). The Options tab nav should be sticky within the /options/* routes.

7. **Visually noisy cards?** The "System diagnostics" AdvancedDetails in Overview.tsx (chips, regime badge, gates count, strategy chip, pipeline chip, last-activity timestamp, all on one row) is the most visually noisy section. The Decisions truth-banner row (multiple chips with dots, all inline) also reads as noisy.

8. **Under-emphasized cards?** The NextStepCard bottom CTA is under-emphasized — it sits after the disclaimer footer styling and can be missed. The `CopilotHoldings` brief view is entirely hidden without URL param knowledge.

9. **Wasted vertical space?** The `mb-6` spacer div in Alpha Lab (ResearchLab.tsx:64) is unnecessary. The `pt-2` section anchors in Overview.tsx ("Today's numbers", "Charts & insights", "Recent activity") add whitespace that could be replaced by visual hierarchy in the sections themselves.

10. **Too-dense sections?** The Options tab nav (12 items) and the Ops page (16 cards without grouping) are the two densest surfaces. The Decisions 3-col layout at 1366px has a very narrow middle column.

11. **Mobile-broken pages?** Options tab nav (flex-wrap → multi-line) is closest to "broken." Overview.tsx's 5-column NAV strip doesn't reflow on mobile. The Decisions 3-col grid collapses correctly but loses the split-column scrolling affordance.

12. **Developer-built pages?** Options (raw Tailwind, amber border tab active state, no picks-root), Alpha Lab (different tab style, no PageChapter integration), and Signal Lab (tombstone "not yet wired" section) read as developer-built. Risk (native checkbox, 11px button) has localized developer-built elements.
