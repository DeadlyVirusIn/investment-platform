# Phase 15 — Round 3 (FINAL), Opus

**Lens:** Premium taste / hierarchy / microcopy / 10-of-10 feel. Copy-ready for the synthesis writer.

---

## 1. Final per-page scores

| # | Page | Final score | One-line justification |
|---|---|---|---|
| 1 | `/overview` (PicksPage) | **6.8** | Four competing heroes (TopStrip NAV / PageChapter NOW / Snapshot NAV / TodayPanel) plus ticker-above-fold drown the actual answer. |
| 2 | `/events` | **5.5** | Silent fetch-error swallow (`EventsResearchPage.tsx:27`) plus zero catalyst→signal synthesis = passive feed, not a "why." |
| 3 | `/action-queue` | **7.5** | Why-no-buys panel + skeleton + aria-pressed FilterBar are real premium moments; thesis-grouping is the next unlock. |
| 4 | `/signal-lab` | **5.0** | "Not yet wired" tombstone (`:170-183`) + uncalibrated 73/100 hero = vacancy sign on the credibility page. |
| 5 | `/decisions` | **6.5** | Calm card + humanReasoning are the best AI-moderator patterns in the product, undercut by two design systems on one page. |
| 6 | `/strategies` | **6.4** | Three opaque component imports stacked with no hero metric — promises a process, delivers a sub-view. |
| 7 | `/options/*` | **4.8** | 12 `flex-wrap` tabs + amber active border + zinc hardcodes = the "different product" surface. Largest single UX-debt item. |
| 8 | `/portfolio` | **6.2** | Default still PortfolioTerminal; brief↔working toggle invisible; the most premium view is hidden behind a URL param. |
| 9 | `/risk` | **6.0** | Honest mark-handling and `u-table-wrap` are excellent; 5 framing layers and an 11px "Generate explanation" button bury the premium feature. |
| 10 | `/research` (Alpha Lab) | **5.2** | Static fallback registry (`ResearchLab.tsx:85-126`) renders identically to live data — quiet trust violation. |
| 11 | `/ops` | **5.3** | Hardcoded `JobRow last="ok"` (`Ops.tsx:262-267`) is a literal lie if the scheduler fails — P0 honesty issue. |

**Median: 6.0.** The floor is now trust-violation pages, not architectural gaps.

---

## 2. Final elite-gap thesis

**This product is one disciplined removal pass away from premium — the elite gap is *singularity*: every fact appears exactly once, in exactly one visual treatment, in exactly the place it belongs.** Stripe shows today's volume *once*, above the fold, as the single hero; this product shows NAV three times in the upper viewport and posture in three places, training the user that *nothing* is the answer because *everything* claims to be. The specific motif elite products have that this lacks is **Stripe's "one hero per page" discipline** — the willingness to demote four good things so one great thing can land. Linear ships in one typeface at five sizes; this product runs Inter + JetBrains Mono + a third `--copilot-type-*` scale plus three frame systems, so Overview → Portfolio → Options feels like switching between three glued products. Until Phase 15 ships the *removals*, no additive polish closes the gap.

---

## 3. Final unanimous-or-strong-consensus findings

- ✓ **Options 12-tab `flex-wrap` nav is the single biggest UX failure** (`OptionsLayout.tsx:48-64`). All four scored 4.5–5.9; all four called for collapse to ~4 grouped sections.
- ✓ **Portfolio default must flip to brief view** (`PortfolioRouteSwitch.tsx:22`). The most premium surface in the product is hidden behind a URL param.
- ✓ **`Ops.tsx:262-267` hardcoded `JobRow last="ok"` is a P0 trust violation.**
- ✓ **`ResearchLab.tsx:85-126` static fallback registry renders identically to live data** — must be labeled or hidden when `shadow.length === 0`.
- ✓ **`EventsResearchPage.tsx:27` silently swallows fetch errors** (`.catch(() => setLoading(false))`) — backend failure looks like a clean empty day.
- ✓ **Three coexisting design systems** make the app read as three stitched products.
- ✓ **PageChapter + NextStepCard are the right narrative spine; adoption is incomplete** — missing on PortfolioTerminal, RiskDashboard (chapter only), AlphaLab, Ops.
- ✓ **"Why no buys?" panel is the best microcopy moment in the product** and should be replicated on Strategies / Signal Lab / Risk / Options-Overview empty states.
- ✓ **Density toggle is over-deployed** on pages where it does nothing visible (Events, Signal Lab, Strategies).
- ◐ **Signal Lab "Not yet wired" tombstone** is a credibility-killer.
- ◐ **Decisions `xl:` breakpoint should be `lg:`** so 1024-1280px users get the 3-col layout (with column-width recalibration).
- ◐ **Mobile is responsive, not native** — shell is solid, page interiors remain desktop ports.

---

## 4. Final disagreements that did NOT converge

1. **Hide DensityToggle on inert surfaces?** Gemini: keep visible globally, fix the CSS. Codex / Sonnet / me: hide. **My final position:** *Hide.* A control whose effect the user cannot perceive is worse than a missing control — it teaches them controls in this product don't do what they say.
2. **Reorder PicksPage launcher to match `page_flow.ts`?** Sonnet: reorder. Gemini / me: keep current "executive reading flow" (signals → catalysts → strategies → portfolio) — intentional and documented at `:198-200`. **My final position:** *Keep.* Add tiny "1 / 2 / 3 / 4" reading-order glyphs if discoverability worries; do not reorder.
3. **Add Source Serif 4 for AI-narrative blocks?** Gemini: yes. Sonnet / me: no. **My final position:** *Reject.* One typeface, one scale. The clarity gap is microcopy, not typography. Adding a serif trains users that AI-text is visually different — wrong direction for an AI-native OS.
4. **Bulk-execute on Action Queue?** Opus R1: yes. Gemini: no — friction is a feature. **My final position (revised):** *Gemini is right.* Keep individual review; add j/k keyboard navigation instead.
5. **Ambient AI-thinking motion on TopStrip?** Gemini: yes. Me: no — atmospheric and dishonest (engine ticks on a scheduler, not continuously). **My final position:** *Reject.* Motion only on real state change (200ms tint when `last_pipeline_at` updates).

---

## 5. Phase 15 roadmap

Each item names the **single polish detail** that determines premium vs developer-built.

### P0 — Truth fixes (non-negotiable)

1. **Replace hardcoded JobRow statuses** — `Ops.tsx:262-267`. **S / low.** Why 15: a literal `last="ok"` is a brand-killer.
   - **Premium-detail moment:** the replacement copy. NEW: `"Status pending — see scheduler logs"` inside `<ExpertDetails>`, not a fake "ok" pill.

2. **Label or hide Alpha Lab static fallback** — `ResearchLab.tsx:85-126`. **S / low.** Why 15: containers visually identical to live data.
   - **Premium-detail moment:** the badge. NEW pill above the registry: `"Static baseline — no live shadow signals this cycle"` at quiet `--fg-3`, not a warning ribbon.

3. **Restore visible fetch error on Events** — `EventsResearchPage.tsx:27`. **S / low.** Why 15: 500 looks identical to clean empty day.
   - **Premium-detail moment:** use the existing `<FetchError>` component from Action Queue; do *not* invent a new error visual.

4. **Verify or remove `GuardrailsToggleButton`** — `OptionsLayout.tsx:44-46`. **S / low.** Why 15: a toggle that looks functional but isn't is fakes-by-UI.
   - **Premium-detail moment:** if kept, the off-state must visibly change something. If it can't, remove.

5. **Hide Signal Lab "Not yet wired" tombstone** — `SignalLabPage.tsx:170-183`. **S / low.** Why 15: 280px+ empty content on the credibility page.
   - **Premium-detail moment:** replace with one line inside `<ExpertDetails>`: `"Backtest validation pending — see Ops > ML pipeline."` Not a card. One line.

6. **Remove emoji from Decisions** — `Decisions.tsx:359`. **S / low.** Why 15: violates trust posture on a decision-audit page.
   - **Premium-detail moment:** the replacement glyph. NEW: a quiet `→` or `·` at `--fg-3`. Not an icon.

### P1 — Hierarchy + microcopy

7. **Flip Portfolio default to brief AND add visible toggle** — `PortfolioRouteSwitch.tsx:22`. **S+S / medium.** Why 15: brief view is the most premium surface; default exposes it.
   - **Premium-detail moment:** the toggle UI. NEW: 2-segment pill in Portfolio header reading `Brief | Working`, same primitive as DensityToggle.

8. **Remove MarketTicker from above-the-fold on Overview** (Overview-only). **S / low.** Why 15: highest-leverage emotional-read change available; ticker is the page's biggest motion source competing with the answer.
   - **Premium-detail moment:** the *transition* — ticker fades out (200ms ease-out) when route is `/overview`, not jump-cut.

9. **Demote PortfolioSnapshot to 3 metrics + ExpertDetails** — `PortfolioSnapshot.tsx:98-160`. **M / low.** Why 15: Stripe's "one hero" discipline.
   - **Premium-detail moment:** *which three.* NEW primary trio: **NAV / Total return / Day P&L**. Everything else in `<ExpertDetails label="Position breakdown">`.

10. **Hide DensityToggle on inert surfaces** (Overview / Events / Signal Lab / Strategies). **S / low.** Why 15: false affordance erodes trust in every other control.
    - **Premium-detail moment:** *conditional render*, not disabled state. A grayed-out toggle is worse than no toggle.

11. **Kill `border-amber-400` in OptionsLayout** — `OptionsLayout.tsx:56`. **S / low.** Why 15: single visual line that says "different product."
    - **Premium-detail moment:** NEW: `border-[var(--accent)]` (the app's `#4B8BFF`). Not a new amber token.

12. **Microcopy translation pass — round 2.** **S / low.** Why 15: every leaked engineering phrase costs premium feel.
    - `PicksPage.tsx:268`: OLD `"${riskCount} signal(s) flagged for risk — see what changed in catalysts first"` → NEW `"${riskCount} picks need a closer look — start with what changed today"`.
    - `EventsResearchPage.tsx:33-37`: OLD `"N symbols from active recommendations · SEC EDGAR feed live"` → NEW `"Tracking N symbols · filings update through the day"`.
    - `OptionsLayout.tsx:42`: OLD `"Paper-trading guidance · simulated only · no live execution"` → NEW `"Paper trading — nothing here places real orders"`.
    - `RiskDashboard.tsx:124-132` button: OLD `"Generate explanation"` → NEW `"Why?"` (and bump to a primary action affordance, not 11px text).
    - `FilterBar.tsx:33-35`: OLD `"high-confidence" / "freshest" / "highest-risk"` → NEW `"≥70% confidence" / "<6h old" / "Risk-flagged"`.
    - **Premium-detail moment:** verbs become questions. `"Why?"` is the most premium copy on the page.

13. **Add NextStepCard at the route level** for PortfolioTerminal, RiskDashboard, AlphaLab, Ops. **S / low.** Why 15: closes FLOW story on four legacy pages without touching internals.
    - **Premium-detail moment:** the *rationale string*. Each must be derived from real data (open trade count, risk flag count). Generic rationales are visible engineering smell.

14. **Decisions `xl:` → `lg:` breakpoint AND column reorder** — `Decisions.tsx:206-207`. **S / low.** Why 15: 1024-1280px users get 3-col; detail becomes the flex anchor.
    - **Premium-detail moment:** column math. NEW: `lg:grid-cols-[320px_minmax(0,1fr)_360px]` — narrow outer columns so detail (the hero) gets breathing room.

15. **Add unified loading-skeleton pattern** to Events / Signal Lab / Overview. **M / low.** Why 15: ActionQueue's skeleton is canon; absence elsewhere reads as unfinished.
    - **Premium-detail moment:** skeleton *shape* must match loaded content silhouette, not generic gray bars.

---

## 6. Phase 16 roadmap

16. **Options 12 → 4 tabs + `--pi-*` tokenization.** XL / medium-high. Why 16: structural; needs sub-tab routing + 12 sub-page QA. Keep all 12 URLs intact (Sonnet's risk catch); only change visual nav. Groups: **Overview / Trades & Risk / Strategy Lab / Engineering**.
17. **Decisions design-system unification** — migrate body to picks-root frame; thread calm card into PageChapter. L / medium. Why 16: many `data-test` selectors; needs careful migration.
18. **Action Queue thesis-grouping** — group by dominant `pickTags` cluster. M / low. Why 16: requires aggregation logic.
19. **"What changed" temporal-context pills** — across Overview, Events, Action Queue, Portfolio, Risk. M / low. Why 16: requires session/timestamp comparison plumbing.
20. **Replicate "Why no buys?" pattern** to Strategies / Signal Lab / Risk / Options-Overview empty states. M / low. Why 16: depends on group-level synthesis from #18.
21. **Move OverviewRouteSwitch experimental variants behind internal flag** — `:35-46`. S / low. Why 16: requires deciding which variants stay.
22. **Strategies hero metric** (active / blocked / eligible) — *not* another Start-here card. M / low. Why 16: requires deriving strategy-state aggregates.
23. **Expand ExpertDetails** to Decisions diagnostics, Risk advanced tables, AlphaLab internals, Ops long-tail, Options diagnostics. M / low. Why 16: additive but cross-page; pacing reasons.

---

## 7. Phase 17 roadmap

24. **One motion vocabulary** — `--motion-fast: 120ms` / `--motion-base: 200ms` ease-out tokens; tied to *real state changes only*. M / low. Why 17: cross-page taste arbitration; explicitly *not* ambient AI motion.
25. **Persistent AI assistant rail** — quiet button, opens drawer, scoped to current page's data, refuses to answer when stale. XL / high. Why 17: must wait for design-system unification; cross-page context assembly is hard.
26. **Inline "Why?" hover on numeric heroes** — readiness composite, drawdown, exposure pct. Button copy is `"Why?"` not `"Generate explanation"`. L / medium. Why 17: requires explanation infra at every numeric source.
27. **Mobile bottom-sheet pattern for Decisions row-detail** — refining Gemini's master-detail away from sub-routes. L / medium. Why 17: needs sheet primitive not in current shell.
28. **Mobile-native re-IA** — separate top mobile widget composition (posture + 1 actionable signal + horizontal swipe). XL / high. Why 17: requires Phase 16 Options collapse first; highest-ambition item.

---

## 8. Final answer to the 12 brief questions

1. **Coherent story?** Mostly — FLOW data structure is coherent; visual delivery is fragmented by competing design systems.
2. **Linear/intelligent navigation?** SideNav: 8/10. In-page: 4/10 — four idioms where one would do.
3. **Natural Overview → Catalysts → Decisions → Execution → Portfolio → Risk?** Possible via PageChapter NEXT, contradicted by NextStepCard rationale that says "see catalysts first" while linking to Action Queue (`PicksPage.tsx:264-271`).
4. **Dead/passive pages?** Events (no synthesis), Signal Lab lower half (tombstone), Alpha Lab (worksheet + static fallback), Ops middle band.
5. **Collapsible?** Decisions diagnostics, Risk advanced breakdowns, Ops 15 cards into 4 super-sections; "Start here" cards become *dismissible* (localStorage), not collapsed-by-default.
6. **Sticky?** Decisions Timeline column at lg+; FilterBar on **desktop only** (Phase 14f-F deliberately relaxed mobile sticky).
7. **Visually noisy?** PortfolioSnapshot 8-12 metrics; Options Risk 4-KPI strip; `u-nonprod-ribbon` orange wash on Decisions; Overview.tsx 5-card 30%-column right rail.
8. **Under-emphasized?** "Generate explanation" button (11px, wrong verb); brief↔working toggle on Portfolio (URL-only); SideNav next-step indicator.
9. **Wasted vertical space?** PicksPage launcher duplicated metric line; Signal Lab tombstone; Decisions calm-card+chip-rail+AdvancedDetails 4-layer stack; Alpha Lab `mb-6` spacer.
10. **Too dense?** Options Chain table; PortfolioTerminal positions on mobile; Decisions 3-col below xl; Ops middle band; Overview.tsx right column.
11. **Mobile fails?** Options 12-tab `flex-wrap`; Decisions 3-col stacking; Ops (no mobile work); Overview.tsx 5-col NAV strip; RiskDashboard 5 framing layers stacked.
12. **Developer-built?** Ops, Options, Alpha Lab, Signal Lab middle, RiskDashboard middle band, Overview.tsx "System diagnostics" AdvancedDetails.

---

## 9. The one thing I would NOT change

**The PageChapter + NextStepCard narrative spine, and specifically the `page_flow.ts` FLOW chain** (`apps/web/src/lib/ui/page_flow.ts:24-78`). This is the single most architecturally elite decision in the codebase — a typed, route-aware narrative graph that makes "Overview → Catalysts → Decisions → Execution → Portfolio → Risk" a *real data structure* the UI consumes, not a hope. Premium-polish proposals to "modernize headers" or "unify hero patterns" must thread *through* PageChapter, not replace it. If Phase 15-17 ship every other recommendation but break this spine, the seven query-param Overview variants, the four header patterns, and the three frame systems will reassert themselves immediately. PageChapter is the load-bearing structure; touch around it, never under it.
