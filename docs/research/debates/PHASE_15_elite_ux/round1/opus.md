# Phase 15 — Round 1, Opus (premium taste / emotional trust / hierarchy / microcopy / 10-of-10 feel)

**Posture:** Honest only. No fabricated AI states. No atmospheric visuals that hide information. Light/dark parity, density modes, accessibility, and paper-trading discipline are non-negotiable. I score against the bar of Stripe, Linear, Perplexity Finance, Bloomberg Terminal — products where every pixel earns its place and the *first ten seconds* tell the user where they are, what changed, and what to do next.

I read the brief, the Phase 12 final, then read the actual implementation in `apps/web/src/pages/*.tsx`, the four shell components, the picks/portfolio components, and the two large CSS files. Where I claim something is in the code I cite a line. I do not anchor to Phase 12's scores; I score against an elite bar, not relative improvement.

---

## Per-page audit

### 1. `/overview` — PicksPage.tsx — **6.8 / 10**

**Strengths.** The Phase 14b executive subtitle (`PicksPage.tsx:122-136`) is a real win — `$X NAV · +Y% return · cautious posture` is exactly the one-line answer a Stripe-grade dashboard owes its user, and it's honestly composed (no filler dashes, no synthesized values). The 4-card launcher grid (`PicksPage.tsx:201-241`) gives the page actual gravity instead of the older flat KPI wall. The empty state (`:245-262`) is genuinely composed prose, not a sad icon.

**Biggest weaknesses.**

1. **Three competing heroes stacked vertically.** From the top: `picks-title` "Overview" + 1-line subtitle, then `PageChapter NOW` ("Engine sees 4 buy · 2 sell · …"), then `PortfolioSnapshot` with a 30-44px NAV (`PortfolioSnapshot.tsx:64-75`), then `TodayPanel` with another posture chip and another headline (`TodayPanel.tsx:62-72`). A novice sees four "this is the most important thing on the page" claims in 600 vertical pixels. Stripe and Linear never do this — there is exactly one anchor.
2. **The launcher metric line repeats engine vocabulary** (`PicksPage.tsx:206`: `${buyCount} buy · ${sellCount} sell · ${trimCount} trim · ${watchlistCount} hold`) which is the same number the PageChapter NOW just delivered eight lines earlier (`:161`). Two cards literally show the same fact.
3. **"Today's read" microcopy** (`:191-194`) is *labeled* but the content comes from `briefing.headline` which is a derived sentence — the label "Today's read" sets up an expectation of editorial summary, then delivers the same posture line. Either the label is over-promising or the content is under-delivering.
4. **The "Continue from Overview → Today's recommendations" NextStepCard** (`:264-271`) at the bottom rationale `${riskCount} signal(s) flagged for risk — see what changed in catalysts first` *names a destination different from the one it links to* — it links to Action Queue but tells the user "see catalysts first." Microcopy lies about routing.

**Desktop issues.** PortfolioSnapshot's HERO + 8-12 secondary metrics in `ps-secondary` (`PortfolioSnapshot.tsx:98-160`) is heavy: every metric is the same visual weight, no progressive disclosure. Premium products would group `Total return` + `Open P&L` + `Day P&L` as the trio and tuck `Cash`, `Money invested`, `Realized` behind a quiet "Show details" toggle.

**Mobile issues.** At ≤640 (`picks.css:4262-4344`) launcher grid stacks 1-col cleanly, but the page now becomes: title → subtitle → density toggle → page-chapter (3 sub-cards) → snapshot hero → 8-metric grid (now 2-col) → today-panel (3 stacked sub-panels) → 4 launcher cards → today's-read line → empty/data → next-step → footer. That's **~14 vertical sections before any actionable picks list.** On a Pixel 8 / iPhone 14 that is roughly 4 full screens of preamble. Density toggle is shown at mobile (`:4278`) but is functionally irrelevant on Overview where there's no dense table to compress.

**Novice issues.** The word "posture" is engine vocabulary, not investor vocabulary; "cautious posture" appears in the subtitle, in the AI summary chip, and in the why-no-buys panel on Action Queue. Novice users won't know what "posture" *governs* — does it change sizing? signals? risk? Nothing on the page tells them.

**Expert issues.** Experts see the same NAV three times (TopStrip `:51-60`, Snapshot hero `:64`, no quick way to compare day-pnl against open-pnl). The launcher cards' metric-as-headline is fine for novices but consumes premium real estate without expert depth (no quick numbers, no spark).

**Storyline.** Page tries to say: "Here's where you are, here's the read, here are the four destinations." It actually says: "Here is where you are. Here is where you are. Here is the read on where you are. And here are four places to go also called where you are."

**Recommended structural changes.**
- Demote `picks-title`+subtitle to a minimal crumb when PageChapter is present (Phase 13e gave us PageChapter — let it be the hero on /overview).
- Collapse PortfolioSnapshot's 8-12 metrics into a 3-metric primary tier (NAV / Return / Day) + Expert details for the rest. Use the existing `<ExpertDetails>` (`shell/ExpertDetails.tsx`) — it's already in the codebase.
- Remove the duplicate metric line from launcher card #1; use a richer micro-narrative instead ("3 buys cluster around energy + payments — average confidence 64%").

**Recommended visual changes.**
- Single hero column (left), single chart column (right). Drop the asymmetric centered layout.
- One posture chip on the page, period. The TopStrip can carry it; PageChapter need not repeat it.

**Recommended interaction changes.**
- Launcher cards should preview their target (small inline 3-row sample on hover) instead of showing the same number twice.
- Density toggle should hide when not applicable (Overview has no table).

**Priority.** P1 (high ROI, no data risk). **Complexity.** M. **Regression risk.** Low — purely additive collapse + microcopy.

---

### 2. `/events` — EventsResearchPage.tsx — **5.5 / 10**

**Strengths.** Honest delegation to `MarketEvents` with explicit not-connected / empty / loading branches (`MarketEvents.tsx:53-100`) — that is exemplary truth-telling. The PageChapter NOW string ("X symbols from active recommendations · SEC EDGAR feed live") is honest data lineage (`EventsResearchPage.tsx:33-37`).

**Biggest weaknesses.**
1. **The page is essentially one component.** Header + PageChapter + `<MarketEvents>` + NextStep + footer. There is *no* curation, *no* "what changed since you last looked," *no* ranking by signal-impact. It is a feed dump.
2. **Fetch error is silently swallowed** (`:27`: `.catch(() => { if (!cancelled) setLoading(false); })`). Phase 12 flagged this; it's still there. A backend 500 looks like a clean empty day. This violates the brief's "no fakes by omission."
3. **Density is broken** — `useState<Density>(() => readInitialDensity())` is read but the page contents are not actually density-sensitive; the toggle does nothing visible. Phase 12's call here was correct.
4. **No event-to-signal join.** This is the page that should answer "why did NVDA flip from buy to trim today?" and instead it shows a raw catalyst feed unjoined from the picks list.

**Desktop issues.** Wide screens get 8 symbols' worth of E/N/F/X pills with no grouping, no priority, no time horizon. There is no "earnings this week" filter. Bloomberg/Perplexity Finance both default to a chronological + impact-ranked view.

**Mobile issues.** `me-grid` collapses to single column at ≤640 (`picks.css:4335`) but each symbol's event tile remains tall; 4 active symbols ≈ 1500px. No sticky filter. No date jump.

**Novice issues.** "SEC filings, news momentum, and earnings windows" is fine; the actual content uses raw filing types (8-K, 10-Q) without translation.

**Expert issues.** No filter chips for `8-K only`, `earnings only`, `next 5 sessions`. No CSV export. No subscribe/watch.

**Storyline.** Catalysts that don't tie back to signals are noise. The page claims to be "the why behind signal changes" but does not in-fact join.

**Structural.** Add a "What changed today" rail above the symbol-by-symbol grid: "TSLA flipped buy→hold (8-K filed yesterday)." Auto-derive from picks+events.

**Visual.** Pills must move from opaque codes (E/N/F/X) to plain words; severity should color-code.

**Interaction.** Add a global `from: today / 5d / 30d` chip row.

**Priority.** P0 for the silent fetch error; P1 for the join. **Complexity.** M (join), S (error). **Regression risk.** Low.

---

### 3. `/action-queue` — ActionQueuePage.tsx — **7.4 / 10**

**Strengths.** This is the most product-shaped page. The Phase 14c "Why no buys?" panel (`:146-170`) is *the* single piece of microcopy on this whole product that makes me believe a designer cared. The skeleton loader (`:114-128`) is correct. PageChapter NOW + posture + count is calibrated. Action color rail in `picks.css` and the FilterBar's switch from `role="tab"` to `aria-pressed` (`FilterBar.tsx:39-40`) is real a11y discipline.

**Biggest weaknesses.**
1. **No bulk-affordance.** Operators can click a card to open a modal. They can't multi-select to compare, can't pin, can't star, can't "send to research cockpit." Linear and Stripe both let you act on N items at once.
2. **HealthRail occupies right column** (`:183-188`) but its three numbers (stale / watchlist / risk) repeat what PageChapter NOW already said. Premium products surface NEW information per region; this region is redundant.
3. **No grouping by *thesis*.** Cards group by action (buy/sell/trim/hold). They don't group by underlying thesis (e.g., "rate-cut beneficiaries," "earnings-week trims"). The micro-rationale on the why-no-buys panel proves the data exists; it's just not surfaced in groups.
4. **Filter bar reads as 8 chips** (`FilterBar.tsx:27-36`: all/buy/hold/trim/sell/high-confidence/freshest/highest-risk) — the last three are *quality filters*, not action filters, mixed in the same row. Stripe would split into a primary tab row + a secondary chip row.

**Desktop.** HealthRail's right-column layout creates a 2-col grid below 1280; cards become narrow. Move HealthRail to a thin top-strip slot or merge into PageChapter.

**Mobile.** `picks-filter-bar` overflow-x at ≤480 (`picks.css:4351`) is correct, but the chip set is still 8-wide; users will rarely scroll. Reduce to top 4 + "more."

**Novice.** "high-confidence", "freshest", "highest-risk" filter labels are still engine vocabulary — they should read "≥70% confidence", "<6h old", "risk-flagged."

**Expert.** No keyboard shortcuts (j/k row navigation, c to copy ticker, o to open modal). Linear's keyboard density is the bar.

**Storyline.** Strong on this page — the why-no-buys panel makes the *current decision-state* visible. Keep that pattern; copy it elsewhere.

**Structural.** Promote thesis-grouping; demote HealthRail to a TopStrip-like ribbon.

**Visual.** The action-color rail is too saturated; tint by ~40%, let the content carry the color. Card border-tone is enough.

**Interaction.** Add j/k/o/c keyboard map; add multi-select via shift-click.

**Priority.** P1 (thesis groups); P2 (keyboard, multi-select). **Complexity.** M / L / S. **Regression risk.** Low (additive).

---

### 4. `/signal-lab` — SignalLabPage.tsx — **5.4 / 10**

**Strengths.** Phase 13h's `<ExpertDetails label="How readiness is computed">` (`:133-141`) is exactly the right pattern: the formula is honest, available, but doesn't dominate the hero. The action distribution + freshness buckets are honest derivations.

**Biggest weaknesses.**
1. **The hero number is a composite the user did not ask for.** "Readiness 73 / 100" looks like a credit score; nobody knows whether 73 is good. There is no peer baseline, no historical benchmark, no "this is in the green band." Premium financial products don't ship hero scores without a calibration.
2. **The "Backtest validation" section reads as broken** (`:170-183`). The eyebrow is "Not yet wired" and the body explains what *would* appear here. This is honest, but it is the second-largest visual block on the page. Either (a) hide it, (b) fold it into ExpertDetails, or (c) wire a minimal proxy. It is currently a permanent vacancy sign on the most credibility-sensitive page in the product.
3. **Subtitle "Model quality, signal freshness, and event-feature coverage"** sets up "model quality" but the page does not actually show model-quality numbers — it shows snapshot freshness + coverage. Microcopy over-promises.
4. Density toggle present (`:101`) but page has no density-sensitive content.

**Desktop.** Hero takes up ~280px for one number + small distribution row. Inverted — the distribution + freshness *is* the data; the score is the summary. Re-layout: distribution + freshness as primary, readiness as a sidebar gauge.

**Mobile.** Same problem amplified — readiness + the empty backtest block consume the entire first viewport with no actual signal data.

**Novice.** "Composite formula" inside ExpertDetails is good. But upstream the user doesn't know what `0.5×avg_confidence + 0.3×fresh_ratio×100 + 0.2×event_coverage×100` *means for them*. Translate: "We're confident, signals are fresh, and we have catalyst data on most of them."

**Expert.** No IC decay, no per-feature Sharpe attribution, no out-of-sample / in-sample split, no walk-forward. The page name is "Signal Lab" — experts will leave fast.

**Storyline.** Promises proof; delivers a self-graded report card.

**Structural.** Either ship the backtest data (Phase 16 work) OR rename the page "Signal Snapshot" and shrink the empty state to a one-line "Backtest validation pending — see Ops > ML pipeline."

**Visual.** Replace the bare "73 / 100" with a band gauge showing red / yellow / green bands and a marker; use the same band logic as portfolio risk.

**Interaction.** Allow click-through from each freshness bucket to a filtered Action Queue view ("show me the 4 stale signals").

**Priority.** P1 visually; P0 truthfully (rename or wire). **Complexity.** S (rename) / XL (wire backtest). **Regression risk.** Low.

---

### 5. `/decisions` — Decisions.tsx — **6.0 / 10**

**Strengths.** The "How to read this page" 3-step ordered list (`:106-135`) and `DecisionsCalmCard` (`:1108-1211`) are the most novice-friendly framing on the entire site. Filter labels translated (`:35-41`: "Real / Recovered / Still open / Flagged" instead of engine codes) is a real win. Plain-English humanReasoning and BlockingPanel fallbacks (`:642-678`, `:701-738`) handle the "review notes unavailable" case with grace — that's premium honesty.

**Biggest weaknesses.**
1. **Two visually-incompatible design systems on one page.** The `picks-root picks-root-inline` PageChapter at the top (`:87-89`) sits inside a `max-w-[1680px] mx-auto px-8 py-8` Tailwind shell (`:86`). The fonts, the shadow density, the border tones, and the spacing rhythm all change above and below the chapter. It feels like two products glued at the seam.
2. **3-column grid at `xl` breakpoint** (`:206-207`) means tablet (1024-1280) is fully linear: timeline → detail → outcome stacked. On a 12.9" iPad in portrait this becomes 1500-2000px of vertical scroll for one decision review. The width threshold should be `lg`, not `xl`.
3. **"All decisions {totals.total}" chip + "Still open {totals.open}" chip + "Waiting for tomorrow's market data {totals.pending}" chip** all sit inline (`:151-184`) immediately under the calm card. The calm card already counted these. Three identical numbers in three visually-different containers within 200px.
4. **Engineering-snapshot KVTable** (`:518-525`) with `u-nonprod-ribbon` is the right intent but the orange ribbon is too loud — it competes with the actual decision narrative.

**Desktop.** Right column (Pattern Context) is good but the win-rate bar visualization (`:976-989`) is a flat horizontal bar without context (no "your account average is X" reference line).

**Mobile.** Three-column grid on `xl` only means mobile gets the full vertical: 5+ decision sections, each 200-400px tall. No sticky timeline, no jump-to-section.

**Novice.** The "How to read this page" list is excellent, but the next thing the novice sees is an inline list of chips with engine vocabulary still present in the chip titles ("All decisions", "Still open" — these are clear; "recovered from backup data" needs the calm-card framing inline).

**Expert.** No CSV export, no per-decision permalink, no diff view between decision_version vN and vN+1.

**Storyline.** Strong intent, weak execution. The calm card answers "is this okay?", then the user gets immediately re-buried in chips and three-column engineering.

**Structural.** Migrate to picks-root frame; collapse the chip rail (calm card already carries the totals); change `xl:grid-cols-[…]` to `lg:grid-cols-[…]`.

**Visual.** Tone down `u-nonprod-ribbon` saturation; harmonize the card system to a single primitive.

**Interaction.** Sticky timeline column at lg+; arrow-key navigation between rows; permalink per decision.

**Priority.** P1 (design-system unification + breakpoint shift). **Complexity.** L (DS unify) / S (breakpoint). **Regression risk.** Medium — Decisions has many data-test selectors used by tests.

---

### 6. `/strategies` — StrategiesPage.tsx — **6.4 / 10**

**Strengths.** Phase 14f-E's `<ExpertDetails label="When each strategy fits">` (`:92-101`) is the right move — that education appeared every visit before; now it's one click. The honest NOW string composition (`:52-60`) only renders parts that exist (no filler).

**Biggest weaknesses.**
1. **Three independent components stacked** — `<TradeLifecycle />`, `<PremiumIncome />`, `<StrategyModules />` (`:103-105`) — with no narrative bridge between them. The page's promise ("How a signal becomes a trade") is not delivered: there is no flow diagram, no per-strategy "here is how it's performing on your last 5 signals."
2. **Subtitle "How a signal becomes a trade · paper trading guidance"** is the right thesis but is then betrayed by three components that show outcomes (lifecycle table, premium income table, strategy modules grid) without showing the *bridge from signal to strategy choice*.
3. **No hero metric.** The page has no answer to "is this working?" — premium income MTD lives inside `<PremiumIncome>` but there's no top-line "Strategies generated $X premium this month vs $Y last."

**Desktop.** Wide screens get a 1-col stack of 3 large components; vertical scroll heavy. Wheel/CC/CSP/LEAPS pillars deserve a 4-card hero.

**Mobile.** Good — components are already responsive within picks-root.

**Novice.** Strategy education only fires on click; for a novice landing here for the first time, that's the most important content. Consider auto-open on first visit (localStorage flag), then collapsed thereafter.

**Expert.** No per-strategy edit panel, no risk-budget dial, no "promote candidate strategy to active."

**Storyline.** Promises a process; delivers a portfolio sub-view.

**Structural.** Top hero: 4 strategy pillar cards (Wheel / CC / CSP / LEAPS) with current trade count + MTD premium per pillar. Then lifecycle / premium / modules below.

**Visual.** Tighten the three component spacings; add a subtle separator with strategy name.

**Interaction.** Filter by strategy chip at top of lifecycle.

**Priority.** P1 (hero pillars), P2 (interactions). **Complexity.** M. **Regression risk.** Low.

---

### 7. `/options/*` — OptionsLayout + 12 sub-pages — **5.0 / 10 overall**

**Strengths.** OptionsOverviewPage (`:102-173`) finally gives the section a calm landing instead of dropping into a chain table. The "Where to go next" tab guide (`:144-171`) is honest microcopy. Paper-only banner is properly persistent (`OptionsLayout.tsx:37`).

**Biggest weaknesses.**
1. **12 tabs** (`OptionsLayout.tsx:19-32`). Twelve. There is no premium product on earth — including Bloomberg, including TWS — that exposes 12 tabs at the same level. The taxonomy is broken: Overview / Chain / Features / Trades / Risk / Observatory / Performance / Diagnostics / Replay / Evaluation / Decision-Support / Decision-Framing has *three* "decision" tabs, *two* "diagnostic" tabs, and a "Features" tab nobody outside engineering should ever see. This is the single largest UX-debt item in the app.
2. **Two parallel design systems on every options sub-page.** OptionsLayout uses Tailwind+zinc utility classes (`:40, :48, :54-58`); sub-pages use a mix (e.g., OptionsChainPage `:42-46`: zinc-100/zinc-700/zinc-950, OptionsRiskDashboardPage `:22, :29`: zinc-100/zinc-400). The `--pi-*` token system the rest of the product converged on is *barely* present here. Phase 13j tokenized TopStrip; Options is the largest unfixed surface.
3. **"Pro view · Options chain" eyebrows** repeated on every sub-page (UX-1 Commit O — `OptionsChainPage.tsx:37-46`, `OptionsRiskDashboardPage.tsx:18-30`, `OptionsPaperTradesPage.tsx:51-60`) read as defensive labeling rather than navigation. Premium products don't tell users "this is advanced" — they reveal complexity progressively.
4. **GuardrailsToggleButton** (`OptionsLayout.tsx:44-46`) is a UI-only toggle that flips a chip but is not wired to any actual data filter — that is a fakes-by-omission risk *if* the user assumes it changes scoring. Verify or remove.
5. **No light-mode parity.** zinc-700/zinc-950 hard-codes break in light mode entirely.

**Desktop.** Tab nav wraps to two rows on most laptops (~1280); already broken hierarchy.

**Mobile.** 12 tabs in a `flex-wrap` (`:48`) with no overflow-x, no priority+more — at 375px it becomes 4-5 rows of tab chips. Phase 14f did not touch this.

**Novice.** "Most beginners never need this" is repeated 5 times across sub-pages. If that's true, hide them from the top nav; create an "Advanced" section.

**Expert.** Real expert needs: per-strategy P&L, IV rank by symbol, quick chain pull. The 12-tab spread *fragments* expert workflow rather than streamlining it.

**Storyline.** Broken — there is no path. The Overview tab guide is a workaround, not a fix.

**Structural.** Collapse 12 → 4 tabs:
- **Overview** (current OptionsOverview)
- **Trades & Risk** (Paper Trades + Risk Dashboard merged)
- **Strategy Lab** (Observatory + Performance + Evaluation merged)
- **Engineering** (Chain + Features + Diagnostics + Replay + Decision-Support + Decision-Framing as a sub-nav inside)

**Visual.** Migrate to `--pi-*` tokens; drop all `zinc-*` Tailwind in this section; thread PageChapter + NextStepCard.

**Interaction.** Single search field at the top: symbol + strategy + status; deep links per tab.

**Priority.** P0 for nav collapse + tokenization. **Complexity.** XL. **Regression risk.** Medium-high — many sub-routes, many tests.

---

### 8. `/portfolio` — PortfolioRouteSwitch → PortfolioTerminal (default) / CopilotHoldings (?view=brief) — **6.2 / 10**

**Strengths.** The route switch (`PortfolioRouteSwitch.tsx:17-23`) lets brief↔working coexist without breaking links. PortfolioTerminal honestly handles `mark_unavailable` (`PortfolioTerminal.tsx:74-77`) — never substitutes a fake zero. CopilotHoldings (`CopilotHoldings.tsx:55-80`) keeps the brief view at 1100px max width — calm and prose-forward.

**Biggest weaknesses.**
1. **Two completely different products under the same URL.** The brief view is ~1100px, prose-styled, copilot tokens (`--copilot-type-24`, `--copilot-type-15`); the working view is 1440px max, dense KPI cards, `u-mono` numbers, Tailwind utilities. Different fonts, different rhythms, different vocabulary. Switching `?view=brief` ↔ `?view=working` feels like switching products.
2. **The default is `working`** (`PortfolioRouteSwitch.tsx:22`) — meaning the Strategic-lock D "preserve legacy" decision is currently exposed to every default visitor. The brief view is hidden behind a query string most users will never type.
3. **PortfolioTerminal's PageGuide** (`:104-119`) uses `<PageGuide>` from `@/components/novice` — *not* PageChapter. This is the visible design-system fork. The two pages most users land on (Overview + Portfolio) don't share a header pattern.
4. **Snapshot-NAV vs PageChapter-NOW competition** persists from Phase 12 — the TopStrip carries NAV, and Portfolio's own header carries NAV again. Three NAV displays in the upper viewport.

**Desktop.** Working view is dense and capable; brief view is calm and storytelling. Both have merit, but the default needs to commit.

**Mobile.** Working view is heavy on tables (TradeLifecycle, executed positions, equity curve chart) — needs `u-table-wrap` discipline. Brief view is mobile-friendly by construction.

**Novice.** "My Holdings" eyebrow + "Top row shows your account at a glance" (`:107-118`) is excellent — but it appears only on the working view, where the dense numbers immediately undercut the calm framing.

**Expert.** Working view is what experts want. Brief view is too calm — no quick filter, no sort, no compare.

**Storyline.** The split URL is a Strategic Lock, not a UX bug — but the *default* selection should reflect "premium product" intent: brief by default, working on toggle.

**Structural.** Make brief the default (Phase F per the inline doc); add a persistent toggle in the page header so working-view users can pin their preference; unify headers via PageChapter.

**Visual.** Bridge the two visual systems: at minimum share fonts, spacing rhythm, color tokens.

**Interaction.** Sticky toggle; deep-link to position from brief view.

**Priority.** P1 (default flip + header unify). **Complexity.** M. **Regression risk.** Medium — PortfolioTerminal has many tests.

---

### 9. `/risk` — RiskDashboard.tsx — **6.0 / 10**

**Strengths.** Honest "mark unavailable" handling everywhere (`:184-194`, table rendering `:512-516`). PageGuide + Start-here focus card (`:52-101`) is the most caring novice scaffolding on the site. `u-table-wrap` discipline (`:489, :545, :583`) — Phase 13's table-overflow fix landed cleanly.

**Biggest weaknesses.**
1. **Header stack is overweight.** `picks-root picks-root-inline` PageChapter (`:45-47`) → `<PageGuide>` (`:52-67`) → "Focus today" `u-card-tight` (`:70-101`) → `<AdvancedDetails>` (`:107-114`) → controls row (`:115-133`). That's **5 framing layers** before the user sees a single risk number. A premium product would compose these into one header band.
2. **Two scaffold systems** — PageChapter (new) + PageGuide+AdvancedDetails (UX-1 era). Both exist; both repeat purpose copy; the user reads "this is the risk view" three times.
3. **"Generate explanation" button** (`:124-132`) is a 11px text button on a quiet border — it looks like a debug control. The narrative drawer is one of the most premium features on the site (LLM-derived risk commentary on demand). Make it a primary action with a clear "AI explanation →" affordance.
4. **`includeReplay` checkbox** (`:117-122`) sits on the right side, away from the table it affects. Should be a control of the table, not the page.

**Desktop.** Tables are well-wrapped; PortfolioSnapshotTable is wide but `u-table-wrap` saves it. Insight drawer on the right is good.

**Mobile.** All tables horizontal-scroll. Headers acceptable. Generate-explanation button is small (≤32px tap target risk on the 11px text).

**Novice.** "Account value, Percent invested, Biggest drop from peak" (`:80-94`) is exactly right. But these phrases appear in the focus card, not as labels on the actual cards below — the *connection* breaks.

**Expert.** No VaR, no historical drawdown chart in-line, no per-strategy risk decomposition, no scenario selector.

**Storyline.** "Is this safe?" answered well; "what should I change?" not answered at all.

**Structural.** Merge PageChapter + PageGuide + Focus card into one composed `RiskHeader` component. Promote "Generate explanation" to the header CTA.

**Visual.** Tone down the warning ribbons; the page already feels nervous.

**Interaction.** Checkbox → table-level toggle. Add scenario selector ("if VIX +50%").

**Priority.** P1 (header consolidation), P0 for design-system bridge. **Complexity.** M. **Regression risk.** Medium — multi-test selectors.

---

### 10. `/research` — ResearchLab.tsx (Alpha Lab) — **5.2 / 10**

**Strengths.** Honest "experimental" chip + Lab-mode visual treatment (`:34-48`). PageChapter threading via `picks-root-inline` (`:31-33`).

**Biggest weaknesses.**
1. **Static fallback registry rows** (`:85-126`) render as if live data — Phase 12 flagged this; the fallback still renders the four "Phase X FAIL" rows when `shadow.length === 0` (`:128`). The `value_display` says "Phase X FAIL" which sounds honest, but the *containers* (Card, Pill, "shadow signal registry") look identical to the live state. A user cannot tell from layout whether they are looking at fresh model output or a hard-coded baseline.
2. **4-tab nav (Signals / Top Wins / Top Losses / Patterns)** uses inline Tailwind border-b utilities (`:50-62`), not the same tokenized tab system as Options. Third nav style in the codebase.
3. **"Alpha Lab" name + "Research" eyebrow + "experimental" chip** are three labels for the same idea, all in the upper 100px.
4. **No cross-link from picks** — when a signal is shadow-flagged on Action Queue, there is no "see in Alpha Lab" link.

**Desktop.** Tab nav is acceptable; signals card is fine.

**Mobile.** Tab nav becomes flex-wrap; with 4 tabs at 375px it's tight but okay. No sticky.

**Novice.** "Observatory for candidate signals, winning/losing pattern mining" is engineer language. Translate.

**Expert.** Experts will want a per-signal sparkline, a download, an OOS validation flag, a date the experiment started. Currently get: status pill + value display + notes string.

**Storyline.** "Where ideas live before they're real" is a great promise; the current page reads like a worksheet.

**Structural.** Either (a) label the static fallback explicitly as "Static registry baseline — no live shadow signals this cycle" inside the registry card, or (b) hide the fallback when there's nothing live and show an empty state. The current dual-meaning rendering is a quiet trust violation.

**Visual.** Migrate to picks-root frame; drop the third-tab-style.

**Interaction.** Add per-signal detail page with permalink.

**Priority.** P0 (label the fallback truthfully), P1 (frame migration). **Complexity.** S / M. **Regression risk.** Low.

---

### 11. `/ops` — Ops.tsx — **5.5 / 10**

**Strengths.** Calm-card framing (`:105-128`) is well-executed for what is fundamentally an engineering dashboard. Section anchors (`:143, :206, :244`) give long-page navigation. PageChapter threaded (`:47-49`).

**Biggest weaknesses.**
1. **Hard-coded JobRow statuses** (`:262-267`): `<JobRow name="daily_paper_pipeline" cadence="…" last="ok" />` and three others — these are not derived from real job logs. A real failure of `daily_paper_pipeline` will *still render "ok"* on this page. This is a fakes-by-omission violation and Phase 12's Tier-1 item #2 — and it has not been fixed. **This is a P0 honesty issue.**
2. **Three card-style systems on one page**: legacy `Card`/`SectionHeader`/`Pill` from `@/components/ui/primitives` (`:151-203`), a sea of opaque `<MLResearchCard />`-style imports (`:148, :211-256`), the new picks-root PageChapter at the top, and the Tailwind divide-y job rows (`:262-267`). Four visual systems on one page.
3. **15+ specialized cards** (`:148`, `:211-217`, `:220-256`) each with their own internal layout. The page is a Frankenstein of every operational concern.
4. **OpsAnchorNav** (`:140`, defined `:288-…`) is sticky but uses `top-[var(--ops-nav-top, 100px)]` — interacts with TopStrip+Ticker+StatusRail's own sticky stack.

**Desktop.** Vertical scroll is heroic — easily 6000-8000px.

**Mobile.** Catastrophic — every "card" assumes desktop width. No mobile testing visible.

**Novice.** Calm card answers "is anything wrong?" well; but if `last="ok"` is *literally hardcoded*, the calm card becomes a lie when something breaks.

**Expert.** This is the ops engineer's page; they need real status. Hardcoded is worse than missing.

**Storyline.** "Is the engine alive?" — answered honestly via SystemHealthCard, lied to via JobRow.

**Structural.** Replace JobRow hardcodes with real `useScheduledJobs()` hook (or label as "TODO — wire to scheduler" inside an `ExpertDetails`). Group 15 cards into 3-4 collapsible super-sections (Phase 12 Tier-6 item #21 — still unshipped).

**Visual.** Single card system; tokenize.

**Interaction.** Per-section "show me failures only" filter.

**Priority.** **P0 for the JobRow honesty fix.** P1 for super-section collapse. **Complexity.** S (JobRow), L (collapse). **Regression risk.** Low (JobRow), medium (collapse).

---

## A. Cross-product findings

### Design-system inconsistencies

**Three coexisting frame systems:**
1. `picks-root` / `picks-frame` / `--pi-*` tokens — Overview, Action Queue, Events, Signal Lab, Strategies (the "Phase 8+ canon")
2. `max-w-[…] mx-auto px-X py-Y` Tailwind shells — Decisions, RiskDashboard, ResearchLab, Ops, PortfolioTerminal
3. Tailwind `zinc-*` hard-codes — Options sub-pages

The `picks-root picks-root-inline` bridge (used in Decisions `:87`, RiskDashboard `:45`, ResearchLab `:31`, Ops `:47`) lets PageChapter render in legacy pages, but the *body* of each legacy page is still its own design world. The "I just left the product" feeling Phase 12 named is real and persistent.

### Header / hero pattern inconsistencies

- PicksPage / Action Queue / Events / Signal Lab / Strategies use `<header className="picks-header">` with `picks-title` + `picks-subtitle` + DensityToggle.
- Decisions / Risk / Portfolio use `<PageGuide>` with eyebrow + title + subtitle + firstLook.
- Options sub-pages use `<header data-test="options-X-intro">` with `u-caption-2 text-fg-3 uppercase` eyebrows + `text-base font-semibold text-zinc-100` titles.
- ResearchLab uses inline `<Label>` + `u-title-lg` + chip.

**Four header patterns.** Premium products have one.

### Typography inconsistencies

- `--fs-hero: 28px / --fs-title: 22px / --fs-body: 14px` defined at `index.css:101-106`.
- `picks-title` uses `clamp()` between 22-44px depending on density (`picks.css:3250, 3322`).
- CopilotHoldings uses `--copilot-type-24` and `--copilot-type-15` (separate token namespace at `lib/copilot/tokens.css`).
- Options uses raw `text-xl`, `text-base`, `text-sm`, `text-xs` Tailwind classes.

There are at least **three independent type scales** rendered side-by-side. A user navigating Overview → Portfolio → Options sees three different body sizes for the "same" body text.

### Density inconsistencies

DensityToggle is rendered on Overview, Action Queue, Events, Signal Lab, Strategies — but only Overview's PortfolioSnapshot and Action Queue's pick-box meaningfully respond to it. Events / Signal Lab / Strategies expose a control that does almost nothing visible. Phase 12 said this; it's still there.

### Interaction inconsistencies

- Action Queue uses `aria-pressed` on filter buttons (`FilterBar.tsx:50`).
- Decisions filter buttons use raw `onClick` with custom border-color inline styles (`Decisions.tsx:219-231`).
- Options tab nav uses NavLink with isActive-derived className.
- ResearchLab tab nav uses raw button + state.

Four chip/tab interaction patterns.

### Color inconsistencies

- picks-* uses its own action palette (`picks.css:14-48`) — emerald 400 / red 400 / orange 400 / amber 400.
- The general design system uses `--accent: #4B8BFF / --success: #26CA72 / --warning: #F8A638 / --danger: #F25053` (`index.css:65-72`).
- CopilotHoldings reads `--copilot-*` tokens.
- Options uses raw zinc-*.

A single buy signal can render in *three different greens* depending on which surface it appears in.

---

## B. Elite-gap analysis — what would Stripe / Linear / Perplexity do that this does not?

This product has shipped many of the right *patterns* (PageChapter, NextStepCard, ExpertDetails, calm cards, honest empty states). What it has not yet shipped is **discipline of singularity** — the elite premium product law that *each piece of information appears exactly once, in exactly one visual treatment, in exactly the place it belongs.*

The specific elite gaps:

**1. Singular hero per page.** Stripe's dashboard has *one* number above the fold: today's volume. Linear has *one*: the inbox count. Perplexity has *one*: the answer. This product currently has 3-4 competing heroes on every primary page (TopStrip NAV, PageChapter NOW, PortfolioSnapshot NAV, TodayPanel headline). The hierarchy is "everything is important," which means nothing is.

**2. One typeface, one scale.** Linear's entire app uses Inter at 5 sizes. This product uses Inter (`--font-ui`), JetBrains Mono (`--font-mono`), and a third copilot scale (`--copilot-type-*`) all rendered side-by-side. Premium feel requires committing to one scale.

**3. The "what changed" instinct.** Linear shows a tiny "12 new since you last looked" pill on every list. Stripe shows "+$12,400 today vs $11,200 yesterday." This product shows only absolute snapshots — there is no temporal context anywhere except the equity sparkline. No "3 picks new since this morning," no "1 strategy changed status overnight."

**4. Honest progressive disclosure.** Premium products give you *more* signal as you click in, never *more chrome*. This product currently disclosees engineering chrome at every level (decision_version, paper_size_multiplier, gate_mode, alpha_rule_snapshot…) — the `<ExpertDetails>` and humanizeKey() helpers are excellent infrastructure but only sparsely applied (Decisions/Signal Lab). Options exposes raw fields everywhere.

**5. Microcopy as product.** Stripe's empty states *teach you the next thing*. Linear's keyboard hints appear contextually. This product has shipped **one** great microcopy moment — the "Why no buys?" panel on Action Queue — and it shows what the rest of the surface could be. Every other page has copy that *describes the page* rather than *advancing the user's decision*.

**6. Trust through restraint.** Bloomberg-grade trust comes from *never* showing a number you cannot defend. The hardcoded JobRow `last="ok"` (`Ops.tsx:263-266`) and the static fallback registry (`ResearchLab.tsx:85-126`) are the two surviving fakes-by-omission spots in the product. Both are P0.

**7. Animation discipline.** Premium products have one motion vocabulary (Linear: 200ms ease-out for everything). This product has Phase 13g press-scale, ticker animation, fresh-pulse on PickBox, no others. That's actually close to right — but the tokens for motion don't exist; future motion adds will diverge.

**8. A single navigation philosophy.** The SideNav uses FLOW + SECTIONS metadata with `next` indication (`SideNav.tsx:65-79`) — that is genuinely elite design. But within pages, the nav idiom changes (Decisions has filter chips at top, Options has 12 tabs, Alpha Lab has 4 tabs, RiskDashboard has no in-page nav). The shell is excellent; the page-level nav is fragmented.

**9. The "AI-native" missing piece.** The product is called AI Investing OS but the AI presence is mostly invisible. The "Generate explanation" button on RiskDashboard is one moment. There is no:
- Persistent AI assistant rail (Linear's command palette equivalent for AI questions)
- Inline "explain this number" hover anywhere
- AI-derived next-action chip on each page beyond static NextStepCard rationale

A Perplexity-grade experience would have a quiet, always-available "ask about this view" affordance that respects honest-data discipline (refuses to answer when data is stale).

**10. Mobile not as port, as product.** The mobile work in Phase 14f is good (drawer, ticker compress, sticky relax, 44px tap targets) but treats mobile as "make the desktop fit." A Robinhood-grade mobile product would have a *different* IA on mobile: top widget = posture + 1 actionable signal, swipe down = today's read, swipe right = next chapter. The current mobile is desktop-light, not mobile-native.

---

## C. Final ranked roadmap — Phase 15 / 16 / 17

Ranking criteria (per brief): UX impact > novice clarity > mobile quality > trustworthiness > implementation safety.

### Phase 15 — Truth + Hierarchy (ship within 2 weeks)

**P0 (truth-first; non-negotiable):**
1. **Replace hardcoded JobRow statuses** in `Ops.tsx:262-267` with real scheduler hook OR label as "(static placeholder — see Ops backlog)" inside `<ExpertDetails>`. Trust violation. **S, low risk.**
2. **Label or hide** the static fallback in `ResearchLab.tsx:85-126`. Add a pill "Static registry baseline — no live shadow signals this cycle" when fallback fires. **S, low risk.**
3. **Restore visible fetch error** on `EventsResearchPage.tsx:27` — the `.catch(() => setLoading(false))` swallow remains. Use the existing `<FetchError>` pattern from Action Queue. **S, low risk.**
4. **Verify `GuardrailsToggleButton`** in OptionsLayout actually changes data, or remove. **S, low risk.**

**P1 (hierarchy + microcopy):**
5. **Demote PortfolioSnapshot to 3 primary metrics + ExpertDetails for the rest.** `PicksPage.tsx` Overview becomes scannable in one breath. **M, low risk.**
6. **Single page header pattern.** Pick PageChapter (it's the most modern + honest); migrate PageGuide-using pages (Risk, Decisions, Portfolio, Ops) to use PageChapter as the canonical header. Keep `firstLook` as an optional PageChapter prop. **L, medium risk** (test selectors).
7. **Demote density toggle** to surfaces where it does work (Action Queue, Portfolio Terminal). Hide on Overview / Events / Signal Lab / Strategies. **S, low risk.**
8. **Microcopy translation pass — round 2.** Translate "high-confidence", "freshest", "highest-risk" filter labels in `FilterBar.tsx:33-35` to "≥70% confidence", "<6h old", "Risk-flagged." Translate "posture" → "stance" or define on first use. **S, low risk.**

### Phase 16 — Singularity + Options collapse (3-4 weeks)

9. **Options nav collapse** from 12 → 4 tabs (Overview / Trades & Risk / Strategy Lab / Engineering). Tokenize all `zinc-*` to `--pi-*`. Single largest UX-debt item. **XL, medium-high risk.**
10. **Decisions design-system unification** — migrate to picks-root frame; change `xl:` breakpoint to `lg:`; thread the calm card into PageChapter. **L, medium risk.**
11. **Portfolio default flip to brief view** (Strategic Lock D allows this if `?view=working` toggle becomes prominent). Add persistent toggle in header. **M, medium risk.**
12. **Action Queue thesis-grouping.** Group cards by dominant `pickTags` cluster, not just by action. **M, low risk.**
13. **"What changed" temporal context.** Add tiny pills to lists: "3 new since 9 AM," "1 flipped buy→hold." Honest derivation from existing data. **M, low risk.**

### Phase 17 — AI-native moments + mobile-native (4-6 weeks)

14. **Persistent AI assistant rail.** Quiet button, opens drawer, scoped to current page's data. Refuses to answer when data is stale. Uses existing InsightDrawer pattern. **L.**
15. **Inline "explain this number" hover** on any number with a derivable computation (readiness composite, risk drawdown, exposure pct). **L.**
16. **Mobile-native re-IA**: separate Top mobile widget composition (not just responsive desktop). Posture + 1 actionable signal + horizontal swipe between Today / Working / Risk. **XL.**
17. **Single motion vocabulary.** Define motion tokens (`--motion-fast: 120ms`, `--motion-base: 200ms`, ease-out). Migrate ticker, press-scale, fresh-pulse. **M.**
18. **Animation: single-source NAV.** TopStrip becomes the only place NAV ever appears at full size; PortfolioSnapshot, PortfolioTerminal headers reduce to delta-only. **M.**

---

## Answers to the 12 specific brief questions

1. **Is the app telling a coherent story page-to-page?** *Mostly, since Phase 13e PageChapter threading.* The FLOW chain works as a backbone, but the visual grammar shifts between sections so the *feeling* is fragmented even when the *information* is coherent.

2. **Does navigation feel linear/intelligent or fragmented?** SideNav itself is intelligent (next-step indicator, FLOW metadata — `SideNav.tsx:65-79`). In-page navigation is fragmented (4 different tab/chip systems).

3. **Are users guided naturally Overview → Catalysts → Decisions → Execution → Portfolio → Risk?** The PageChapter+NextStepCard pair makes this *possible*. It's not yet *natural* because the next-step rationale sometimes contradicts the destination ("see catalysts first" links to Action Queue — `PicksPage.tsx:264-271`).

4. **Which pages feel "dead" or passive?** Events (single component delegation, no curation); Signal Lab's lower half ("Backtest validation — Not yet wired" — `SignalLabPage.tsx:170-183`); Alpha Lab (worksheet feel).

5. **Which sections should become collapsible?** Strategies education (already done in 14f-E ✓); Options "Where to go next" tab guide (long list); RiskDashboard "Focus today" + "Where this data comes from" (consolidate into one collapsible); Ops 15 cards into 3-4 super-sections; Decisions "How to read this page" (collapse after first visit via localStorage).

6. **Which sections should become sticky?** Decisions Timeline column at lg+ (currently scrolls with body); FilterBar on Action Queue; OpsAnchorNav (already sticky but conflicts with TopStrip stack — needs stack-coordination).

7. **Which cards are visually noisy?** PortfolioSnapshot's 8-12 metric grid; the `u-nonprod-ribbon` orange wash on Decisions diagnostic snapshot; the Why-no-buys panel border tone is fine; Options Risk summary cards (4 KPI cards with no hierarchy).

8. **Which cards are under-emphasized?** "Generate explanation" button on RiskDashboard (`:124-132`) — buried 11px text; the brief↔working toggle on Portfolio (URL-only); the "next-step" indicator on SideNav (very subtle 9px chip — `SideNav.tsx:69-72`).

9. **Which sections waste vertical space?** PortfolioSnapshot loading skeleton; PicksPage launcher cards' duplicated metric line; Signal Lab "Backtest validation — Not yet wired" empty section; Decisions calm-card + chip rail + AdvancedDetails stack (4 layers of "what is this page").

10. **Which sections are too dense?** Options Chain table; PortfolioTerminal executed positions table on mobile; Decisions 3-column grid below xl; Ops middle band (15 stacked cards with no grouping).

11. **Which pages fail on mobile ergonomics?** Options (12-tab nav wraps to 4 rows at 375px, no priority+more); Decisions (no sticky timeline, 1500-2000px decision review); Ops (no mobile work visible — every card is desktop-shaped); RiskDashboard (5 framing layers before any number, all stacked vertically on mobile).

12. **Which pages still feel "developer-built" instead of "premium product"?** Ops (clearly), Options (12 tabs, zinc hard-codes, defensive labeling), Alpha Lab (worksheet aesthetic, raw chip), Signal Lab (composite-score-as-hero), RiskDashboard middle band (controls row + warning ribbons + KVTable density).

---

## Final personal verdict (premium-taste lens)

The product has the bones of a 9/10 product and the surface of a 6/10 product. The hardest, most-architectural work has been done — there is a real FLOW chain, a real PageChapter pattern, a real ExpertDetails primitive, a real `useFetchWithError` discipline (mostly applied), a real `useExecutedPositions` honesty backbone, real action-color semantics, real density tokens.

What remains is **discipline of singularity** — and **truth-debt clearance** at two specific spots (Ops JobRow, ResearchLab fallback). If Phase 15 ships the four P0 truth fixes + the header-pattern unification + the density-toggle hide, the product will be a 7.5-8.0 average overall. If Phase 16 collapses Options + flips Portfolio default + ships thesis-grouping + temporal "what changed" pills, it will sit at 8.5. The 9.5/10 aspiration requires Phase 17's AI-native moments and mobile-native re-IA — but those are unlocks, not rescues. The product no longer needs rescuing; it needs *committing to one voice*.

DONE: docs/research/debates/PHASE_15_elite_ux/round1/opus.md (3,950 words written)
