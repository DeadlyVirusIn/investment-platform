# Phase 15 Elite UX Debate — Round 2 (Sonnet / Pragmatic Implementer)

**Perspective:** Pragmatic Implementer — rebuttal lens, effort estimates, regression risk, shortest path to max impact.

---

## 1. Convergence — What All Four Panelists Agree On

Every panelist reached the same five conclusions independently. These are load-bearing consensus items that should be treated as unambiguous Phase 15 mandates:

1. **Options 12-tab nav is the single biggest UX failure.** All four named it P0 or equivalent. The code is confirmed: `OptionsLayout.tsx:48` uses `flex-wrap` with no overflow-x; 12 tabs at 375px wraps to 4+ rows. No dispute.
2. **JobRow statuses are hardcoded.** `Ops.tsx:263-266` — `last="ok"` and `last="skipped"` are string literals, not derived from any hook. Opus and I both flagged this P0; Codex flagged it P1. It is a truth violation.
3. **Signal Lab's "Backtest validation — Not yet wired" section** is a tombstone that belongs behind a collapse or off the page entirely. Confirmed at `SignalLabPage.tsx:173-183`.
4. **Three coexisting design systems** (picks-root, u-card/Tailwind, Options zinc-*) make the app read as three stitched products.
5. **Portfolio default should flip to brief view.** The comment at `PortfolioRouteSwitch.tsx:6` says "Phase F is when the default flips to brief." Phase F has not shipped. All four flagged this. It is an S-complexity, Medium-risk flip.

---

## 2. Divergence — Where Panelists Split, and My Position

### 2a. Signal Lab Score: 5.0 (me, Round 1) vs 5.4 (Opus) vs 6.7 (Codex) vs 5.0 (Gemini)

Codex scored Signal Lab 6.7 because it emphasized the structural improvements (FetchError, density, ExpertDetails, NextStepCard all wired correctly per `SignalLabPage.tsx:63-75`). That's a fair reading of the implementation quality. But from a user-facing product perspective, the tombstone section at line 173 dominates the lower half of the page on any viewport, and the score should reflect user experience, not implementation completeness. **I hold 5.0. The tombstone is a production smell regardless of what else is correctly wired.**

### 2b. Events Score: 5.5 (me), 5.5 (Opus) vs 6.5 (Gemini) vs 7.0 (Codex)

Codex gave Events 7.0, citing strong state management and honest PageChapter wiring. Gemini gave 6.5. Opus and I gave 5.5. The divergence is explained by what each panelist weighted. Codex weighted structural integrity; we weighted user value. The confirmed fetch-error swallow at `EventsResearchPage.tsx:27` — `.catch(() => { if (!cancelled) setLoading(false); })` — is a real trust issue, not a style concern. A backend failure renders as an identical "empty day" to a legitimate zero-catalyst day. **This is a P0 truth violation per the brief's "no fakes by omission" rule.** Events score should not be above 6.0 until this is fixed.

### 2c. Gemini's Serif Proposal (Source Serif 4 for AI narrative blocks)

Gemini proposed adding Source Serif 4 for PageChapter, Calm Cards, and Copilot stories. **I push back on this hard.** Effort is M-L (add font file, update CSS variables, test font loading on mobile, verify dark/light parity across tokens). Regression risk is Medium — the `--font-ui: 'Inter', …` token in `index.css` feeds everything; any fork risks inconsistency at surfaces that were not explicitly updated. More importantly, the brief says "no atmospheric visuals that reduce information clarity." A serif font in an AI-narrative block is atmospheric in exactly that sense — it aestheticizes a data-derived sentence rather than making the data clearer. Opus specifically said "one typeface, one scale" as an elite requirement. **My position: stick with Inter. The clarity gap is microcopy, not typography.** This item should not enter Phase 15 or 16.

### 2d. Opus's "Persistent AI assistant rail" (Phase 17)

Opus proposed a persistent AI assistant drawer that refuses to answer when data is stale. I agree with the intent and the Phase 17 timing. But Opus underestimated effort: this is not an L, it is an XL. The InsightDrawer pattern (`RiskDashboard.tsx:31-38`) already exists as a precedent — but that is page-scoped and operator-triggered. A persistent global rail requires: (1) cross-page context assembly, (2) stale-data gating per the `useFetchWithError` pattern applied globally, (3) a new UI shell slot that doesn't conflict with the SideNav/TopStrip sticky stack, and (4) a disambiguation layer so the AI knows which page's data is "current." **Mark effort as XL, regression risk High. Don't start this until the three-design-system problem is resolved in Phase 16.**

### 2e. Action Queue FilterBar ordering (my Round 1 finding)

I flagged that the FilterBar sits above the "Why no buys?" panel in JSX (ActionQueuePage.tsx:139–170), creating a logical ordering problem. Opus, Gemini, and Codex each mentioned the FilterBar but none called out this specific ordering defect. I re-read the code and I'm right: the FilterBar renders first, then the no-buys panel renders. When all-filter is applied and there are no results, the explanation appears below the filter that caused the absence — it should be inline contextual, not below. **This is still a legitimate P1 fix, effort S, regression Low.**

---

## 3. Concessions — Where I Was Wrong or Missed Something

### 3a. Concede to Opus: Alpha Lab fallback registry is a truth violation, not just a visual gap

In my Round 1 I scored Alpha Lab 5.5 and classified the fallback as a "visual inconsistency." Opus correctly elevated this to a P0: `ResearchLab.tsx:85-128` renders four hardcoded `ShadowSignal` entries with `value_display: "Phase X FAIL"` in containers that are visually identical to live data. The conditional at line 128 is `(shadow && shadow.length > 0) ? shadow : knownSignals` — the user cannot tell from the UI whether they're looking at live results or a hardcoded baseline. I understated this. **Concede to Opus. Alpha Lab P0 for fallback labeling, not P2.**

### 3b. Concede to Codex: Overview query-param gallery is a structural problem, not just P2

In Round 1 I labeled the dual-overview (PicksPage vs Overview.tsx) as P2 complexity. Codex correctly pointed out that `OverviewRouteSwitch.tsx:35-46` preserves seven query-param variants — `working`, `stream`, `conviction`, `copilot`, `living`, `legacy`, and default. While these are mostly research/archive variants, any user who arrives from a shared link hits a completely different page than the default, without any UI signal that they're in a non-canonical view. This is a real navigation coherence issue. **Concede to Codex. The OverviewRouteSwitch should at minimum surface a "you are in advanced view" banner for non-default variants. Effort S, regression Low.**

### 3c. Concede to Opus: Decisions breakpoint `xl` → `lg` is a trivial fix I under-prioritized

Decisions.tsx:207 uses `xl:grid-cols-[360px_minmax(0,1fr)_420px]` — at `xl` (1280px+), the three columns activate. But 1024-1280px users (common laptop widths) get the full single-column linear stack. Opus correctly flagged this as a one-line change (`xl:` → `lg:`) with major mobile/tablet impact. I put this as P2 in my table. **Concede: this is P1, effort S (one CSS class change), regression Low. It should be in Phase 15.**

---

## 4. What All Four Panelists Collectively Underweighted

### 4a. GuardrailsToggleButton is unverified — but the risk is asymmetric

Opus raised that `GuardrailsToggleButton` (`OptionsLayout.tsx:44-46`) may be UI-only and not actually filter data. None of us verified this by reading the component implementation. From an implementer standpoint: **if this button doesn't do anything, it must be removed or labeled "visual only" before Phase 15 ships.** A toggle that looks functional but isn't is a fakes-by-UI violation. Effort S to verify; effort S to remove if unwired.

### 4b. No panelist addressed the DensityToggle false affordance rigorously enough

Opus called it out most clearly: Events, Signal Lab, and Strategies all render a DensityToggle that does nothing visible. This is a false affordance — a control that appears to have an effect but doesn't. All four of us mentioned this but none put it as P0. **From a trust standpoint this is P0-level:** the brief says preserve density modes, and the implication is that the toggle is functional everywhere it appears. Hiding the toggle from non-density-sensitive pages is an S-complexity fix (add a `showDensity` prop or conditional render) with zero regression risk. This should be in Phase 15, not Phase 16.

### 4c. `PageChapter` missing from PortfolioTerminal — bigger impact than scored

Multiple panelists noted this in passing. But the severity was understated: Portfolio is the highest-trust page (real paper-trade data, honest marks). A user who lands on `/portfolio` directly (the default) gets PortfolioTerminal with no PageChapter narrative rail. They have no "NOW / WHY / NEXT" context and no `NextStepCard` pointing to Risk. The journey breaks here. Adding `PageChapter` to PortfolioTerminal is S-complexity, Low regression — it's a purely additive import.

---

## 5. Refined Per-Page Scores (Round 2)

| # | Page | R1 Score | R2 Score | Justification |
|---|------|----------|----------|---------------|
| 1a | Overview (PicksPage) | 7.5 | 7.5 | Multiple competing heroes remain; launcher order mismatch with page_flow.ts unresolved. |
| 1b | Overview.tsx (working) | 7.0 | 7.0 | NAV strip mobile overflow unchanged; no PageChapter/NextStepCard. |
| 2 | Events & Catalysts | 5.5 | 5.0 | Downgraded: P0 fetch-error swallow at line 27 is a truth violation; density toggle non-functional. |
| 3 | Action Queue | 8.0 | 8.0 | Strongest page; FilterBar ordering defect is real but minor at this score level. |
| 4 | Signal Lab | 5.0 | 5.0 | Tombstone section confirmed at line 173; readiness score without calibration band. |
| 5 | Decisions | 7.0 | 7.0 | `xl:` → `lg:` breakpoint is a P1 fix that raises this score to 7.5 once shipped. |
| 6 | Strategies | 6.5 | 6.5 | Three opaque component imports create an auditing/regression black box. |
| 7 | Options | 4.5 | 4.5 | 12-tab flex-wrap is a confirmed mobile failure; amber active border is a confirmed design-system divergence. |
| 8 | Portfolio | 6.5 | 6.5 | Phase F flip not shipped; `?view=brief` not discoverable; PortfolioTerminal has no PageChapter. |
| 9 | Risk | 6.0 | 6.0 | 11px "Generate explanation" button and native OS checkbox are confirmed implementation gaps. |
| 10 | Alpha Lab | 5.5 | 5.0 | Downgraded: conceding to Opus that the fallback registry is P0 truth violation, not visual gap. |
| 11 | Ops | 6.0 | 5.5 | Downgraded: hardcoded JobRow `last="ok"` at lines 263-266 is a confirmed P0 trust violation. |

---

## 6. Refined Phase 15/16/17 Roadmap

Reorganized after reading all four panelists. Phase 15 is the "truth + S-complexity" phase — every item here is either a P0 honesty fix or an S/M effort with Low regression risk. No item in Phase 15 should touch the three-design-system problem (that is Phase 16-17 work).

### Phase 15: Truth + Quick Wins (target: all S-complexity, max 2 M-complexity items)

| # | Item | File:line | Effort | Regression | Priority |
|---|------|-----------|--------|------------|---------|
| 1 | Fix hardcoded `JobRow` statuses OR add ExpertDetails label "(static placeholder)" | `Ops.tsx:263-266` | S | Low | P0 |
| 2 | Label Alpha Lab fallback registry with "Static registry baseline — no live signals this cycle" pill | `ResearchLab.tsx:128` | S | Low | P0 |
| 3 | Restore fetch-error display on Events page (use existing FetchError component) | `EventsResearchPage.tsx:27` | S | Low | P0 |
| 4 | Remove/replace Signal Lab tombstone section (hide behind ExpertDetails or true empty state) | `SignalLabPage.tsx:170-183` | S | Low | P0 |
| 5 | Fix Options tab nav: `flex-wrap` → `overflow-x-auto` single-row on mobile | `OptionsLayout.tsx:48` | S | Low | P0 |
| 6 | Add view toggle (Brief / Working) as visible UI element on Portfolio | `PortfolioRouteSwitch.tsx` | S | Low | P0 |
| 7 | Hide DensityToggle on pages where it has no visible effect (Events, Signal Lab, Strategies) | Multiple pages | S | Low | P0 |
| 8 | Verify GuardrailsToggleButton wiring; remove or label if UI-only | `OptionsLayout.tsx:44-46` | S | Low | P0 |
| 9 | Add readiness score interpretation band (0-40 red, 41-70 amber, 71-100 green) | `SignalLabPage.tsx` | S | Low | P1 |
| 10 | Add `PageChapter` + `NextStepCard` to PortfolioTerminal | `PortfolioTerminal.tsx` | S | Low | P1 |
| 11 | Flip Decisions `xl:grid-cols` → `lg:grid-cols` for 3-col layout | `Decisions.tsx:207` | S | Low | P1 |
| 12 | Remove 🌱 emoji from Decisions EmptyFilter | `Decisions.tsx:355-363` | S | Low | P0 |
| 13 | Add `role="tablist"` / `role="tab"` / `aria-selected` to Alpha Lab tab nav | `ResearchLab.tsx:50-62` | S | Low | P1 |
| 14 | Style Risk "Generate explanation" button and `includeReplay` checkbox to match design system | `RiskDashboard.tsx:115-133` | S | Low | P1 |
| 15 | Add "you are in advanced view" banner on non-default OverviewRouteSwitch variants | `OverviewRouteSwitch.tsx` | S | Low | P1 |
| 16 | Reorder PicksPage launcher cards to match page_flow.ts order | `PicksPage.tsx:201-241` | S | Low | P1 |
| 17 | Flip Portfolio default to brief (`CopilotHoldings`) per Phase F spec | `PortfolioRouteSwitch.tsx:22` | S | Medium | P1 |
| 18 | Add skeleton loader to Events page (matches ActionQueue skeleton pattern) | `EventsResearchPage.tsx` | M | Low | P1 |

### Phase 16: Coherence + Options Consolidation (M/L complexity, must not start before Phase 15 complete)

| # | Item | Effort | Regression | Note |
|---|------|--------|------------|------|
| 1 | Options tabs 12 → 4-5 (Overview / Trades+Risk / Strategy Lab / Advanced) | L | High | Test all 12 sub-pages independently after. |
| 2 | Migrate Options to picks-root / `--pi-*` tokens, drop zinc hardcodes | L | High | Do after tab consolidation, not before. |
| 3 | Expand ExpertDetails to Decisions diagnostics, Risk full breakdowns, Ops ML/replay cards | M | Low | Additive — no data logic change. |
| 4 | Group Ops 16 cards into 4 collapsible sections | M | Low | Purely additive layout. |
| 5 | Group-level rationale on Action Queue (most common tags per action group) | M | Medium | Touches ActionQueue card rendering logic. |
| 6 | Unify loading pattern: add skeletons to Options overview, Portfolio, Risk | M | Medium | Use ActionQueue skeleton as the template. |
| 7 | Add "Catalyst brief" summary header to Events (top 3 catalysts + affected symbols) | M | Low | New component, no existing logic changed. |
| 8 | Decisions design-system: migrate body to picks-root frame (keep PageChapter) | L | Medium | Many test selectors depend on Decisions layout. |

### Phase 17: Polish + AI-Native Moments (XL complexity, only after Phase 16 land)

| # | Item | Effort | Regression | Note |
|---|------|--------|------------|------|
| 1 | Merge picks-* and u-card into one canonical layout | XL | Very High | This is the whole design system. Don't rush. |
| 2 | Add "what changed since last visit" temporal pills across pages | L | Medium | Requires per-session state (localStorage or sessionStorage). |
| 3 | Persistent AI assistant drawer (scoped to current page data, stale-gated) | XL | High | Must wait for design-system unification. |
| 4 | Mobile-native IA re-architecture (portfolio widget, swipe-between-chapters) | XL | High | Requires Phase 16 Options collapse first. |
| 5 | Single motion vocabulary (define `--motion-fast`, `--motion-base` tokens) | M | Low | Safe standalone; do in parallel with Phase 17. |

---

## 7. Re-Answering the 12 Brief Questions (Updated)

1. **Coherent story page-to-page?** Mostly yes from Overview → Action Queue → Signal Lab → Decisions. Breaks at Portfolio (no PageChapter/NextStepCard on PortfolioTerminal) and at Options (which is its own mini-app). The PageChapter + NextStepCard infrastructure works when applied; the gap is incomplete adoption.

2. **Navigation linear/intelligent or fragmented?** SideNav FLOW metadata is excellent. In-page navigation is fragmented across four systems (FilterBar aria-pressed, Decisions custom inline onClick, Options NavLink, Alpha Lab raw buttons). The shell nav is 8/10; in-page nav is 4/10.

3. **Natural guided flow?** The `page_flow.ts` encoded flow is coherent. The PicksPage launcher order (action-queue → events → strategies → portfolio) contradicts it, confirmed at `PicksPage.tsx:201-241`. Fix the launcher order and 80% of the flow coherence issue resolves.

4. **Dead/passive pages?** Signal Lab (tombstone section), Events (no curation layer, feed dump), Alpha Lab (worksheet feel + static fallback). These three are the "dead zone" cluster.

5. **Sections to collapse?** Ops 16 cards (group into sections), Decisions "How to read" (auto-close after first visit), Risk 5-layer header (merge into single RiskHeader), Signal Lab backtest section (full removal until wired), Alpha Lab static registry (label or hide).

6. **Sections to make sticky?** Options tab nav (single-row with overflow-x once flex-wrap is fixed), Action Queue FilterBar (sticky on long scroll), Decisions Timeline column at lg+. NOT the Risk controls row — it's secondary to the table content.

7. **Visually noisy cards?** PortfolioSnapshot 8-12 metric grid (confirmed at `PortfolioSnapshot.tsx:98-160`), Ops 16-card dump, Options Risk 4-KPI cards with no visual hierarchy.

8. **Under-emphasized?** "Generate explanation" on Risk (11px button confirmed at `RiskDashboard.tsx:124-132`), CopilotHoldings brief view (URL-only access confirmed at `PortfolioRouteSwitch.tsx:21`), the SideNav next-step chip (9px text per `SideNav.tsx:69-72` is real but functionally effective — don't over-engineer this one).

9. **Wasted vertical space?** Signal Lab tombstone section (280px+ of empty content area), Ops preamble (80 lines of PageGuide + start-here before first operational card), Alpha Lab `mb-6` spacer at `ResearchLab.tsx:64`.

10. **Too dense?** Options chain table, PortfolioTerminal 5-column NAV strip (will overflow mobile), Decisions 3-column at sub-xl widths (fixed by `xl:` → `lg:` change).

11. **Mobile-broken pages?** Options tab nav is the worst confirmed case. PortfolioTerminal NAV strip (`gridTemplateColumns: "2.2fr 1fr 1fr 1fr 1fr"` inline style) will overflow at 390px. Ops has no mobile-specific CSS audited; it's likely a scroll-of-death.

12. **Developer-built feel?** Options (amber active border + zinc hardcodes + raw Tailwind layout), Alpha Lab (raw tab buttons, no PageChapter integration), Signal Lab (tombstone section), Risk (native OS checkbox, 11px button). These are all implementation-observable, not taste differences.

---

## 8. Key Implementation Risks That Other Panelists Underestimated

**Options 12→4 tab consolidation is the most regression-prone change in the roadmap.** Each of the 12 sub-pages has its own data hooks, independent routing, and in some cases test selectors. Gemini rated this "High" for regression. I want to be more specific: the risk is not just the tab nav — it's the `Outlet` routing in `OptionsLayout.tsx:65` that maps each `TABS` entry to a full sub-page component. Restructuring into 4 groups changes the URL structure unless shallow sub-tabs are used within each group. If URLs change, any bookmarks, deep links, or external references break. **Recommendation: keep all 12 URLs intact. Change only the visual nav presentation — group tabs into 4 visual headers with secondary tabs inside each, all still linking to the same 12 routes.** This is M effort, Low-Medium regression, and preserves all existing deep links.

**Decisions `xl:` → `lg:` breakpoint change (Opus's call, which I conceded to) has a hidden risk:** the 3-column grid at `lg:` means 1024px-1280px users get the multi-column layout. This sounds good but the middle column at 1024px with 220px sidebar = 804px available — col 1 = 360px, col 3 = 420px, col 2 = 804-360-420-gaps ≈ roughly 0px or negative with standard gaps. **The column width math breaks at `lg:`; either the fixed widths (360px and 420px) need to shrink, or the breakpoint should be `lg:` with width recalibration.** This is still P1 but effort is S-M, not S.

**Portfolio default flip** (PortfolioRouteSwitch.tsx:22 → default to brief) looks like an S change but carries Medium regression risk because PortfolioTerminal is the highest-trust page in the product with multiple data hooks. QA must verify that the brief view (`CopilotHoldings`) doesn't expose any data-display regressions before shipping. The Strategic Lock D comment says "Phase F is when the default flips" — this was planned, but the exact QA checklist for that flip was never specified. Flag this for explicit QA sign-off.

---

DONE: docs/research/debates/PHASE_15_elite_ux/round2/sonnet.md
