# Phase 15 — Round 2, Opus (premium taste / hierarchy / microcopy / 10-of-10 feel)

**Posture for Round 2:** Read all three of Gemini, Codex, Sonnet at length. Where they're right, I'll concede crisply. Where they prescribed a "fix" that creates inelegance, hierarchy collision, or motif drift, I'll push back with file:line evidence and propose the more elegant alternative. My lens stays narrow: what does this *feel like* in the first ten seconds, and would Stripe / Linear / Perplexity / Bloomberg actually ship it.

---

## 1. Convergence — what all 4 of us agreed on

Across four independent reads, these are the unanimous findings. They are now load-bearing for Phase 15 planning:

1. **Options is the single largest UX-debt surface.** All four of us scored it 4.5–5.9/10 and all four called the 12-tab `flex-wrap` nav (`OptionsLayout.tsx:48-64`) the headline failure. All four called for collapse to ~4 grouped sections. This is no longer debate — it is decided.
2. **The Portfolio default should flip to brief view.** All four landed on this. The `?view=working` default at `PortfolioRouteSwitch.tsx:22` is now historical residue.
3. **PageChapter / NextStepCard are the right narrative spine.** Codex, Sonnet, Gemini, and I all praise the threading. The disagreement is *only* about completeness: NextStepCard is missing on Portfolio, Risk (it has PageChapter NEXT but no card), Alpha Lab, Ops.
4. **"Why no buys?" is the single best microcopy moment in the product.** Universal recognition. The pattern needs to be replicated on Strategies (when no active strategies fit), Signal Lab (when readiness < band), Risk (when nothing flagged), and Options Overview.
5. **Density toggle is over-deployed.** It appears on pages where it does nothing visible (Events, Signal Lab, Strategies, Overview when no table is present). Codex, Sonnet and I all flagged this. Hide where inert.
6. **Multiple coexisting design systems is the real coherence problem.** Codex names "mixed product eras"; Sonnet names "three layout systems"; Gemini names "Three Navs"; I named "discipline of singularity." Same finding, four framings.
7. **Mobile is responsive but not native.** All four agreed the shell work in 14f is solid, but page interiors (NAV strips, multi-column grids, Options tabs, Decisions 3-col) remain desktop ports.

These seven items should be the spine of the Round 3 synthesis. Anything not in this list is contested.

---

## 2. Divergence — where I take a position against another panelist

### 2.1 The "AI Presence" / Serif font question — I disagree with Gemini

Gemini (round1/gemini.md §3, item 2 + Phase 16 item 1) proposes introducing **Source Serif 4** for AI-narrative blocks (PageChapter, Calm Cards, Copilot stories), and adding "subtle motion in TopStrip when the engine is thinking" as ambient AI signal.

**I push back on both, hard.**

A second typeface for "AI moments" is exactly the kind of move that *looks* premium in a Figma frame and *feels* gimmicky in a shipped product. Linear ships everything in Inter. Stripe ships everything in their own grotesque. Perplexity ships everything in a single sans + a single serif for *quoted source content*, not for AI-generated content. Adding a serif to flag "this paragraph is from the model" trains the user that AI-text is visually different from human-text — which is the wrong direction for an AI-native OS where the model *is* the product. The serif also collides with the existing `--copilot-type-*` tokens (`CopilotHoldings.tsx`) which are already a third typographic system; layering serif on top of that doubles the typographic debt that Codex and I both already named.

The "ambient TopStrip motion when engine is thinking" suggestion is worse. It is precisely the "atmospheric visual that reduces information clarity" the brief explicitly forbids. It also lies — the engine is *not* thinking continuously; it ticks on a scheduler. Pulsing animation would imply continuous activity that doesn't exist. Bloomberg never animates without a state change. Linear's only ambient motion is the cursor in the command palette. **Reject.**

The premium move instead: **one motion vocabulary, applied only on real state change.** A 200ms ease-out tint on TopStrip when `last_pipeline_at` changes (i.e., when fresh data actually arrived). A `nowrap-counter` numeric tween on NAV when the value moves. *That* is AI presence — making the *truth* visible the moment it changes, not faking liveness.

### 2.2 Reordering launcher cards to match `page_flow.ts` — I disagree with Sonnet

Sonnet (round1/sonnet.md, §1a, P1 recommendation #8) wants the launcher cards reordered from action-queue → events → strategies → portfolio (as currently shipped at `PicksPage.tsx:201-241`) to overview → events → action-queue → strategies (page_flow.ts order).

**I push back.** The current order is *correct* and the comment at `PicksPage.tsx:198-200` documents the intent: "an executive's reading flow: signals → catalysts → strategies → risk." This is the right premium-product hierarchy — a person opening their day wants to see *what to do* first (signals), then *why* (catalysts), then *how* (strategies), then *what's at stake* (portfolio/risk). page_flow.ts is the FLOW for sequential drill-down on a single thesis — it's the keyboard / SideNav metaphor. The launcher grid is the *desk* metaphor: four piles arranged by cognitive priority, not by sequential workflow.

Reordering them would put Events first, which is a Bloomberg-Terminal pattern (catalysts-first), not a Stripe-pattern (action-first). For an *AI-native* product where the AI has already done the catalyst-to-signal join, the action surface is the right primary. **Keep current order. Add a "1, 2, 3, 4" reading-order tick on the cards if discoverability is the worry, but do not reorder.**

### 2.3 Master-detail navigation on Decisions mobile — I half-disagree with Gemini

Gemini (§1.5) proposes converting the Decisions 3-column to "a 'Master-Detail' view on mobile where clicking a timeline entry navigates to a sub-route."

**I push back on the sub-route part.** Sub-routing per decision is a navigation cliff — back-button behavior breaks, deep-links proliferate, and the "I clicked a row to see its detail" gesture acquires a URL change that wasn't there before. Linear handles this with an in-page expanding row (the "Issue detail panel" in mobile is an in-page sheet, not a route). The premium move is **bottom sheet on tap**, not sub-route — a `details` panel that slides up from the bottom on mobile, dismissed by swipe or back-button, no URL change. Sonnet's "scroll-into-view on selection" (§5, item 3) is even simpler and probably correct for a first ship, then bottom-sheet later.

### 2.4 "Hidden 'developer-built' badge" / collapsed-by-default novice content — I disagree with Sonnet

Sonnet (§5) proposes the Decisions "Start here" card "already collapsible would be better than always-visible." Codex (§5) proposes broadly expanding ExpertDetails across diagnostics.

**I push back partially.** Collapsing the novice-help card after the user scrolls past it once (via localStorage flag) is exactly right — premium products like Notion's onboarding cards do this. But always-collapsed-by-default removes the very thing that makes Decisions and Risk feel premium-novice today: the calm-card framing *appearing* on first visit. The pattern that ships well is `dismissible: true, default: open, persistent-after-dismiss: true` — same as Stripe Connect's onboarding hint cards. **Concede the localStorage flag idea; reject "collapsed by default" without dismissal.**

---

## 3. Where I was wrong in Round 1 — explicit concessions

### 3.1 To Sonnet — I missed the Decisions emoji

Sonnet (§5, P0 item) caught `🌱` in `Decisions.tsx:359` (`EmptyFilter` function). I read the Decisions file in detail in Round 1 and missed this. It violates the no-emoji discipline in user-global instructions. **P0 fix, S complexity.** I should have caught it; Sonnet did. Concession.

### 3.2 To Sonnet — I underweighted the loading-state inconsistency

Sonnet (§A.3) named "Loading state inconsistency" as a cross-product finding: ActionQueue has skeleton, SignalLab shows "Loading…" text, Overview.tsx shows nothing, Events has no indicator. I called out the absence on Events but did not connect it to a *systemic* loading-pattern debt. Sonnet's framing is more useful for roadmap prioritization. **Concession: this belongs in Phase 15, not 17.**

### 3.3 To Codex — I underweighted the OverviewRouteSwitch query-param sprawl

Codex (§1, weakness #1) flagged that `OverviewRouteSwitch.tsx:35-46` preserves working / stream / conviction / copilot / living / legacy / default views — 7 query-param variants for a single route. I noted the brief↔working duality on Portfolio but did not surface the same pattern on Overview. Codex is right that this is a "product confidence" leak — it tells the user "we couldn't decide what Overview is." **Concession.** The fix is to move experimental variants behind a hidden internal flag, not into the user-discoverable URL space.

### 3.4 To Gemini — I was too generous on Decisions (7.0 → 6.0 in my round)

Gemini scored Decisions 7.5/10, citing the calm card. I scored 6.0, citing the design-system collision. Re-reading both, Gemini is right about the **functional** quality (the calm card is genuinely the best AI-moderator pattern in the product — Decisions.tsx:1108-1211). My downgrade was justified on visual coherence but harsh on what Decisions actually delivers cognitively. **Re-score below to 6.5.**

---

## 4. Where I push back with file:line evidence

### 4.1 Codex's "PortfolioTerminal NextStepCard missing" — partially refuted

Codex (§8) claims PortfolioTerminal "does not use PageChapter/NextStepCard." This is true for `PortfolioTerminal.tsx`, but the routing layer matters: `/portfolio` defaults to PortfolioTerminal which lacks both, **but** the brief view at `?view=brief` (CopilotHoldings) also lacks both — Codex correctly flags this for terminal but doesn't note that the brief view has the same gap. The fix isn't just "add to terminal"; it's "the route owner should add a single PageChapter at the route level so both views inherit it." That's a different (and cleaner) fix than what Codex proposed.

### 4.2 Sonnet's "Decisions Col 2 narrowest" claim — confirmed but mis-prioritized

Sonnet (§5, desktop-specific) calculates: at 1366px laptop, columns become 360 / ~320 / 420, making the middle (Decision Detail) column narrowest. I checked `Decisions.tsx:206`: `xl:grid-cols-[360px_minmax(0,1fr)_420px]`. Sonnet's math is right — the *detail* column is meant to be the visual anchor of the page and is the narrowest. **However**, my Round 1 push to change `xl:` → `lg:` breakpoint is a different fix than Sonnet's column-width re-calibration. The right premium move combines both: change the breakpoint to `lg:` *and* reorder columns to `360px_420px_minmax(0,1fr)` so detail gets the flex column. Neither of us alone proposed this combined fix; together it's complete.

### 4.3 Gemini's "Options uses border-amber-400 active state" — confirmed

`OptionsLayout.tsx:56`: `isActive ? 'border-b-2 border-amber-400 text-fg' : ...`. Gemini's claim is true. Amber active state inside a section that uses zinc backgrounds and sits inside an app whose primary accent is `--accent: #4B8BFF` (`index.css:65`) is genuinely jarring. **The Phase 15 tokenization pass should kill `border-amber-400` here as a P0-adjacent change** — it's a single line, a single token swap (`border-[var(--accent)]`), and removes a piece of visual debt that signals "different product."

### 4.4 Sonnet's claim that ActionQueue FilterBar should be sticky — I push back

Sonnet (§3, mobile, and §B point 4 indirectly) implies the FilterBar should be sticky on scroll. I disagree on mobile and agree on desktop. On mobile, Phase 14f-F deliberately *relaxed* sticky behavior — only TopStrip stays pinned (`index.css:1766-1783`). Adding back another sticky element re-fights that decision. The premium move is the *opposite*: on mobile, FilterBar scrolls with content; if the user has scrolled past it and wants to re-filter, they pull-to-top (a gesture mobile-native users expect on a 1-screen-deep list) or hit the SideNav back-to-top affordance. Sticky-on-mobile is a desktop-instinct fix; the elite mobile pattern is *fewer* persistently-pinned elements.

---

## 5. What we collectively underweighted (taste + emotional tone lens)

Reading all four Round 1s side by side, four things are quietly missing:

### 5.1 Cold-start emotional read — what does the user *feel* in the first second?

None of us scored against this. Stripe's dashboard *feels calm and professional* the moment it loads. Linear *feels fast and quiet*. Bloomberg *feels intense and authoritative*. Robinhood *feels playful and risky*. What does this product feel like in the first second?

Re-reading `/overview` cold: ticker animates across the top (motion), four shell layers stack (framing chrome), then the actual content begins. The *first emotional read* is "there is a lot here." That is not a 10/10 emotion. Stripe's emotion is "I'm in control." Linear's emotion is "I can move fast." This product's current emotion is "I am being briefed." That is the right emotion for a research surface — but it's also why Sonnet's recommendation to add more skeletons and Gemini's recommendation to add "ambient AI motion" would push toward "I am being managed," which is wrong. The fix is *less* not *more*.

**The single most premium move available right now is to remove the MarketTicker from above-the-fold on Overview.** It is the page's biggest motion source, it conveys macro-context that the StatusRail already carries, and it competes for first-second attention with the page's actual answer (NAV / posture). Move it to the bottom of TopStrip on Overview only, or behind a quiet toggle. Neither Codex, Sonnet, nor Gemini said this. I think it's the highest-leverage emotional-read change in the whole audit.

### 5.2 Microcopy that still leaks engineering vocabulary — beyond what panelists named

Sonnet and I both flagged "posture," "balanced posture," "freshest." But there is more, and the panelists missed these:

- `PicksPage.tsx:268` — `"${riskCount} signal(s) flagged for risk — see what changed in catalysts first."` The phrase *"signal(s) flagged for risk"* is engineering vocabulary disguised in plain English. Premium: *"3 picks need a closer look — start with what changed today."*
- `EventsResearchPage.tsx:33-37` — `"N symbols from active recommendations · SEC EDGAR feed live"`. The word *"feed"* is plumbing. Premium: *"Tracking N symbols · filings update through the day."*
- `OptionsLayout.tsx:42` — `"Paper-trading guidance · simulated only · no live execution"`. Three disclaimers in one breath. Premium: *"Paper trading — nothing here places real orders."*
- `RiskDashboard.tsx:124-132` — the "Generate explanation" button (which Codex and I both flagged for size) also has the wrong *verb*. *"Generate explanation"* is API vocabulary. Premium: *"Explain this view"* or simply *"Why?"*. The button copy is the most engineer-coded text on a page that aspires to feel premium.

### 5.3 The "what a Bloomberg/Stripe/Linear/Perplexity would specifically do" thought experiment

Each panelist gestured at premium products as a benchmark. None of us actually walked the comparison concretely. Let me, briefly:

- **Stripe on /overview**: would have one number above the fold (today's NAV change), a second-tier "what changed" microcopy strip below it, and a single CTA ("Review N picks"). Stripe would *not* have a launcher grid of four equal cards — Stripe always picks one primary action.
- **Linear on /action-queue**: would have keyboard-first navigation (j/k/o), a command palette (Cmd-K), and would render the queue as a single dense list with inline expand, not a card grid. Linear would *kill* the HealthRail right column entirely and put the three numbers in TopStrip.
- **Perplexity on /events**: would lead with a one-paragraph synthesis ("Today's catalysts: TSLA earnings, Fed minutes, NVDA 8-K"), then sources below. The current page has zero synthesis — it's pure source list.
- **Bloomberg on /options**: would expose 12 tabs proudly — Bloomberg is the one product that earns 12 tabs because every tab is a workspace. But Bloomberg uses a function-key abbreviation system (`OMON`, `SKEW`, `IVAT`) that turns the tab list into a memorizable command set. This product cannot be Bloomberg without earning the function-key vocabulary first; therefore it must collapse to 4 tabs. **The Bloomberg comparison validates Codex/Gemini/me on the collapse — and refutes any "but Bloomberg does it" defense.**

### 5.4 Hierarchy collisions in proposed fixes — where panelists' fixes would make things worse

Several proposed fixes inadvertently demote something that should remain primary:

- **Codex's "make Snapshot the numeric hero and PageChapter the route-context rail"** (§1, recommendation #2) — this *demotes* the PageChapter NOW string ("Engine sees 4 buy · 2 sell · …"). But PageChapter NOW is the page's *most product-shaped* sentence — it's the Stripe-grade "here is the answer." Demoting it to route-context (which is what the SideNav already does) would empty the page of its narrative voice. The right hierarchy fix is the *opposite*: PageChapter NOW becomes the singular hero; Snapshot demotes to a 3-metric strip below it.
- **Sonnet's "add Start-here card to Strategies"** (§6, P1 recommendation) — would make Strategies the *fifth* page with a "Start here" card. The pattern is already overused; Sonnet correctly identified this in §A.5 ("the experience becomes repetitive across all pages"). Adding a fifth instance contradicts Sonnet's own cross-product finding. The premium move on Strategies is *not* a Start-here card — it's a hero metric (active strategies / blocked / eligible) that *is* the orientation.
- **Gemini's "Pattern moves to Signal Lab"** (§1.10) — would push more content into Signal Lab, which I, Gemini, and Sonnet all scored as the page with the worst signal-to-noise ratio (5.0–5.4/10). Adding Patterns there compounds the problem. Patterns belongs on Action Queue as a per-card affordance ("similar past trades"), not on Signal Lab.

---

## 6. Refined per-page scores (Round 2)

| Page | R1 score | R2 score | One-sentence justification |
|---|---|---|---|
| Overview (`/overview`) | 6.8 | **6.8** | Unchanged; the four-hero stacking and ticker-above-fold are the unfixed blockers. |
| Events (`/events`) | 5.5 | **5.5** | Unchanged; silent fetch-error swallow + no synthesis still keep this passive. |
| Action Queue (`/action-queue`) | 7.4 | **7.5** | +0.1 — Codex's "group-level rationale" is genuinely the next unlock; current state remains premium-shaped. |
| Signal Lab (`/signal-lab`) | 5.4 | **5.0** | −0.4 — Sonnet's tombstone framing is sharper than mine; until "Not yet wired" is removed or wired, this page is honestly worse than a 5.4 deserves. |
| Decisions (`/decisions`) | 6.0 | **6.5** | +0.5 — conceding to Gemini that the calm card pattern carries more weight than my visual-coherence downgrade allowed. |
| Strategies (`/strategies`) | 6.4 | **6.4** | Unchanged; missing hero metric is the gap. |
| Options (`/options/*`) | 5.0 | **4.8** | −0.2 — `border-amber-400` active state plus 12-tab `flex-wrap` is more visually offensive than I weighted in R1. |
| Portfolio (`/portfolio`) | 6.2 | **6.2** | Unchanged; default-flip is the unlock. |
| Risk (`/risk`) | 6.0 | **6.0** | Unchanged; "Generate explanation" button copy + size is the hidden premium-feature problem. |
| Alpha Lab (`/research`) | 5.2 | **5.2** | Unchanged; static-fallback honesty problem is still P0 and Sonnet's accessibility ARIA gap adds weight. |
| Ops (`/ops`) | 5.5 | **5.3** | −0.2 — hardcoded JobRow status is more damning than my R1 score reflected; this is a trust-violation page until fixed. |

**Median: 5.5 → 5.5.** The product hasn't gotten worse; my evaluation got more honest about the trust-violation pages.

---

## 7. Refined Phase 15/16/17 roadmap

### Phase 15 — Truth + emotional first-second (ship in 2 weeks)

**P0 truth (all four panelists converge here):**
1. Replace hardcoded JobRow statuses in `Ops.tsx:262-267` (mine + Sonnet's framing).
2. Label or hide the static fallback in `ResearchLab.tsx:85-126` (mine).
3. Restore visible fetch error on `EventsResearchPage.tsx:27` (mine + Sonnet).
4. Verify or remove `GuardrailsToggleButton` UI-only toggle (mine).
5. Remove "Not yet wired" tombstone from Signal Lab (Sonnet's sharper framing of mine).
6. Remove emoji from `Decisions.tsx:359` (Sonnet's catch).
7. Add visible view-toggle on Portfolio brief↔working *and* flip default to brief (Sonnet + Gemini + me converge).

**P1 hierarchy + microcopy:**
8. **Remove MarketTicker from above-the-fold on Overview** (my Round 2 addition — biggest emotional-read leverage).
9. Demote PortfolioSnapshot to 3 primary metrics + ExpertDetails (mine).
10. Hide DensityToggle on inert surfaces (Overview / Events / Signal Lab / Strategies) (Codex + me).
11. Microcopy translation round 2 — including the four engineering-leak phrases I named in §5.2 (mine).
12. Kill `border-amber-400` in OptionsLayout — single-line tokenization (Gemini + me).
13. Add unified loading-skeleton pattern to Events / Signal Lab / Overview (Sonnet's framing).
14. Add NextStepCard to PortfolioTerminal, RiskDashboard, AlphaLab, Ops — but at the *route* level, not in each page (refining Codex).

### Phase 16 — Singularity + Options collapse (3-4 weeks)

15. Options 12 → 4 tabs + `--pi-*` tokenization (universal convergence).
16. Decisions design-system unification + `lg:` breakpoint + column reorder (mine + Sonnet combined).
17. Action Queue thesis-grouping (Codex + me).
18. "What changed" temporal-context pills (mine).
19. Move OverviewRouteSwitch experimental variants behind internal flag (Codex's catch).
20. Strategies hero metric (active / blocked / eligible) — **not** another Start-here card (refining Sonnet).
21. Replicate "Why no buys?" pattern on Strategies / Signal Lab / Risk / Options-Overview empty states (universal convergence on the pattern; my generalization).

### Phase 17 — AI-native and mobile-native (4-6 weeks)

22. One motion vocabulary (`--motion-fast: 120ms`, `--motion-base: 200ms`) tied to *real state changes only* — explicitly rejecting Gemini's ambient-AI-motion proposal.
23. Persistent AI assistant rail (mine, deferred from R1).
24. Inline "Why?" on numeric heroes — note: button copy is "Why?" not "Generate explanation" (mine + microcopy refinement).
25. Mobile bottom-sheet pattern for Decisions row-detail (refining Gemini's master-detail proposal away from sub-routes).
26. Single typeface, single scale — explicitly rejecting Gemini's serif spike.

---

## 8. Re-answering the 12 brief questions

1. **Coherent story?** Mostly, *with caveats now sharper*: Overview's launcher order disagrees with `page_flow.ts` on purpose (defensible per `:198-200` comment) but is *not* documented to the user. Add a tiny "1 / 2 / 3 / 4" reading-order glyph instead of reordering.
2. **Linear/intelligent navigation?** SideNav: yes. In-page: four nav idioms (FilterBar / Options NavLink / AlphaLab buttons / Decisions chips) — three to merge.
3. **Natural Overview → Catalysts → Decisions → Execution → Portfolio → Risk?** Possible via PageChapter NEXT, contradicted by NextStepCard rationale on Overview that says "see catalysts first" while linking to Action Queue (`PicksPage.tsx:264-271`). Microcopy lies about routing.
4. **Dead/passive pages?** Events (no synthesis), Signal Lab lower half (tombstone), Alpha Lab (worksheet feel), Ops middle-band (15 unranked cards).
5. **Collapsible?** Strategies edu (done ✓); Decisions diagnostics (Codex); Risk full breakdowns; Ops 15 cards into 4 super-sections; Decisions/Risk/Ops "Start here" cards become *dismissible* not collapsed-by-default.
6. **Sticky?** Decisions Timeline column at lg+ (mine). FilterBar on **desktop only** (refuting Sonnet for mobile). OpsAnchorNav stack-coordinated.
7. **Visually noisy?** PortfolioSnapshot 8-12 metrics; Options Risk 4-KPI strip; `u-nonprod-ribbon` orange wash; Overview.tsx 5-card 30%-column right rail (Sonnet's catch).
8. **Under-emphasized?** "Generate explanation" button (Codex + Gemini + me); brief↔working toggle (URL-only — universal); SideNav next-step indicator (mine).
9. **Wasted vertical space?** PortfolioSnapshot loading skeleton; PicksPage launcher duplicated metric line; Signal Lab tombstone block; Decisions calm-card+chip-rail+AdvancedDetails 4-layer stack; Alpha Lab `mb-6` spacer (Sonnet's catch).
10. **Too dense?** Options Chain table; PortfolioTerminal positions on mobile; Decisions 3-col below xl; Ops middle-band; Overview.tsx right column at narrow widths.
11. **Mobile fails?** Options 12-tab wrap (universal); Decisions 3-col stacking (universal); Ops (no mobile work — universal); Overview.tsx 5-col NAV strip (Sonnet's catch); RiskDashboard 5 framing layers stacked (mine).
12. **Developer-built?** Ops, Options, Alpha Lab, Signal Lab middle, RiskDashboard middle band, Overview.tsx "System diagnostics" AdvancedDetails (Sonnet's catch).

---

## Final premium-taste verdict (Round 2)

The four-panel debate has converged on the *what*. The remaining disagreements are about the *how* — and they break cleanly along taste lines:

- Gemini wants more (serif font, ambient motion, AI presence).
- Sonnet wants fewer regressions (skeletons everywhere, accessibility ARIA, conservative reorders).
- Codex wants more *coherence* (PageChapter+NextStepCard everywhere, group rationales, IA collapses).
- I want **less** (kill the ticker on Overview, kill amber, kill the 12 tabs, kill the redundant "Start here" cards, kill the duplicate NAV displays, kill the engineering microcopy).

If the project ships my Phase 15 list (the seven P0 truth fixes + the eight P1 hierarchy/microcopy moves), the product crosses from "high-end developer tool with caring scaffolding" to "premium product that respects the user's first ten seconds." That is the elite gap — and it closes by *removing*, not adding.

DONE: docs/research/debates/PHASE_15_elite_ux/round2/opus.md (2,415 words)
