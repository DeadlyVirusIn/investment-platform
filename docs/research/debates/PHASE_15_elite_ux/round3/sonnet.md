# Phase 15 Elite UX Debate — Round 3 Final (Sonnet / Pragmatic Implementer)

## 1. Final per-page scores

| # | Page | Final score | One-line justification |
|---|---|---|---|
| 1 | `/overview` | 7.0 | Launcher order defensible (per comment at PicksPage.tsx:198-200), but four stacked heroes above the fold prevent a clean first-second read. |
| 2 | `/events` | 5.0 | The `.catch(() => setLoading(false))` at EventsResearchPage.tsx:27 is a confirmed truth violation — a failed fetch is indistinguishable from a zero-catalyst day. |
| 3 | `/action-queue` | 8.0 | Strongest surface; skeleton, "Why no buys?", FetchError all correct; FilterBar/no-buys ordering defect is real but minor. |
| 4 | `/signal-lab` | 5.0 | Tombstone section at SignalLabPage.tsx:173-183 confirmed; readiness score has no calibration band; the lower half of the page signals a backlog ticket. |
| 5 | `/decisions` | 7.0 | Calm card is genuinely excellent; `xl:grid-cols` breakpoint at Decisions.tsx:207 is the single-line fix that prevents the fix; combined change brings this to 7.5. |
| 6 | `/strategies` | 6.5 | ExpertDetails collapse is correctly done; three opaque component imports are a regression black box; no hero metric. |
| 7 | `/options/*` | 4.5 | 12-tab flex-wrap at OptionsLayout.tsx:48 is a confirmed mobile failure; amber active border at line 56 is a confirmed design-system break. |
| 8 | `/portfolio` | 6.5 | Phase F flip not shipped (PortfolioRouteSwitch.tsx:22); brief view undiscoverable; PortfolioTerminal has no PageChapter. |
| 9 | `/risk` | 6.0 | Native OS checkbox and 11px "Generate explanation" button (RiskDashboard.tsx:115-133) are confirmed implementation gaps; honest mark handling is correct. |
| 10 | `/research` | 5.0 | ResearchLab.tsx:128 fallback renders static `knownSignals` in the same card as live data with no visual distinction — P0 truth violation. |
| 11 | `/ops` | 5.5 | Ops.tsx:263-266 hardcodes `last="ok"` and `last="skipped"` — trust violation on a page whose only job is to report system truth. |

---

## 2. Final elite-gap thesis

The product is not yet elite because it has not resolved the difference between "correctly wired" and "honest to the user." Pages like Ops, Alpha Lab, and Events are structurally sound — they have PageChapter, FetchError imports, and correct hook patterns — but their user-facing data is either hardcoded, silently swallowed, or rendered without distinguishing live from static. This is the specific gap between a premium developer tool and a premium product: a developer tool shows you what the system is doing; a premium product guarantees that what it shows you is true. Until every visible status, fallback, and tombstone either reflects live data or is labeled as not live, the product cannot reach elite status regardless of visual polish. Options and the three-design-system problem are the second layer of the gap — real, but secondary to the truth violations that currently exist on four separate pages.

---

## 3. Final unanimous-or-strong-consensus findings

- ✓ Options 12-tab `flex-wrap` at `OptionsLayout.tsx:48` is the single largest UX failure — mobile completely broken, all four panelists agree.
- ✓ `Ops.tsx:263-266` hardcoded `last="ok"` / `last="skipped"` is a P0 trust violation — all four panelists converge.
- ✓ `ResearchLab.tsx:128` static fallback registry renders identically to live data — P0 fakes-by-omission, all four agree.
- ✓ `EventsResearchPage.tsx:27` swallows fetch errors silently — P0 truth violation, all four identify.
- ✓ Portfolio default must flip to brief view (`CopilotHoldings`) — all four converge on this.
- ✓ Signal Lab tombstone ("Not yet wired") at `SignalLabPage.tsx:173-183` must be removed or hidden — all four agree.
- ✓ Three coexisting design systems (picks-root / u-card Tailwind / Options zinc-*) is the structural coherence problem — all four name it.
- ◐ DensityToggle is a false affordance on pages where it has no visible effect (Events, Signal Lab, Strategies) — Opus, Sonnet, Codex converge; Gemini disagrees (wants global state preserved).
- ◐ PageChapter + NextStepCard threading is incomplete — missing from PortfolioTerminal, AlphaLab, Ops bottom — three of four flag this.
- ◐ `border-amber-400` active state in OptionsLayout.tsx:56 collides with `--accent: #4B8BFF` — Opus, Gemini, Sonnet confirm.

---

## 4. Final disagreements that did NOT converge

**a. DensityToggle: hide on inert pages vs. wire globally**
Gemini holds that the toggle is global app state and should remain visible everywhere, with the CSS tokens fixed to actually respond on non-table pages. Opus, Sonnet, Codex hold that showing a control that does nothing undermines trust. My final position: hide on inert pages in Phase 15 (S effort, zero regression risk). The token-wiring fix is Phase 16 work and should not block the false-affordance removal.

**b. Launcher card ordering: match page_flow.ts or keep "executive reading order"**
Opus (supported by Gemini) argues the current order (signals → catalysts → strategies → portfolio) is intentionally correct and documented at PicksPage.tsx:198-200. My Round 1 flag to reorder was wrong per that comment. I concede to Opus: the order stays; the fix is adding a visible reading-order glyph ("1 / 2 / 3 / 4") to each card so the intent is discoverable. Effort S, regression Low.

**c. Serif font for AI narrative blocks (Gemini's proposal)**
Gemini still holds a reduced form of the serif proposal for AI synthesis blocks. All other panelists reject it. My final position: reject entirely. The brief explicitly forbids "atmospheric visuals that reduce information clarity." A serif font in an AI-narrative block aestheticizes data without clarifying it. Inter stays. The clarity gap is microcopy, not typography.

**d. FilterBar sticky on mobile**
I proposed the FilterBar should be sticky on scroll. Opus correctly pushed back citing Phase 14f-F's deliberate decision to relax sticky behavior (only TopStrip pinned). I concede. FilterBar is sticky on desktop only. Mobile scrolls with content. The 14f-F decision stands.

**e. Decisions breakpoint `xl:` → `lg:` combined with column width math**
I conceded to Opus in Round 2 that this is a correct fix, but flagged in my Round 2 implementation note that the fixed column widths (360px and 420px) break the math at `lg:` widths — col 2 becomes near-zero at 1024px with a 220px sidebar. The correct fix is `lg:grid-cols-[280px_minmax(0,1fr)_360px]` (shrinking fixed columns proportionally), not a pure breakpoint change. This is still P1, effort S-M, not S.

---

## 5. Phase 15 roadmap

1. **Fix hardcoded Ops JobRow statuses or label them**
   - `apps/web/src/pages/Ops.tsx:263-266`
   - Effort: S | Regression risk: low
   - Why 15: P0 trust violation — hardcoded "ok" on a system-health page contradicts the product's core honest-data premise.

2. **Label Alpha Lab static fallback registry**
   - `apps/web/src/pages/ResearchLab.tsx:128`
   - Effort: S | Regression risk: low
   - Why 15: P0 fakes-by-omission — the conditional at line 128 renders static entries visually identical to live data; a pill or ExpertDetails wrapper fixes this in one change.

3. **Restore Events fetch error display**
   - `apps/web/src/pages/EventsResearchPage.tsx:27`
   - Effort: S | Regression risk: low
   - Why 15: P0 truth violation — existing FetchError component is already in the codebase; this is a one-line catch handler fix.

4. **Remove Signal Lab tombstone**
   - `apps/web/src/pages/SignalLabPage.tsx:170-183`
   - Effort: S | Regression risk: low
   - Why 15: P0 production smell — the section is ~280px of "not yet wired" text occupying a user-facing page; replacement is a true empty state with no data dependencies.

5. **Fix Options tab mobile nav: `flex-wrap` → `overflow-x-auto`**
   - `apps/web/src/pages/options/OptionsLayout.tsx:48`
   - Effort: S | Regression risk: low
   - Why 15: P0 mobile failure — single class swap; no routing change; all 12 URLs preserved; confirmed at line 48.

6. **Kill Options amber active border, replace with `--accent`**
   - `apps/web/src/pages/options/OptionsLayout.tsx:56`
   - Effort: S | Regression risk: low
   - Why 15: Single token swap eliminates the most visually jarring design-system collision in the product.

7. **Add visible Portfolio view toggle (Brief / Working)**
   - `apps/web/src/pages/copilot/PortfolioRouteSwitch.tsx`
   - Effort: S | Regression risk: low
   - Why 15: CopilotHoldings is URL-only discoverable (confirmed at line 20-22); the toggle is purely additive UI with no data logic change.

8. **Flip Portfolio default to brief view**
   - `apps/web/src/pages/copilot/PortfolioRouteSwitch.tsx:22`
   - Effort: S | Regression risk: medium
   - Why 15: The Phase F flip was planned and documented in code; regression risk is medium because PortfolioTerminal is the highest-trust page — requires explicit QA sign-off before shipping, but belongs in Phase 15 because it's paired with the toggle above.

9. **Remove emoji from Decisions EmptyFilter**
   - `apps/web/src/pages/Decisions.tsx:355-363`
   - Effort: S | Regression risk: low
   - Why 15: P0 discipline violation per user-global instructions; one-line removal.

10. **Verify or remove GuardrailsToggleButton wiring**
    - `apps/web/src/pages/options/OptionsLayout.tsx:44-46`
    - Effort: S | Regression risk: low
    - Why 15: If this button does not filter data, it is UI-only and must be removed or labeled; asymmetric risk — if it works, no change needed; if it doesn't, it is a fakes-by-UI violation that belongs in Phase 15.

11. **Hide DensityToggle on inert pages (Events, Signal Lab, Strategies)**
    - Multiple page files
    - Effort: S | Regression risk: low
    - Why 15: False affordance — a control that appears active but does nothing reduces trust; conditional render via a `showDensity` prop is a minimal additive change.

12. **Add PageChapter + NextStepCard to PortfolioTerminal at route level**
    - `apps/web/src/pages/copilot/PortfolioTerminal.tsx`
    - Effort: S | Regression risk: low
    - Why 15: Purely additive import; Portfolio is the highest-trust page and the only major page without a narrative rail; the journey breaks here without it.

13. **Fix Decisions 3-col breakpoint + column widths**
    - `apps/web/src/pages/Decisions.tsx:207`
    - Effort: S-M | Regression risk: low
    - Why 15: Change `xl:grid-cols-[360px_minmax(0,1fr)_420px]` to `lg:grid-cols-[280px_minmax(0,1fr)_360px]`; fixes 1024-1280px users (common laptop); column math must account for 220px sidebar — verify before ship.

14. **Add readiness score interpretation band to Signal Lab**
    - `apps/web/src/pages/SignalLabPage.tsx`
    - Effort: S | Regression risk: low
    - Why 15: The score (0-100) has no interpretive value without a band; pairs directly with tombstone removal (same page, same sprint).

---

## 6. Phase 16 roadmap

1. **Options IA: 12 tabs → 4 visual groups, preserve all 12 URLs**
   - `apps/web/src/pages/options/OptionsLayout.tsx` + all sub-pages
   - Effort: M | Regression risk: medium
   - Why 16: Do NOT change URL structure (breaks deep links); change only the visual nav presentation — group tabs into 4 headers with secondary tabs; test all 12 sub-pages independently after.

2. **Unified loading skeleton pattern across all pages**
   - EventsResearchPage, SignalLabPage, PortfolioTerminal, RiskDashboard
   - Effort: M | Regression risk: low
   - Why 16: ActionQueue skeleton is the template; pattern is additive; Phase 15 truth fixes land first so the skeleton pattern isn't masking errors.

3. **Ops 16-card grouping into 4 collapsible sections**
   - `apps/web/src/pages/Ops.tsx`
   - Effort: M | Regression risk: low
   - Why 16: Purely additive layout; wait for Phase 15 Ops truth fix (hardcoded statuses) so grouping doesn't hide a fixed problem.

4. **Action Queue group-level rationale (top decision factors per action group)**
   - `apps/web/src/pages/ActionQueuePage.tsx`
   - Effort: M | Regression risk: medium
   - Why 16: Action Queue is already the strongest page; enhancement waits until broken pages are stabilized in Phase 15.

5. **Replicate "Why no buys?" pattern on Signal Lab, Strategies, Options Overview empty states**
   - SignalLabPage, StrategiesPage, options/OptionsOverviewPage
   - Effort: M | Regression risk: low
   - Why 16: Pattern is proven; requires per-page copy and conditional logic per posture; additive but non-trivial to get microcopy right.

6. **Microcopy translation round 2: four confirmed engineering-vocabulary leaks**
   - `PicksPage.tsx:268`, `EventsResearchPage.tsx:33-37`, `OptionsLayout.tsx:42`, `RiskDashboard.tsx:124-132`
   - Effort: S | Regression risk: low
   - Why 16: Not Phase 15 because microcopy is lower priority than truth violations; but confirmed vocabulary leaks named by Opus should be addressed before Phase 17 polish.

7. **Strategies page hero metric (active / blocked / eligible count)**
   - `apps/web/src/pages/StrategiesPage.tsx`
   - Effort: M | Regression risk: low
   - Why 16: Replaces the missing "Start here" card pattern (which would be the 5th instance of that pattern) with a data-driven hero metric instead.

---

## 7. Phase 17 roadmap

1. **Merge picks-* and u-card systems into one canonical layout**
   - All pages; anchored in `apps/web/src/index.css` + `picks.css`
   - Effort: XL | Regression risk: very high
   - Why 17: This is the whole design system; touching it before Phase 15-16 truth and coherence work would destabilize a moving target; only safe to unify when the page count is stable and all surfaces are confirmed correct.

2. **Single motion vocabulary tied to real state changes**
   - `apps/web/src/index.css` (`--motion-fast`, `--motion-base` tokens)
   - Effort: M | Regression risk: low
   - Why 17: Safe standalone; worth doing in parallel with Phase 17; the 200ms tint on TopStrip when `last_pipeline_at` changes is the correct "AI presence" moment — not ambient animation.

3. **Mobile-native Decisions detail: bottom sheet on row tap**
   - `apps/web/src/pages/Decisions.tsx`
   - Effort: L | Regression risk: medium
   - Why 17: Requires Phase 16 Decisions layout stabilization first; bottom sheet (not sub-route) is the correct premium pattern per Opus; the Phase 13 scroll-into-view fix in Phase 15 is the interim.

4. **Persistent AI assistant rail (page-scoped, stale-gated)**
   - `apps/web/src/components/shell/Shell.tsx`
   - Effort: XL | Regression risk: high
   - Why 17: Must not start until design-system unification (Phase 17 item 1) is complete; requires cross-page context assembly, stale-data gating, and a new shell slot that doesn't conflict with SideNav/TopStrip stack; the existing InsightDrawer at RiskDashboard.tsx:31-38 is the proof-of-concept precedent.

---

## 8. Final answer to the 12 brief questions

1. The structural story in `page_flow.ts` is coherent; the actual page delivery breaks at Portfolio (no PageChapter on PortfolioTerminal) and Events (passive feed with no catalyst-to-signal join).
2. SideNav + PageChapter NEXT threading is intelligently designed; in-page navigation is fragmented across four incompatible patterns (FilterBar/Options NavLink/AlphaLab buttons/Decisions chips).
3. The Overview → Catalysts → Decisions flow is possible but never automatic — the PicksPage launcher order is defensible but not explained to the user, and Portfolio breaks the chain by defaulting to the dense terminal.
4. Signal Lab (tombstone), Events (passive RSS dump), and Alpha Lab (static fallback + worksheet feel) are the three dead-zone pages.
5. Ops 16 cards (into 4 groups), Signal Lab backtest section (until wired), Decisions/Risk "Start here" cards (auto-collapse after first visit with localStorage flag).
6. Options tab nav should be sticky as a single overflow-x row after the flex-wrap fix; Decisions Timeline column is sticky at `lg+` on desktop only; FilterBar is sticky on desktop, scrolls with content on mobile per Phase 14f-F intent.
7. The PortfolioSnapshot 8-12 metric grid and the Overview 4-stacked-hero composition are the noisiest surfaces; Options 12-tab header is the densest navigation element.
8. CopilotHoldings brief view (URL-only access), the Risk "Generate explanation" button (11px, confirmed at RiskDashboard.tsx:124), and the Portfolio view toggle (non-existent in UI) are all under-emphasized.
9. Signal Lab tombstone block (~280px of empty content), Ops preamble (80 lines before first operational card), and the Alpha Lab `mb-6` spacer at ResearchLab.tsx:64.
10. Options chain table, PortfolioTerminal 5-column NAV strip at sub-mobile widths, and Decisions 3-column at sub-`xl` widths are the three over-dense surfaces.
11. Options tab nav is the confirmed worst mobile failure; PortfolioTerminal 5-column NAV strip will overflow at 390px; Ops is an unstructured scroll with no mobile-specific layout work.
12. Ops (hardcoded statuses), Alpha Lab (static fallback), Signal Lab lower half (tombstone), Options (amber border + raw Tailwind layout), and Risk (native OS checkbox + 11px button) all read as developer-built.

---

## 9. The one thing you would NOT change

The `PageChapter` + `NextStepCard` narrative spine — the NOW / WHY / NEXT threading through `page_flow.ts` — is the single most load-bearing architectural decision in the codebase and would be a mistake to undo or dilute, even in the name of visual unification.
