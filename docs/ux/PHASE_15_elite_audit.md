# Phase 15 Elite UX Audit — AI Investing OS

**Date:** 2026-05-11
**Format:** 4-panelist octo:debate (Gemini CLI 0.39.1 · Codex CLI 0.125.0 · Claude Sonnet · Claude Opus)
**Rounds:** 3 (positions → rebuttals → final convergence)
**Branch:** phase-1/ledger
**Latest commit at audit time:** c0e18fd (Phase 14f-F)
**Pages reviewed:** 11
**Raw transcripts:** docs/research/debates/PHASE_15_elite_ux/round{1,2,3}/{gemini,codex,sonnet,opus}.md (12 files, ~262KB combined)

---

## 1. Executive summary

After three rounds and ~262KB of independent audit, four panelists converge on a single thesis: **the product has the bones of a 9/10 AI-native investing OS and the surface of a 6/10. The elite gap is not missing features — it is a discipline of singularity (one fact, one place, one treatment) and a small number of unfixed truth violations that quietly lie to the user.** The architectural decisions that mattered (the `page_flow.ts` chain, PageChapter/NextStepCard threading, ExpertDetails progressive disclosure, honest paper-trading disclaimers, the `/api/paper/summary` canonical source, action-color semantics) have all landed correctly. What remains is removal work, not addition work.

The headline number is an **overall median page score of 6.0/10** across the 11 pages (Gemini median 6.0, Codex 6.5, Sonnet 6.0, Opus 6.0). Round 3 panelist scores agree within ~1.0 on every page. The strongest surface is Action Queue (median 8.0/10) — universally praised for the "Why no buys?" panel, the skeleton loader, and `aria-pressed` filter semantics. The weakest cluster is **Options (median 4.6/10), Ops (4.9), Alpha Lab (4.9), and Signal Lab (5.0)** — for distinct reasons that resolve to the same root cause: surfaces that show information without enough hierarchy, provenance, or honesty.

Top three actions for Phase 15, in plain English: **(1) Stop lying to the user.** Four pages currently show data that is hardcoded, silently swallowed, or rendered identically to live data — Ops `JobRow last="ok"`, Alpha Lab static fallback registry, Events fetch-error swallow, and the Signal Lab "Not yet wired" tombstone. These four fixes are all S-effort, low-regression, and unanimously P0. **(2) Unbreak Options on mobile.** Twelve `flex-wrap` tabs at 375px wrap to four rows of chips before any content is visible — a single-line CSS fix (`flex-wrap` → `overflow-x-auto`) is the immediate patch; the structural collapse to four grouped tabs is Phase 16. **(3) Make the premium Portfolio view discoverable.** The `CopilotHoldings` brief view is hidden behind `?view=brief`; default visitors land on the dense terminal. Add a visible Brief/Working toggle and flip the default — both planned in code comments, neither shipped.

If Phase 15 ships these three groups (12-15 items, all S/M effort, low-medium regression), the median moves from 6.0 to ~7.5 and the product crosses from "high-end developer tool with caring scaffolding" to "premium product that respects the user's first ten seconds." Everything in Phase 16-17 (Options IA collapse, design-system unification, AI-native moments, mobile-native re-IA) is unlock work, not rescue work.

---

## 2. Per-page final scores

| # | Page | Gemini R3 | Codex R3 | Sonnet R3 | Opus R3 | **Median** | One-line consensus |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | `/overview` (PicksPage) | 7.0 | 7.2 | 7.0 | 6.8 | **7.0** | Strong executive briefing undermined by 3-4 competing heroes (TopStrip NAV / PageChapter NOW / Snapshot NAV / TodayPanel) and a duplicated launcher metric line. |
| 2 | `/events` | 6.0 | 5.8 | 5.0 | 5.5 | **5.65** | Honest delegation, but `EventsResearchPage.tsx:27` swallows fetch errors silently and the page never joins catalysts to active signals — passive feed, not the "why." |
| 3 | `/action-queue` | 8.5 | 8.1 | 8.0 | 7.5 | **8.05** | Best surface in the product; "Why no buys?" panel + skeleton + `aria-pressed` FilterBar are real premium moments; thesis-grouping is the next unlock. |
| 4 | `/signal-lab` | 4.5 | 5.1 | 5.0 | 5.0 | **5.0** | "Not yet wired" tombstone at `SignalLabPage.tsx:170-183` plus uncalibrated 73/100 hero is a vacancy sign on the credibility page. |
| 5 | `/decisions` | 7.0 | 6.7 | 7.0 | 6.5 | **6.85** | Calm card + humanReasoning are the best AI-moderator patterns in the product; undercut by two design systems on one page and an `xl:` breakpoint that strands 1024-1280px users. |
| 6 | `/strategies` | 6.5 | 6.7 | 6.5 | 6.4 | **6.5** | Education collapse (Phase 14f-E) landed correctly; the page lacks a top-level active/blocked/eligible hero metric and stacks three opaque component imports. |
| 7 | `/options/*` | 4.0 | 4.7 | 4.5 | 4.8 | **4.6** | 12 `flex-wrap` tabs + amber active border + zinc hardcodes = the "different product" surface; largest single UX-debt item in the codebase. |
| 8 | `/portfolio` | 6.0 | 6.4 | 6.5 | 6.2 | **6.3** | Default still PortfolioTerminal; brief↔working toggle invisible; the most premium surface in the product is hidden behind a URL param. |
| 9 | `/risk` | 6.5 | 6.5 | 6.0 | 6.0 | **6.25** | Honest mark-handling and `u-table-wrap` discipline are excellent; 5 framing layers and an 11px "Generate explanation" button bury the premium feature. |
| 10 | `/research` (Alpha Lab) | 4.0 | 5.2 | 5.0 | 5.2 | **5.1** | Static fallback registry at `ResearchLab.tsx:85-126` renders identically to live data — quiet trust violation; worksheet aesthetic and weak verdict framing. |
| 11 | `/ops` | 4.0 | 5.1 | 5.5 | 5.3 | **5.2** | Hardcoded `JobRow last="ok"` at `Ops.tsx:262-267` is a P0 trust violation; 16-card sprawl with no grouping. |

**Overall median page score: 6.0/10.** Round 1 → Round 3 score drift is small (≤0.5) on most pages; the largest moves are Ops (5.5 → 5.2) and Alpha Lab (5.5 → 5.1) — both downgrades after panelists collectively elevated trust violations to P0.

---

## 3. Unanimous findings (4-of-4)

- ✓ **Options 12-tab `flex-wrap` nav at `OptionsLayout.tsx:48-64` is the single largest UX failure** — completely broken on mobile (4+ rows of chips at 375px), overwhelming on desktop. *(Gemini R1/R2/R3, Codex R1/R2/R3, Sonnet R1/R2/R3, Opus R1/R2/R3.)*
- ✓ **Hardcoded `JobRow last="ok"` and `last="skipped"` at `Ops.tsx:262-267` is a P0 trust violation** — a literal lie if the scheduler fails on a system-health page whose only job is to report system truth. *(Opus R1 first-flagged; conceded by Gemini R2, Codex R2, Sonnet R1; reaffirmed unanimously R3.)*
- ✓ **Static fallback registry at `ResearchLab.tsx:85-126` renders identically to live data** — when `shadow.length === 0` the page silently substitutes hardcoded `knownSignals` rows in the same "Shadow Signal Registry" card with no visual distinction. P0 fakes-by-omission. *(Opus R1 first-flagged; conceded by Gemini R2, Codex R2, Sonnet R2; reaffirmed unanimously R3.)*
- ✓ **`EventsResearchPage.tsx:27` silently swallows fetch errors** (`.catch(() => { if (!cancelled) setLoading(false); })`) — backend 500 looks identical to a clean empty day. P0 truth violation. *(Opus R1, Sonnet R1; conceded by Codex R2; reaffirmed unanimously R3.)*
- ✓ **Portfolio default must flip from PortfolioTerminal to brief view (`CopilotHoldings`)** — `PortfolioRouteSwitch.tsx:22` defaults to terminal; `?view=brief` is URL-only and undiscoverable; the most premium AI-narrative surface in the product is hidden from default visitors. The Phase F flip was planned in code comments but never shipped. *(Gemini R1/R2/R3, Codex R1/R2/R3, Sonnet R1/R2/R3, Opus R1/R2/R3.)*
- ✓ **Signal Lab "Not yet wired" backtest tombstone at `SignalLabPage.tsx:170-183` must be removed or hidden** — ~280px of "Not yet wired" empty content on the credibility page; reads as a developer backlog ticket. *(Gemini R1/R2/R3, Codex R1/R2/R3, Sonnet R1/R2/R3, Opus R1/R2/R3.)*
- ✓ **Three coexisting design systems** make the app read as three stitched products: (a) `picks-root` / `--pi-*` tokens (Overview, Action Queue, Events, Signal Lab, Strategies); (b) `max-w-[…] mx-auto px-X py-Y` Tailwind shells with `u-card` (Decisions, RiskDashboard, ResearchLab, Ops, PortfolioTerminal); (c) `zinc-*` Tailwind hardcodes (Options sub-pages). *(Gemini R1/R2/R3, Codex R1/R2/R3, Sonnet R1/R2/R3, Opus R1/R2/R3.)*
- ✓ **PageChapter + NextStepCard are the right narrative spine but adoption is incomplete** — missing on PortfolioTerminal, AlphaLab, Ops bottom; RiskDashboard has PageChapter NEXT but no NextStepCard. *(Gemini R3, Codex R1/R2/R3, Sonnet R1/R2/R3, Opus R1/R2/R3.)*
- ✓ **The "Why no buys?" panel on Action Queue at `ActionQueuePage.tsx:146-170` is the best microcopy moment in the product** and should be replicated on Strategies / Signal Lab / Risk / Options-Overview empty states. *(Gemini R1/R2/R3, Codex R1/R2/R3, Sonnet R1/R2/R3, Opus R1/R2/R3.)*
- ✓ **Mobile is responsive but not native** — the Phase 14f shell work (drawer, ticker compress, sticky relax, 44px tap targets) is solid, but page interiors (NAV strips, multi-column grids, Options tabs, Decisions 3-col, Ops cards) remain desktop ports. *(Gemini R1/R2/R3, Codex R1/R2/R3, Sonnet R1/R2/R3, Opus R1/R2/R3.)*

---

## 4. Strong-consensus findings (3-of-4)

- ◐ **DensityToggle is over-deployed on pages where it has no visible effect** (Events, Signal Lab, Strategies, Overview when no table is present) — false affordance. *(Codex R1/R2/R3, Sonnet R1/R2/R3, Opus R1/R2/R3; Gemini dissents — wants global state preserved with CSS tokens fixed instead.)*
- ◐ **`border-amber-400` active state at `OptionsLayout.tsx:56` collides with `--accent: #4B8BFF`** — single-line tokenization fix; visually jarring "different product" cue. *(Gemini R1, Sonnet R1/R2/R3, Opus R1/R2/R3; Codex did not separately call out the amber color but supports tokenization broadly.)*
- ◐ **OverviewRouteSwitch at `OverviewRouteSwitch.tsx:35-46` preserves seven query-param variants** (working / stream / conviction / copilot / living / legacy / default) without UI signal — product-confidence leak. *(Codex R1/R2/R3, Sonnet R2/R3 conceded, Opus R2/R3 conceded; Gemini did not flag this.)*
- ◐ **Decisions `xl:grid-cols-[360px_minmax(0,1fr)_420px]` breakpoint at `Decisions.tsx:207` should be `lg:` with column-width recalibration** — 1024-1280px users (common laptop widths) currently get the full single-column linear stack. *(Opus R1/R2/R3, Sonnet R2/R3 conceded, Codex R3 supports; Gemini emphasized mobile master-detail rather than the breakpoint.)*
- ◐ **Decisions `Decisions.tsx:355-363` `EmptyFilter` contains a 🌱 emoji** — violates the no-emoji discipline in user-global instructions on a decision-audit page that requires restrained tone. *(Sonnet R1 first-flagged; conceded by Opus R2 and Codex R2; Gemini did not separately flag.)*
- ◐ **Risk "Generate explanation" button at `RiskDashboard.tsx:124-132` is undersized and miscopied** — 11px text, looks like a debug control, wrong verb ("Generate explanation" is API vocabulary; should be "Why?" or "Explain this view"). *(Codex R1, Gemini R1, Opus R1/R2/R3, Sonnet R1/R2/R3.)*
- ◐ **GuardrailsToggleButton at `OptionsLayout.tsx:44-46` may be UI-only (not wired to data filter)** — must be verified or removed; a toggle that looks functional but isn't is fakes-by-UI. *(Opus R1, Sonnet R2; conceded by Codex R3; Gemini did not separately verify.)*
- ◐ **Loading-state inconsistency** — ActionQueue has a polished skeleton, SignalLab shows "Loading…" text, Overview.tsx shows nothing, EventsResearchPage has no indicator. *(Sonnet R1/R2 framed as systemic, Opus R2 conceded, Codex R3; Gemini did not call out the cross-product pattern.)*
- ◐ **Ops 16 cards (`Ops.tsx:21-36, :211-256`) need collapsible super-section grouping** — Live / ML / Engine / Replay or similar 3-4 group taxonomy. *(Gemini R1/R3, Codex R1/R3, Sonnet R1/R3; Opus framed it as "15 cards into 4 super-sections.")*

---

## 5. Disagreements that did NOT converge

1. **DensityToggle: hide on inert pages vs. wire globally and keep visible.**
   - Gemini R2/R3: *Keep visible globally.* The setting is global app state; hiding implies it only applies locally; fix the `--pi-space-*` CSS tokens to actually scale text leading and card padding on non-table pages.
   - Codex R3: *Hide where inert in Phase 15, then make density genuinely global later.*
   - Sonnet R3: *Hide via `showDensity` prop conditional render.* False affordance is worse than missing control.
   - Opus R3: *Hide.* "A control whose effect the user cannot perceive is worse than a missing control — it teaches them controls in this product don't do what they say."
   - **Discipline lock that arbitrates:** the brief mandates "preserve density modes (compact / cozy / spacious)." Preserving density does *not* require the toggle to render on every page; it requires the user's chosen density to apply everywhere it has visible effect. The 3-of-4 majority position (hide on inert pages) honors the lock more precisely than Gemini's "keep visible." **Recommended arbitration: hide on inert pages in Phase 15; revisit token wiring in Phase 16.**

2. **PicksPage launcher card ordering: match `page_flow.ts` or keep "executive reading flow."**
   - Sonnet R1: *Reorder to match `page_flow.ts`* (Overview → Events → Action Queue → Strategies). Sonnet R3 conceded after seeing the comment at `PicksPage.tsx:198-200`.
   - Opus R2/R3: *Keep current order* (signals → catalysts → strategies → portfolio). The order is intentional and documented; Stripe-style "action first," not Bloomberg-style "context first." Add tiny "1/2/3/4" reading-order glyphs if discoverability worries.
   - Gemini R2: *Keep current order* — "a dashboard shouldn't strictly mirror a linear workflow; it should prioritize the most actionable items first."
   - Codex R3: *Keep action-first order* but fix contradictory NextStep copy and reduce duplicated metrics.
   - **Discipline lock that arbitrates:** UX-5 progressive abstraction (3-of-4 lock) and the documented intent at `PicksPage.tsx:198-200` favor keeping action-first order. **Recommended arbitration: keep order; add reading-order glyphs; fix the contradictory NextStep rationale at `PicksPage.tsx:264-271` that says "see catalysts first" while linking to Action Queue.**

3. **Source Serif 4 for AI narrative blocks (PageChapter, Calm Cards, Copilot stories).**
   - Gemini R1/R2/R3: *Yes (reduced form in R3).* "A deliberate serif contrast for AI synthesis blocks creates a premium, editorial reading experience novices appreciate."
   - Sonnet R2: *Reject.* M-L effort; medium regression; brief forbids "atmospheric visuals that reduce information clarity"; adding serif aestheticizes data without clarifying it.
   - Opus R2/R3: *Reject hard.* "One typeface, one scale. Adding a serif trains the user that AI-text is visually different from human-text — wrong direction for an AI-native OS where the model *is* the product."
   - Codex R3: *Reject (no serif and no fake liveness; use motion only on real state changes).*
   - **Discipline lock that arbitrates:** the brief explicitly forbids "atmospheric visuals that reduce information clarity." Serif font for AI blocks falls inside that prohibition. **Recommended arbitration: reject. The clarity gap is microcopy, not typography.**

4. **Ambient TopStrip motion when engine is "thinking."**
   - Gemini R1: *Yes — subtle, non-distracting motion to indicate background pipeline activity.*
   - Opus R2/R3: *Reject hard.* "Atmospheric visual that reduces information clarity. Also lies — the engine is *not* thinking continuously; it ticks on a scheduler. Bloomberg never animates without a state change."
   - Codex R3: *Reject (no fake liveness; motion only on real state changes).*
   - Sonnet R2: *Implicitly rejects via "no atmospheric" stance.*
   - Gemini R2: *Conceded* on ambient motion.
   - **Discipline lock that arbitrates:** "no atmospheric visuals" + "no fabricated AI states." Pulsing animation implies continuous activity that doesn't exist on a scheduled pipeline. **Recommended arbitration: reject. The premium move is one motion vocabulary applied only on real state change (200ms tint when `last_pipeline_at` changes).**

5. **Action Queue bulk-execute affordance (multi-select / "execute all").**
   - Opus R1: *Yes — Linear and Stripe both let you act on N items at once.*
   - Gemini R2: *No — friction is a feature.* "This is an AI paper-trading evaluation OS, not an execution broker. Adding bulk approval bypasses the 'validate and read the reasoning' step that the entire product is built to enforce."
   - Codex R3: *Add keyboard navigation and compare/pin later, not bulk execution.*
   - Opus R3: *Revised — Gemini is right.* "Keep individual review; add j/k keyboard navigation instead."
   - **Discipline lock that arbitrates:** the product is a paper-trading research surface, not an execution venue. Bulk-execute would compromise the "see the working" lock from UX-4. **Recommended arbitration: no bulk-execute. Phase 17 may add j/k keyboard navigation per item.**

6. **Decisions mobile detail navigation: bottom sheet vs. sub-route vs. scroll-into-view.**
   - Gemini R1/R3: *Sub-route master-detail* (clicking a timeline entry navigates to a sub-route). Updated R3: *swipeable bottom sheet*.
   - Sonnet R1: *Scroll-into-view on selection.*
   - Opus R2: *Bottom sheet on tap (in-page, no URL change)* — sub-route is a navigation cliff because back-button breaks and deep-links proliferate.
   - Sonnet R3: *Phase 15 ships scroll-into-view as the interim; Phase 17 ships bottom sheet.*
   - **Discipline lock that arbitrates:** Linear's mobile pattern (in-page sheet, no URL change) is the premium reference. **Recommended arbitration: scroll-into-view in Phase 15 (cheap); bottom sheet in Phase 17 (correct premium); reject sub-route entirely.**

---

## 6. Cross-product findings

### 6.1 Design-system inconsistencies

The largest cross-product finding is **three coexisting frame systems on one product**:

1. **picks-root / `--pi-*` tokens** — `apps/web/src/lib/picks/picks.css` (5178 lines). Used by Overview (PicksPage), Action Queue, Events, Signal Lab, Strategies. The "Phase 8+ canon."
2. **`max-w-[…] mx-auto px-X py-Y` Tailwind shells with `u-card`** — Decisions, RiskDashboard, ResearchLab, Ops, PortfolioTerminal. UX-1 era.
3. **Tailwind `zinc-*` hardcodes** — Options sub-pages (`OptionsChainPage.tsx:42-46`, `OptionsRiskDashboardPage.tsx:22, :29`, `OptionsStrategyDiagnosticsPage.tsx:122-157`).

The `picks-root picks-root-inline` bridge (used in Decisions:87, RiskDashboard:45, ResearchLab:31, Ops:47) lets PageChapter render in legacy pages, but the *body* of each legacy page is still its own design world. CopilotHoldings additionally introduces a fourth token namespace (`--copilot-type-24`, `--copilot-type-15` from `lib/copilot/tokens.css`).

A single buy signal can render in three different greens depending on which surface it appears in: picks-* uses its own action palette (`picks.css:14-48`, emerald 400 / red 400), `index.css:65-72` defines `--success: #26CA72`, and Options uses raw zinc-*.

### 6.2 Navigation inconsistencies

- **Three nav idioms in production:** SideNav (primary, FLOW + SECTIONS metadata with `next` indicator at `SideNav.tsx:65-79`), Options 12-tab `flex-wrap` with amber border (`OptionsLayout.tsx:48-64`), Alpha Lab custom underline tab buttons (`ResearchLab.tsx:50-62`).
- **Four header patterns:** picks-header (Overview/ActionQueue/Events/SignalLab/Strategies), `<PageGuide>` eyebrow + title (Decisions/Risk/Portfolio), `data-test="options-X-intro"` with `u-caption-2` eyebrows (Options sub-pages), `<Label>` + `u-title-lg` + chip (ResearchLab).
- **Route-level discoverability gaps:** `OverviewRouteSwitch.tsx:35-46` exposes seven query-param variants without UI signal; `PortfolioRouteSwitch.tsx:17-22` exposes brief↔working without a visible toggle.
- **PageChapter / NextStepCard adoption is incomplete:** PageChapter present on 9 of 11 pages (missing on Options nested routes and PortfolioTerminal); NextStepCard present on 6 of 11 (missing on Overview.tsx, PortfolioTerminal, RiskDashboard, AlphaLab, Ops).
- **NextStepCard rationale microcopy can contradict the destination link** — `PicksPage.tsx:264-271` says "see what changed in catalysts first" while linking to Action Queue.

### 6.3 Typography inconsistencies

- `--fs-hero: 28px / --fs-title: 22px / --fs-body: 14px` defined at `index.css:101-106`.
- `picks-title` uses `clamp()` between 22-44px depending on density (`picks.css:3250, 3322`).
- CopilotHoldings uses `--copilot-type-24` and `--copilot-type-15` (separate token namespace).
- Options uses raw `text-xl`, `text-base`, `text-sm`, `text-xs` Tailwind classes.

There are at least three independent type scales rendered side-by-side. A user navigating Overview → Portfolio → Options sees three different body sizes for the "same" body text.

### 6.4 Density inconsistencies

DensityToggle is rendered on Overview, Action Queue, Events, Signal Lab, Strategies — but only Overview's PortfolioSnapshot and Action Queue's PickBox meaningfully respond to it. Events / Signal Lab / Strategies expose a control that does almost nothing visible. Legacy pages (PortfolioTerminal, Decisions, Risk, Alpha Lab, Ops) do not participate in the density contract at all and read at a different scale. Phase 12 flagged this; it's still there.

### 6.5 Interaction inconsistencies

Four chip/tab interaction patterns coexist:
- **FilterBar** (Action Queue) uses `role="group"` + `aria-pressed` (`FilterBar.tsx:45-52`) — correct button-group semantics.
- **Decisions filter buttons** use raw `onClick` with custom border-color inline styles (`Decisions.tsx:219-231`).
- **Options tab nav** uses NavLink with `isActive`-derived className and amber border.
- **ResearchLab tab nav** uses raw `<button>` elements with no `role="tablist"` / `role="tab"` / `aria-selected` (Sonnet R1 accessibility gap).

Loading states are similarly fragmented: ActionQueue has an explicit skeleton (`ActionQueuePage.tsx:114-128`); SignalLab shows "Loading…" text; Overview.tsx renders nothing while hooks load async; EventsResearchPage has no indicator at all.

---

## 7. Elite-gap thesis

The four panelists named the elite gap differently, but the core diagnosis converges. Opus called it **"discipline of singularity"** — every fact appears exactly once, in exactly one visual treatment, in exactly the place it belongs. Codex called it **"hierarchy, progressive disclosure, and 'what changed / what matters next' synthesis from real data."** Sonnet called it **"the difference between correctly wired and honest to the user."** Gemini called it **"pervasive erosion of honest-data trust through silent fallbacks, hardcoded UI placeholders, and fragmented design systems."** All four diagnoses point to the same root cause: the product currently shows all truthful information rather than the next truthful decision, and a small number of surfaces show information that isn't even truthful.

The specific elite-product behaviors panelists called out as missing:

- **Stripe ships one number above the fold.** Today's volume is the single hero on the dashboard; everything else is secondary. This product currently shows NAV three times in the upper viewport (TopStrip NAV, PortfolioSnapshot NAV hero, Overview header context) and posture in three places (subtitle, PageChapter NOW, why-no-buys panel). Stripe would *not* ship a launcher grid of four equal cards — Stripe always picks one primary action.
- **Linear ships everything in one typeface.** Inter at five sizes. This product runs Inter (`--font-ui`), JetBrains Mono (`--font-mono`), and a third copilot scale (`--copilot-type-*`) all rendered side-by-side. Linear's only ambient motion is the cursor in the command palette; it never animates without a state change.
- **Perplexity leads with synthesis, not source list.** A Perplexity-grade Events page would lead with a one-paragraph synthesis ("Today's catalysts: TSLA earnings, Fed minutes, NVDA 8-K"), then sources below. The current Events page has zero synthesis — it's pure source list, and the wrapper-level `.catch(() => setLoading(false))` at `EventsResearchPage.tsx:27` makes a backend failure indistinguishable from a clean empty day.
- **Bloomberg earns 12 tabs by earning the function-key vocabulary.** Bloomberg uses an abbreviation system (`OMON`, `SKEW`, `IVAT`) that turns the tab list into a memorizable command set. Until this product earns that vocabulary, 12 peer tabs in Options is unjustifiable. The Bloomberg comparison validates the unanimous call to collapse to four grouped sections — and refutes any "but Bloomberg does it" defense.

The discipline locks (no fakes / no atmospheric / honest data) imply a clear path forward: **the elite gap closes by removing, not adding.** Removing the MarketTicker from above-the-fold on Overview (Opus's highest-leverage emotional-read change), removing the duplicate metric line from launcher card #1, removing the Signal Lab tombstone, removing the static fallback registry rendering, removing the hardcoded JobRow statuses, removing the amber active border, removing the false-affordance density toggles, removing the `Generate explanation` API verb. Every additive proposal that would compound chrome (serif font, ambient AI motion, more "Start here" cards, more disclaimers) was rejected by 3-of-4 panelists for the same reason: this product needs less chrome and more committed hierarchy.

If Phase 15 ships the four P0 truth fixes plus the hierarchy-and-microcopy moves identified below, the product crosses from "high-end developer tool with caring scaffolding" to "premium product that respects the user's first ten seconds." Phase 16's Options collapse and design-system unification take it to ~8.5. Phase 17's AI-native moments and mobile-native re-IA are unlocks beyond that — but those are aspiration, not rescue. **The product no longer needs rescuing; it needs committing to one voice.** (Opus R1 final verdict, Sonnet/Codex/Gemini all converge.)

---

## 8. Phase 15 — next phase to ship

Ordered strictly by: UX impact → novice clarity → mobile quality → trustworthiness → implementation safety. Sonnet's effort/risk estimates used as primary; Codex/Gemini disagreement flagged where present.

### P0 — Truth fixes (non-negotiable; all panelists converge)

**1. Replace hardcoded `JobRow` statuses or label as static placeholder**
- File:line — `apps/web/src/pages/Ops.tsx:262-267`
- Effort: S | Regression risk: low
- Why P0: Unanimous trust violation. A literal `last="ok"` is a brand-killer on a system-health page that contradicts the product's core honest-data premise. Replace with real `useScheduledJobs()` hook OR, per Opus's premium-detail moment, replacement copy `"Status pending — see scheduler logs"` inside `<ExpertDetails>`, not a fake "ok" pill.
- Endorsed by: G/C/S/O (all four)

**2. Label or hide Alpha Lab static fallback registry**
- File:line — `apps/web/src/pages/ResearchLab.tsx:128` (and content range `:85-126`)
- Effort: S | Regression risk: low
- Why P0: Unanimous P0 fakes-by-omission. The conditional `(shadow && shadow.length > 0) ? shadow : knownSignals` renders static entries visually identical to live data. Per Opus's premium-detail moment, NEW pill above the registry: `"Static baseline — no live shadow signals this cycle"` at quiet `--fg-3`, not a warning ribbon.
- Endorsed by: G/C/S/O

**3. Restore visible fetch error on Events page**
- File:line — `apps/web/src/pages/EventsResearchPage.tsx:27`
- Effort: S | Regression risk: low
- Why P0: Unanimous P0 truth violation. The `.catch(() => { if (!cancelled) setLoading(false); })` swallow makes a 500 indistinguishable from a clean empty day. Use the existing `<FetchError>` component from Action Queue — do not invent a new error visual.
- Endorsed by: G/C/S/O

**4. Verify or remove `GuardrailsToggleButton`**
- File:line — `apps/web/src/pages/options/OptionsLayout.tsx:44-46`
- Effort: S | Regression risk: low
- Why P0: A toggle that looks functional but isn't is fakes-by-UI. If kept, the off-state must visibly change something. If it can't, remove.
- Endorsed by: O (Opus first-flagged R1), S (Sonnet R2 conceded), C (Codex R3); G did not separately verify

**5. Remove Signal Lab "Not yet wired" tombstone**
- File:line — `apps/web/src/pages/SignalLabPage.tsx:170-183`
- Effort: S | Regression risk: low
- Why P0: ~280px of empty content on the credibility page. Per Opus's premium-detail moment, replace with one line inside `<ExpertDetails>`: `"Backtest validation pending — see Ops > ML pipeline."` Not a card. One line.
- Endorsed by: G/C/S/O

**6. Remove emoji from Decisions `EmptyFilter`**
- File:line — `apps/web/src/pages/Decisions.tsx:355-363` (the 🌱 glyph at `:359`)
- Effort: S | Regression risk: low
- Why P0: Violates the no-emoji discipline in user-global instructions on a decision-audit page that requires restrained tone. Per Opus, NEW glyph: a quiet `→` or `·` at `--fg-3`. Not an icon.
- Endorsed by: S (first-flagged R1), C (R2 conceded), O (R2 conceded), G (R3 endorses removal)

### P0 — Mobile blocker

**7. Fix Options tab nav: `flex-wrap` → `overflow-x-auto` single-row on mobile**
- File:line — `apps/web/src/pages/options/OptionsLayout.tsx:48`
- Effort: S | Regression risk: low
- Why P0: Unanimous mobile failure. Single class swap; no routing change; all 12 URLs preserved. The structural collapse to 4 grouped tabs is Phase 16; the immediate single-row scroll is Phase 15.
- Endorsed by: G/C/S/O

### P1 — Hierarchy and discoverability

**8. Add visible Portfolio view toggle (Brief / Working) AND flip default to brief**
- File:line — `apps/web/src/pages/copilot/PortfolioRouteSwitch.tsx:17-22`
- Effort: S+S | Regression risk: medium (per Sonnet R2 — PortfolioTerminal is the highest-trust page; explicit QA sign-off required before flip)
- Why P1: Unanimous. CopilotHoldings (brief view) is URL-only discoverable; the most premium AI-narrative surface in the product is hidden from default visitors. Per Opus's premium-detail moment, the toggle UI is a 2-segment pill in the Portfolio header reading `Brief | Working`, same primitive as DensityToggle.
- Endorsed by: G/C/S/O

**9. Remove MarketTicker from above-the-fold on Overview (Overview-only)**
- File:line — `apps/web/src/pages/PicksPage.tsx` (and shell composition)
- Effort: S | Regression risk: low
- Why P1: Opus's highest-leverage emotional-read change. Ticker is the page's biggest motion source competing with the actual answer (NAV / posture). Per Opus, the *transition* matters: ticker fades out (200ms ease-out) when route is `/overview`, not jump-cut.
- Endorsed by: O (R2 first-named); G (R3 endorses)
- *Note: Codex and Sonnet did not separately call for ticker removal but did not contest it either; flagged as a strong-recommendation by Opus rather than 4-of-4 unanimous.*

**10. Hide DensityToggle on inert pages (Events, Signal Lab, Strategies, Overview when no table)**
- File:line — Multiple page files (conditional `showDensity` prop)
- Effort: S | Regression risk: low
- Why P1: 3-of-4 majority. False affordance erodes trust in every other control. Per Opus, conditional render — not a disabled state. A grayed-out toggle is worse than no toggle.
- Endorsed by: C/S/O; G dissents (wants global state preserved with token wiring fix instead — see §5 disagreement #1)

**11. Kill `border-amber-400` in OptionsLayout active state**
- File:line — `apps/web/src/pages/options/OptionsLayout.tsx:56`
- Effort: S | Regression risk: low
- Why P1: Single token swap eliminates the most visually jarring design-system collision in the product. Per Opus, NEW: `border-[var(--accent)]` (the app's `#4B8BFF`). Not a new amber token.
- Endorsed by: G/S/O; C supports tokenization broadly

**12. Fix Decisions 3-col breakpoint AND column widths**
- File:line — `apps/web/src/pages/Decisions.tsx:206-207`
- Effort: S-M | Regression risk: low (Sonnet R3 specifically flagged the column-width math: at `lg:` with a 220px sidebar, the original 360/420 fixed columns leave near-zero for the middle detail column — must shrink to `lg:grid-cols-[280px_minmax(0,1fr)_360px]` or `[320px_minmax(0,1fr)_360px]` per Opus's R3 refinement)
- Why P1: 1024-1280px users (common laptop widths) currently get the full single-column linear stack. Detail column must become the flex anchor.
- Endorsed by: O (R1 first-named), S (R2 conceded), C (R3 supports); G did not separately flag breakpoint but supports detail-anchor reorder

**13. Add readiness score interpretation band to Signal Lab**
- File:line — `apps/web/src/pages/SignalLabPage.tsx` (around `:129-131` hero score)
- Effort: S | Regression risk: low
- Why P1: 0-100 score has no interpretive value without a band (0-40 red, 41-70 amber, 71-100 green) — pairs directly with tombstone removal (item #5) since both ship in the same Signal Lab sprint.
- Endorsed by: G/C/S/O (Codex frames as "interpretation band: safe to inspect / use caution / data incomplete / do not act")

**14. Add NextStepCard at the route level for PortfolioTerminal, RiskDashboard, AlphaLab, Ops**
- File:line — `apps/web/src/pages/copilot/PortfolioTerminal.tsx`, `apps/web/src/pages/RiskDashboard.tsx`, `apps/web/src/pages/ResearchLab.tsx`, `apps/web/src/pages/Ops.tsx`
- Effort: S | Regression risk: low
- Why P1: Closes the FLOW story on four legacy pages without touching internals. Per Opus's refinement: add at the *route level* (so brief↔working both inherit on Portfolio), not in each page body. Per Opus's premium-detail moment: the rationale string must be derived from real data (open trade count, risk flag count) — generic rationales are visible engineering smell.
- Endorsed by: C (R1 first-named the gap), S (R2 confirmed), O (R2 refined to route-level); G implicitly via consistency call

**15. Microcopy translation pass — round 2 (verbatim OLD/NEW from Opus R3)**
- File:line — Five confirmed engineering-vocabulary leaks
- Effort: S | Regression risk: low
- Why P1: Every leaked engineering phrase costs premium feel. Per Opus, "verbs become questions; `Why?` is the most premium copy on the page."
  - `PicksPage.tsx:268`: OLD `"${riskCount} signal(s) flagged for risk — see what changed in catalysts first"` → NEW `"${riskCount} picks need a closer look — start with what changed today"`
  - `EventsResearchPage.tsx:33-37`: OLD `"N symbols from active recommendations · SEC EDGAR feed live"` → NEW `"Tracking N symbols · filings update through the day"`
  - `OptionsLayout.tsx:42`: OLD `"Paper-trading guidance · simulated only · no live execution"` → NEW `"Paper trading — nothing here places real orders"`
  - `RiskDashboard.tsx:124-132` button: OLD `"Generate explanation"` → NEW `"Why?"` (and bump to a primary action affordance, not 11px text)
  - `FilterBar.tsx:33-35`: OLD `"high-confidence" / "freshest" / "highest-risk"` → NEW `"≥70% confidence" / "<6h old" / "Risk-flagged"`
- Endorsed by: O (named all five with verbatim alternatives R3); S (R2 supported microcopy translation pass); G/C support direction

---

## 9. Phase 16 — after Phase 15

Ordered same criteria. Phase 16 is "coherence + Options collapse + progressive disclosure"; effort skews M-L; regression risk skews medium-high.

**1. Options IA — collapse 12 tabs to 4 visual groups, preserve all 12 URLs**
- File:line — `apps/web/src/pages/options/OptionsLayout.tsx` + all 12 sub-pages
- Effort: L (Sonnet R2 specifically warned: do NOT change URL structure — breaks deep links; change only the visual nav presentation, group tabs into 4 headers with secondary tabs, test all 12 sub-pages independently after) | Regression risk: high
- Why P1 / Why 16 not 15: Too risky to bundle with P0 truth fixes; requires deep QA of nested routes. Proposed groups (per Opus): **Overview / Trades & Risk / Strategy Lab / Engineering**.
- Endorsed by: G/C/S/O (universal convergence on the collapse; only the exact taxonomy varies slightly)

**2. Tokenize Options out of `zinc-*` and `amber-*` into `--pi-*` system**
- File:line — `apps/web/src/pages/options/*` and `apps/web/src/components/options/*`
- Effort: L | Regression risk: high
- Why P1 / Why 16: Visual unification follows truth/mobile fixes; do after tab consolidation, not before.
- Endorsed by: G/C/S/O

**3. Group Ops 16 cards into 4 collapsible super-sections (Live / ML / Engine / Replay)**
- File:line — `apps/web/src/pages/Ops.tsx` (cards at `:21-36, :211-256`)
- Effort: M | Regression risk: low (purely additive layout; Sonnet R3 flag: wait for Phase 15 Ops truth fix so grouping doesn't hide a fixed problem)
- Why P1 / Why 16: Alleviates the scroll-of-death; secondary to the P0 truth fix on hardcoded statuses.
- Endorsed by: G/C/S/O

**4. "What changed" temporal-context pills across Overview / Events / Action Queue / Portfolio / Risk**
- File:line — Across multiple pages; requires session/run comparison plumbing
- Effort: M-L | Regression risk: medium (requires session state — localStorage or sessionStorage)
- Why P1 / Why 16: Codex's "still missed" item — premium investing OS should answer "new since last run," "flipped since yesterday," "stale because source unavailable." Honest if derived from existing timestamps.
- Endorsed by: O (R1 first-named "what changed instinct"), C (R2 elevated to central), G (R3 endorsed); S accepts as Phase 16-17 work

**5. Action Queue group-level rationale (top decision factors per action group)**
- File:line — `apps/web/src/pages/ActionQueuePage.tsx`, `apps/web/src/components/picks/ActionQueue.tsx`
- Effort: M | Regression risk: medium (Sonnet R3: touches ActionQueue card rendering logic)
- Why P1 / Why 16: Group cards by dominant `pickTags` cluster (e.g., "rate-cut beneficiaries," "earnings-week trims") — micro-rationale data exists; just not surfaced in groups. Action Queue is already strong; enhancement waits until broken pages stabilized.
- Endorsed by: C (R1 first-named), O (R2), S supports via group rationale framing

**6. Replicate "Why no buys?" pattern on Strategies / Signal Lab / Risk / Options-Overview empty states**
- File:line — `StrategiesPage.tsx`, `SignalLabPage.tsx`, `RiskDashboard.tsx`, `apps/web/src/pages/options/OptionsOverviewPage.tsx`
- Effort: M | Regression risk: low
- Why P1 / Why 16: Proven pattern; requires per-page copy and conditional logic per posture; additive but non-trivial to get microcopy right.
- Endorsed by: G/C/S/O

**7. Strategies hero metric (active / blocked / eligible count) — NOT another "Start here" card**
- File:line — `apps/web/src/pages/StrategiesPage.tsx`
- Effort: M | Regression risk: low
- Why P1 / Why 16: Replaces what would be the 5th instance of the "Start here" pattern (which Sonnet's own cross-product finding flagged as overused) with a data-driven hero metric. Requires deriving strategy-state aggregates.
- Endorsed by: O (R2 — explicit refinement of Sonnet's add-Start-here proposal); C (R3 supports state panels broadly)

**8. Move OverviewRouteSwitch experimental variants behind internal flag**
- File:line — `apps/web/src/pages/copilot/OverviewRouteSwitch.tsx:35-46`
- Effort: S | Regression risk: low
- Why P1 / Why 16: Codex's catch — seven query-param variants for a single route is a "product confidence" leak. Move experimental variants behind a hidden internal flag, not user-discoverable URL space.
- Endorsed by: C (R1), O (R2 conceded), S (R2 conceded as Phase 15 banner add, full move in 16)

**9. Expand ExpertDetails to legacy advanced content**
- File:line — Decisions diagnostics, Risk advanced tables, AlphaLab internals, Ops long-tail cards, Options diagnostics/evaluation/support pages
- Effort: M | Regression risk: medium
- Why P1 / Why 16: Progressive disclosure should be systematic; ExpertDetails is the right pattern but underused on Decisions, Risk, Research, Ops, Options diagnostics.
- Endorsed by: C/S/O; G implicitly supports

**10. Unified loading-skeleton pattern across all pages**
- File:line — EventsResearchPage, SignalLabPage, PortfolioTerminal, RiskDashboard
- Effort: M | Regression risk: low (Sonnet: ActionQueue skeleton is the template; pattern is additive; Phase 15 truth fixes land first so skeleton pattern isn't masking errors)
- Why P1 / Why 16: ActionQueue's skeleton is canon; absence elsewhere reads as unfinished. Per Opus, skeleton *shape* must match loaded content silhouette, not generic gray bars.
- Endorsed by: S (R1 first-framed as systemic), O (R2 conceded), C (R3 supports)

**11. Add Events catalyst-brief synthesis hero (top 3 catalysts + affected symbols)**
- File:line — `apps/web/src/pages/EventsResearchPage.tsx`, `apps/web/src/components/portfolio/MarketEvents.tsx`
- Effort: M | Regression risk: low
- Why P1 / Why 16: Events is currently a passive feed dump; a Perplexity-grade page would lead with synthesis ("TSLA flipped buy→hold (8-K filed yesterday)") then sources below.
- Endorsed by: C/G/O; S supports via "highest-priority catalyst hero"

**12. Decisions design-system unification — migrate body to picks-root frame**
- File:line — `apps/web/src/pages/Decisions.tsx`
- Effort: L | Regression risk: medium (Sonnet R2 flag: many `data-test` selectors used by tests)
- Why P1 / Why 16: Two visually-incompatible design systems on one page (`picks-root picks-root-inline` PageChapter at top inside `max-w-[1680px] mx-auto px-8 py-8` Tailwind shell). Thread calm card into PageChapter.
- Endorsed by: O (R1 first-named), S (R2 supports as Phase 16), C (R3 supports)

---

## 10. Phase 17 — last (highest ambition / lowest mobile priority)

Phase 17 is "premium product feel" — XL effort, polish on stable foundations, AI-native moments and mobile-native re-IA. **Should not start until Phase 15 truth fixes and Phase 16 coherence work are stable.**

**1. Single motion vocabulary tied to real state changes only**
- File:line — `apps/web/src/index.css` (`--motion-fast: 120ms`, `--motion-base: 200ms` ease-out tokens)
- Effort: M | Regression risk: low
- Why 17: Cross-page taste arbitration; safe standalone. The 200ms tint on TopStrip when `last_pipeline_at` changes is the correct "AI presence" moment — not ambient animation. Per Opus's R3 explicit rejection: this is *not* Gemini's ambient AI motion proposal.
- Endorsed by: O (R1 first-named), C (R3 supports), S supports

**2. Persistent AI assistant rail (page-scoped, stale-gated)**
- File:line — `apps/web/src/components/shell/Shell.tsx` (new shell slot)
- Effort: XL (Sonnet R2 specifically corrected Opus's L estimate to XL — requires cross-page context assembly, stale-data gating per `useFetchWithError`, new shell slot that doesn't conflict with SideNav/TopStrip sticky stack, page-disambiguation layer) | Regression risk: high
- Why 17: Must wait for design-system unification (Phase 17 item 1 below). The existing `InsightDrawer` at `RiskDashboard.tsx:31-38` is the proof-of-concept precedent — but page-scoped and operator-triggered. A persistent global rail is a different beast.
- Endorsed by: O (R1 deferred to Phase 17), C (R3 endorses scoped affordance), S (R2 sized correctly)

**3. Inline "Why?" hover on numeric heroes**
- File:line — Readiness composite, drawdown, exposure pct — across pages
- Effort: L | Regression risk: medium
- Why 17: Requires explanation infra at every numeric source. Per Opus, button copy must be `"Why?"` not `"Generate explanation"` (microcopy refinement).
- Endorsed by: O (R1), C (R3 supports as scoped AI explanation affordance)

**4. Mobile-native Decisions detail: bottom sheet on row tap**
- File:line — `apps/web/src/pages/Decisions.tsx`
- Effort: L | Regression risk: medium
- Why 17: Requires Phase 16 Decisions layout stabilization first. Bottom sheet (in-page, no URL change) is the correct premium pattern per Opus — explicitly *not* sub-route. The Phase 15 scroll-into-view fix is the interim.
- Endorsed by: G/O (Gemini converged R3 to bottom sheet); S (R3 sequenced as interim → Phase 17)

**5. Mobile-native re-IA — separate top mobile widget composition**
- File:line — Cross-cutting; requires Phase 16 Options collapse first
- Effort: XL | Regression risk: high
- Why 17: Highest-ambition item. Per Opus: posture + 1 actionable signal as top widget; horizontal swipe between Today / Working / Risk; not just responsive desktop. Robinhood-grade mobile product treats mobile as a different IA, not a port.
- Endorsed by: O (R1 first-framed), C (R3 supports), S accepts as XL

**6. Merge picks-* and u-card systems into one canonical layout**
- File:line — All pages; anchored in `apps/web/src/index.css` + `apps/web/src/lib/picks/picks.css`
- Effort: XL | Regression risk: very high (Sonnet R2: "This is the whole design system. Don't rush. Only safe to unify when the page count is stable and all surfaces are confirmed correct.")
- Why 17: Touching design system before Phase 15-16 truth and coherence work would destabilize a moving target.
- Endorsed by: G/C/S/O all defer to Phase 17

### Deferred-or-rejected items (Gemini's serif/motion proposals)

- **Source Serif 4 for AI narrative blocks** — *Rejected (3-of-4 panelists).* Rationale: brief forbids "atmospheric visuals that reduce information clarity"; one typeface, one scale (Linear/Stripe discipline); adding serif trains user that AI-text is visually different from human-text — wrong direction for an AI-native OS where the model *is* the product. (Sonnet R2, Opus R2/R3, Codex R3.) Gemini R3 still holds reduced form; arbitrated against by majority + brief discipline lock.
- **Ambient TopStrip motion when engine is "thinking"** — *Rejected (3-of-4 + Gemini R2 conceded).* Rationale: atmospheric and dishonest (engine ticks on a scheduler, not continuously); Bloomberg never animates without a state change; Linear's only ambient motion is the cursor in the command palette. (Opus R2/R3, Codex R3, Gemini R2 conceded.) Replaced by Phase 17 item 1 (motion only on real state change).
- **Bulk-execute on Action Queue (multi-select + "execute all")** — *Rejected.* Rationale: friction is a feature on a paper-trading evaluation OS; bulk approval bypasses the "validate and read the reasoning" step the entire product is built to enforce. (Gemini R2, Opus R3 revised, Codex R3.) Replaced by Phase 17 item considering j/k keyboard navigation per individual item.
- **Sub-route navigation for Decisions mobile detail** — *Rejected.* Rationale: navigation cliff; back-button breaks; deep-links proliferate; Linear's mobile pattern is in-page sheet, no URL change. (Opus R2, Sonnet R3, Codex R3.) Replaced by Phase 17 item 4 (bottom sheet).

---

## 11. Final answers to the 12 brief questions

**1. Is the app telling a coherent story page-to-page?** *Mostly.* The structural spine (`page_flow.ts:24-78`) is coherent and the PageChapter + NextStepCard threading makes it visible on newer pages. But visual delivery is fragmented by three coexisting design systems (picks-root / Tailwind legacy / Options zinc-*) and the journey breaks at PortfolioTerminal (no PageChapter) and Events (passive feed with no catalyst-to-signal join). The FLOW data structure is right; the lived path through it is not yet seamless.

**2. Does navigation feel linear/intelligent or fragmented?** *Both, depending on layer.* The SideNav is genuinely elite — FLOW + SECTIONS metadata with `next` indicator (`SideNav.tsx:65-79`) — Sonnet scored shell nav 8/10. But in-page navigation is fragmented across four idioms: FilterBar `aria-pressed`, Decisions custom inline `onClick`, Options NavLink, AlphaLab raw `<button>` with no `role="tablist"`. In-page nav is 4/10. Options' 12-tab `flex-wrap` and the seven query-param Overview variants are the worst fragmentation cases.

**3. Are users guided naturally Overview → Catalysts → Decisions → Execution → Portfolio → Risk?** *Possible, not yet automatic.* The PageChapter+NextStepCard pair makes it possible. It's not yet natural because (a) the PicksPage launcher order (signals → catalysts → strategies → portfolio) is intentional and documented at `:198-200` but not explained to the user; (b) the NextStepCard rationale at `PicksPage.tsx:264-271` says "see what changed in catalysts first" while linking to Action Queue — microcopy lies about routing; (c) Portfolio breaks the chain by defaulting to the dense terminal instead of brief. Fix the launcher reading-order glyphs and the NextStep microcopy and 80% of the flow coherence resolves.

**4. Which pages feel "dead" or passive?** *Four-page cluster.* Events (no synthesis layer; pure feed dump; silent fetch-error swallow); Signal Lab lower half ("Not yet wired" tombstone); Alpha Lab (worksheet aesthetic + static fallback registry rendering identically to live data); Ops middle band (15+ ungrouped cards with no hierarchy). All four share the same root cause: information shown without enough hierarchy or honest provenance.

**5. Which sections should become collapsible?** Ops 16 cards into 4 super-sections (Live / ML / Engine / Replay); Decisions diagnostics and "How to read this page" auto-collapse after first visit (localStorage flag, dismissible-not-default-collapsed per Opus's refinement); Risk full breakdowns and "Where this data comes from"; AlphaLab internals; Signal Lab backtest section (full removal until wired); Options Diagnostics/Evaluation/Decision Support/Decision Framing into ExpertDetails wrappers.

**6. Which sections should become sticky?** Decisions Timeline column at `lg+` on desktop only; FilterBar on Action Queue **desktop only** (Opus pushed back on Sonnet's mobile-sticky proposal — Phase 14f-F deliberately relaxed mobile sticky to TopStrip-only); Options tab nav as a single overflow-x row after the `flex-wrap` fix; OpsAnchorNav stack-coordinated with TopStrip. **Keep mobile sticky minimal** — universal panelist agreement.

**7. Which cards are visually noisy?** PortfolioSnapshot 8-12 metric grid (`PortfolioSnapshot.tsx:98-160`); Options Risk 4-KPI strip with no hierarchy; the `u-nonprod-ribbon` orange wash on Decisions diagnostic snapshot; Overview's 4-stacked-hero composition (TopStrip NAV / PageChapter NOW / Snapshot NAV / TodayPanel); Overview.tsx 5-card 30%-column right rail; Ops 16-card stack.

**8. Which cards are under-emphasized?** "Generate explanation" button on Risk (11px text confirmed at `RiskDashboard.tsx:124-132`); CopilotHoldings brief view (URL-only access, no UI affordance); the brief↔working toggle on Portfolio (non-existent in UI); the SideNav next-step indicator (9px chip at `SideNav.tsx:69-72`); Action Queue group rationale; Research verdict / provenance.

**9. Which sections waste vertical space?** PicksPage launcher duplicated metric line; Signal Lab tombstone block (~280px of "Not yet wired"); Decisions calm-card + chip-rail + AdvancedDetails 4-layer stack; Alpha Lab `mb-6` spacer at `ResearchLab.tsx:64`; Ops preamble (80 lines of PageGuide + Start-here before first operational card); Overview ps-secondary on mobile; PortfolioSnapshot loading skeleton; Options repeated banners on every subtab.

**10. Which sections are too dense?** Options Chain table; PortfolioTerminal 5-column NAV strip (`gridTemplateColumns: "2.2fr 1fr 1fr 1fr 1fr"`) on mobile; Decisions 3-column at sub-`xl` widths; Ops middle band (ML/engine/replay sections); Overview.tsx right column at narrow widths; Options Diagnostics/Evaluation/Decision Support/Decision Framing pages.

**11. Which pages fail on mobile ergonomics?** Options is the unanimous worst — 12-tab `flex-wrap` becomes 4+ rows of chips at 375px before any content. PortfolioTerminal NAV strip will overflow at 390px. Ops has no mobile-specific layout work — it's a "Scroll of Death." Decisions 3-col stacking loses split-column scrolling affordance. RiskDashboard 5 framing layers stacked vertically delay the first risk number. Overview.tsx 5-col NAV strip doesn't reflow.

**12. Which pages still feel "developer-built" instead of "premium product"?** Ops (hardcoded statuses + 16 cards + four card-style systems on one page); Options (12 tabs + amber active border + zinc hardcodes + `_TAB_GUIDE` defensive labeling + raw Tailwind layout); Alpha Lab (raw tab buttons, no PageChapter integration, static fallback rendering as live, `experimental` chip + "Research" eyebrow + "Alpha Lab" name = three labels for the same idea); Signal Lab middle/lower half (tombstone + uncalibrated composite-as-hero); RiskDashboard middle band (5-layer header stack + native OS checkbox + 11px "Generate explanation" button + KVTable density); Overview.tsx "System diagnostics" AdvancedDetails noise.

---

## 12. The one thing to NOT change

Each panelist named a single load-bearing decision they would not undo in Round 3:

- **Gemini R3:** *"The 'Why no buys?' explanation panel on the Action Queue must remain exactly as it is, as it represents the absolute pinnacle of trust-building AI product design in the entire codebase."*
- **Codex R3:** *"Do not undo the PageChapter / NextStepCard narrative spine; incomplete adoption is the problem, not the motif itself."*
- **Sonnet R3:** *"The PageChapter + NextStepCard narrative spine — the NOW / WHY / NEXT threading through page_flow.ts — is the single most load-bearing architectural decision in the codebase and would be a mistake to undo or dilute, even in the name of visual unification."*
- **Opus R3:** *"The PageChapter + NextStepCard narrative spine, and specifically the page_flow.ts FLOW chain (apps/web/src/lib/ui/page_flow.ts:24-78). This is the single most architecturally elite decision in the codebase — a typed, route-aware narrative graph that makes 'Overview → Catalysts → Decisions → Execution → Portfolio → Risk' a real data structure the UI consumes, not a hope. Premium-polish proposals to 'modernize headers' or 'unify hero patterns' must thread through PageChapter, not replace it."*

**Synthesis: the strongest "do not undo" lock is the `page_flow.ts` + PageChapter + NextStepCard narrative spine.** Three of four panelists named exactly this — the one outlier (Gemini) named the "Why no buys?" panel, which is itself an instance of the same broader principle (honest synthesis from real state). The unanimous architectural lock is therefore:

> **Phase 15+ hard architectural lock: the `page_flow.ts` typed FLOW graph and the PageChapter + NextStepCard threading on top of it are inviolable. All future phases must extend or thread through this spine — never replace, dilute, or work around it.** Premium-polish proposals (header unification, hero pattern overhaul, design-system merge in Phase 17) must thread through PageChapter, not bypass it. If any future phase ships every other recommendation but breaks this spine, the seven query-param Overview variants, the four header patterns, and the three frame systems will reassert themselves immediately. PageChapter is the load-bearing structure; touch around it, never under it. Additionally, the **"Why no buys?" honest-synthesis pattern at `ActionQueuePage.tsx:146-170`** is the canonical instance of this lock applied to per-page empty states, and must be replicated (not redesigned) on Strategies / Signal Lab / Risk / Options-Overview empty states in Phase 16.

---

## 13. Appendix — raw transcript inventory

| Round / Panelist | File | Bytes (approx) | Words (approx) | One-line summary |
|---|---|---:|---:|---|
| R1 / Gemini | round1/gemini.md | ~20KB | ~2,200 | Per-page tabular audit, IA-first lens; flagged Options 12-tab and "Three Navs" problem; missed truth violations later conceded. |
| R1 / Codex | round1/codex.md | ~34KB | ~3,200 | File:line-grounded structural audit; named "mixed product eras"; correctly identified PortfolioTerminal NextStepCard gap and OverviewRouteSwitch query-param sprawl. |
| R1 / Sonnet | round1/sonnet.md | ~48KB | ~6,500 | Pragmatic implementer lens with effort/regression estimates; first-flagged Decisions emoji and loading-state inconsistency cross-product finding. |
| R1 / Opus | round1/opus.md | ~48KB | ~5,500 | Premium-taste lens; first-flagged Ops `JobRow last="ok"` and ResearchLab static fallback as P0 truth violations; named "discipline of singularity" elite-gap thesis. |
| R2 / Gemini | round2/gemini.md | ~10KB | ~1,400 | Conceded Ops/AlphaLab P0 truth violations to Opus; conceded Events to Sonnet; held density-toggle-global and serif-for-AI positions. |
| R2 / Codex | round2/codex.md | ~12KB | ~1,700 | Conceded Ops, AlphaLab, Events truth fixes; refuted Gemini's stale FilterBar P0 (Phase 13d already fixed); held targeted-patch-first sequencing position. |
| R2 / Sonnet | round2/sonnet.md | ~21KB | ~3,100 | Detailed effort/regression rebuttal; pushed back on Opus's L estimate for AI assistant rail (correct: XL); first-named GuardrailsToggleButton verification need; rejected Gemini's serif. |
| R2 / Opus | round2/opus.md | ~17KB | ~2,400 | Sharpest "removal vs addition" thesis; first-named MarketTicker-above-fold removal as highest-leverage emotional-read change; rejected Gemini's serif and ambient AI motion with file:line discipline. |
| R3 / Gemini | round3/gemini.md | ~11KB | ~1,600 | Final scores converged to 6.0 median; explicit residual disagreements on density/serif/bulk-execute/keyboard/bottom-sheet; "Why no buys?" as do-not-change. |
| R3 / Codex | round3/codex.md | ~12KB | ~1,600 | Final scores converged with overall 6.0 thesis; held action-first launcher order; rejected serif and ambient motion; PageChapter spine as do-not-change. |
| R3 / Sonnet | round3/sonnet.md | ~13KB | ~2,400 | Final scores converged; conceded launcher order to Opus; specified Decisions column-width math at `lg:` breakpoint; PageChapter spine as do-not-change. |
| R3 / Opus | round3/opus.md | ~17KB | ~2,200 | Final scores median 6.0; verbatim microcopy OLD/NEW for five engineering-vocabulary leaks; Stripe/Linear/Perplexity/Bloomberg specific comparisons; PageChapter spine as do-not-change. |

**Totals:** 12 transcript files, ~262KB, ~33,800 words combined. Brief at `docs/research/debates/PHASE_15_elite_ux/brief.md` adds ~15KB.

---

## 14. Appendix — what each panelist contributed uniquely

**Gemini.** Best at structural / IA framing. Round 1 gave the cleanest tabular per-page audit and the cleanest per-page priority calls, even where the truth-violation undercurrent was missed. Uniquely identified the "Three Navs Problem" (SideNav primary + Options amber-border tabs + Alpha Lab custom underline) as a single named cross-product finding. Pushed hardest on Bloomberg-Terminal aspirational lens and serif/motion premium proposals — all three of which were rejected by majority but produced the cleanest formal disagreements that sharpened the elite-gap thesis. Honest concessions in Round 2 to Opus (truth violations) and Sonnet (Events passivity) and graceful refusal to drop the serif position even after rejection. Uniquely held the "DensityToggle is global app state" position against the 3-of-4 hide majority — the only contested item that genuinely could go either way.

**Codex.** Best at file:line grounding and IA-graph reasoning. Round 1 produced the most line-citation-dense audit, particularly correct identification of `OverviewRouteSwitch.tsx:35-46` query-param sprawl that the other three missed, and the `page_flow.ts:27-78` flow-graph consumption pattern as the load-bearing architectural decision. Uniquely framed the elite-gap as "hierarchy + progressive disclosure + 'what changed/what matters next' synthesis from real data" — sharper diagnostic than the others' generic "premium feel" framings. Pushed back hardest on Gemini's stale FilterBar P0 (Phase 13d already fixed `aria-pressed`) and on Opus's broad header-unification sequencing (correctly identified as too risky for Phase 15). Most disciplined about "patch first, refactor later" sequencing throughout all three rounds.

**Sonnet.** Best at implementation safety, effort estimation, and regression-risk calibration. Uniquely produced the only audit with full effort/regression columns per item, which the synthesis adopts as primary estimates. First-flagged the Decisions 🌱 emoji at `:359` (caught after Opus and Gemini both read the file in detail and missed it). First-named "loading-state inconsistency" as a *systemic* cross-product finding (not just a per-page absence). First-named the GuardrailsToggleButton wiring verification need. Uniquely correctly sized the persistent AI assistant rail as XL (not L per Opus) by walking through the cross-page context assembly + stale-data gating + shell-slot conflict requirements. Uniquely flagged the column-width math defect when changing Decisions `xl:` → `lg:` (the 360/420 fixed columns leave near-zero for col 2 at 1024px with a 220px sidebar — must shrink). Most defensible single-source for Phase 15 effort/regression estimates.

**Opus.** Best at premium-taste judgment, microcopy, and emotional-read framing. First-flagged the two surviving truth violations that conceded universal P0 status (Ops `JobRow last="ok"` and ResearchLab static fallback registry) — both load-bearing for the Phase 15 P0 spine. First-framed the elite-gap as "discipline of singularity" and "premium move is removal not addition." Uniquely produced verbatim OLD/NEW microcopy for five engineering-vocabulary leaks (`PicksPage.tsx:268`, `EventsResearchPage.tsx:33-37`, `OptionsLayout.tsx:42`, `RiskDashboard.tsx:124-132`, `FilterBar.tsx:33-35`) — the synthesis carries these forward verbatim as Phase 15 item #15. Uniquely first-named the MarketTicker-above-fold removal on Overview as the highest-leverage emotional-read change available. Pushed back hardest on Gemini's serif/ambient-motion proposals using file:line and brief-discipline evidence. Provided the only concrete Stripe/Linear/Perplexity/Bloomberg comparison thought-experiment that walked the comparison rather than just gesturing at it. Made the largest number of explicit Round 2 concessions of any panelist (to Sonnet on emoji and loading-state, to Codex on OverviewRouteSwitch, to Gemini on Decisions calm-card weighting), demonstrating the highest peer-update rate in the debate.

---
