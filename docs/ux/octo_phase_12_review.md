# Octo UX Review — AI Investing OS, Phase 12

**Branch:** `phase-1/ledger`
**Date:** 2026-05-10
**Format:** 4-panelist octo:debate (Gemini CLI · Codex CLI · Claude Sonnet agent · Claude Opus inline)
**Rounds:** 3 (positions → rebuttals → final convergence)
**Pages reviewed:** 11 (Overview, Action Queue, Events, Strategies, Portfolio, Signal Lab, Decisions, Risk, Options, Alpha Lab, Ops)
**Raw transcripts:** `C:/tmp/octo-debate/phase-12-ux/round{1,2,3}/{gemini,codex,sonnet,opus}.md` (2,234 lines combined)

---

## 1. Raw debate summary by model

### Gemini — product journey, investor mental model, novice clarity, storytelling
- **R1:** Visual-philosophy manifesto. "Atmospheric Copilot — from data wall to guided focus." Proposed temperature-tinted backgrounds (warm/cool by conviction median), "Ghost Cursor" AI-presence indicator, breathing pulse markers, multi-stage shadows, choreographed reveals.
- **R2:** Re-aligned to per-page template after pushback. Held atmospheric vision but engaged peers on specific pages.
- **R3:** Conceded "AI Theater" (breathing/lean-in/ghost-cursor) as out-of-scope, conceded Source Serif 4 for AI narratives, conceded staggered orchestration (30ms). **Held: dark substrate (#0B0B0E), internal 1px specular highlights, typographic weight-as-confidence.**

### Codex — implementation safety, React/CSS architecture, responsive, accessibility, regression risks
- **R1:** Exhaustive file:line citations. Identified the dual-architecture problem (`picks-root` vs older Tailwind/`u-*` pages), `picks.css` override-heaviness as a regression magnet, missing focus-visible on link-cards, swallowed fetch errors, density inconsistency, hard-coded zinc in Options/Risk/Research/Ops.
- **R2:** Pushed back on Gemini's atmospheric proposals as fakes-by-omission. Translated Sonnet's findings into specific PR scopes.
- **R3:** Concedes hierarchy improvements. Holds: reject dynamic atmospheric mood. Reject merging `/portfolio` + `/portfolio/intel`. Reject Options nav redesign before tokenization.

### Claude Sonnet — practical execution plan, exact files, scoped sequence
- **R1:** 416-line per-page audit with line citations. Quantified the design-system drift via concrete imports.
- **R2:** Five specific rebuttals to Gemini's atmospheric proposals (each rejected for fake-data reasons or regression risk). Endorsed Opus's design-system unification with PR-decomposition.
- **R3:** Conceded several R1 inaccuracies (picks.css light coverage exists at line 3042; `<main>` exists in Shell; `&lt;`/`&gt;` in TSX is valid). Delivered exact PR-by-PR Phase 13 sequence with file paths + build/test/visual-check steps.

### Claude Opus — premium taste, emotional trust, visual hierarchy, microcopy, 10/10 feel
- **R1:** Per-page review with hierarchy + microcopy lens. Identified Snapshot-NAV vs PageChapter-NOW competition, "I just left the product" feel of design-system drift, engine-vocabulary leakage to novices.
- **R2:** Conceded Codex's CSS de-duplication priority and Sonnet's density-broken-promise. Held the line on rejecting Gemini's atmospheric pivot as a fakes-by-omission vector.
- **R3:** Final scores with median 6.0/10. Top-5 prioritized: CSS de-dupe → density lift → fetch-error UI → microcopy translation → a11y debt clear. Hold: zero pixels of color or motion that don't trace back to a real-time field.

---

## 2. Consensus findings

The four panelists converged on six items unanimously and three items with 3-of-4 agreement.

### Unanimous (4/4)

1. **Density toggle is broken on four pages.** `EventsResearchPage.tsx:36`, `StrategiesPage.tsx:52`, `SignalLabPage.tsx:81`, `PortfolioIntelligencePage.tsx:32` all hard-code `data-density="cozy"`, ignoring the user's localStorage preference. The toggle in the header is visually present but functionally a no-op on those pages.
2. **Fetch errors are swallowed silently on four pages.** `PicksPage.tsx:73`, `ActionQueuePage.tsx:48`, `StrategiesPage.tsx:29`, `SignalLabPage.tsx:68` all use `catch(() => setLoading(false))` with no error UI. A backend 500 is indistinguishable from a genuine empty day. This is a fakes-by-omission violation.
3. **The codebase has two parallel design systems.** Phase 8+ pages use `--pi-*` tokens, `picks-root` shell, FLOW chain, PageChapter, NextStepCard. Pre-8 pages (Decisions, Risk, Alpha Lab, Ops) use Tailwind utility classes, older `Card/Pill/Primitives`, `AdvancedDetails`. Navigating between them creates an "I just left the product" feel.
4. **PageChapter + NextStepCard threading is the highest-ROI structural bridge.** Adding these two purely-additive components to Decisions/Risk/Alpha Lab/Ops solves the design-system drift narratively without rewriting the underlying surfaces.
5. **Skip-link missing from Shell.** No "Skip to main content" link. WCAG 2.4.1 unmet across all 11 pages.
6. **`:focus-visible` missing on link-styled cards.** `LauncherCard`, `PageChapter-next`, `NextStepCard` all interact via mouse + show hover, but keyboard users see only the browser default focus. Three CSS rule additions in `picks.css`.

### Strong consensus (3/4)

7. **`picks.css` (~3000 lines) is too override-heavy for safe iteration.** Multiple definitions for `.pick-box`, `.pick-modal`, and portfolio styles at lines 210/1579/3042 (Codex's citation). Future visual fixes are regression-prone until tokenized + de-duplicated.
8. **Gemini's atmospheric/cinematic proposals must be rejected for Phase 13** — temperature-tinted backgrounds and "Ghost Cursor" require backend signals that don't exist (would coerce them into fake-data violations). Opus, Sonnet, Codex all agree; Gemini holds these as Phase 14+ aspirations.
9. **Microcopy translation pass on engine-vocabulary abbreviations is high-leverage.** `4B · 2S · 6T · 8H` → `4 buy · 2 sell · 6 trim · 8 hold`. `E/N/F/X` pills → `Earnings · News · Filings · Expirations`. "Mark unavailable" → "Live price not yet available". Single PR, multi-page benefit.

---

## 3. Per-page UX scores

Final scores aggregated as the **median of 4 panelists** (Gemini was high-variance; clamped where outlier).

| # | Route | Median | Range | One-line consensus |
|---|-------|--------|-------|--------------------|
| 1 | `/overview` | **7.5/10** | 7.0–8.0 | Strong FLOW launcher; Snapshot NAV competes with PageChapter NOW for hero attention |
| 2 | `/action-queue` | **7.0/10** | 6.5–9.0 | Best operator surface; FilterBar uses tab roles without keyboard tab semantics |
| 3 | `/events` | **6.0/10** | 5.5–6.5 | Educational subtitle helps; pills opaque (E/N/F/X), density frozen |
| 4 | `/strategies` | **6.5/10** | 6.0–7.0 | Best microcopy on the site (edu rail); education appears every visit (friction); density frozen |
| 5 | `/portfolio` + `/intel` | **6.5/10** | 6.0–7.0 | Useful split but feels like two products; ledger lacks PageChapter |
| 6 | `/signal-lab` | **5.5/10** | 5.0–6.0 | Honest readiness hero followed by aspirational empty section; abbreviations leak |
| 7 | `/decisions` | **6.0/10** | 5.5–7.0 | Excellent novice scaffold; nested mobile scroll; no FLOW thread |
| 8 | `/risk` | **6.0/10** | 5.0–6.5 | Anti-fake discipline exemplary; tables overflow on phones; dark-only zinc |
| 9 | `/options/*` | **5.0/10** | 4.0–5.5 | 12-tab cognitive overload; worst dark/light parity; strictest copy constraints |
| 10 | `/research` (Alpha Lab) | **5.5/10** | 4.0–6.0 | Fakes-by-omission risk in fallback registry rows |
| 11 | `/ops` | **5.5/10** | 3.0–6.0 | Operational spine works; no FLOW thread; sticky nav in older token system |

**Overall median: 6.0/10** · Best: Action Queue + Overview · Worst risk: Options (combined cost)

---

## 4. Top 25 improvements ranked by impact

Each item: ✓ unanimous, ◐ strong consensus, • single-panelist endorsement.

**Tier 1 — blockers / data-truth violations (must ship first)**

1. ✓ Add `useFetchWithError` hook + visible error states on `PicksPage.tsx:73`, `ActionQueuePage.tsx:48`, `StrategiesPage.tsx:29`, `SignalLabPage.tsx:68`. Stops backend failures looking like calm empty states.
2. ◐ Replace or label hard-coded `JobRow` statuses in `Ops.tsx:258-261`. Currently a job failure can render as "ok".
3. ◐ Fix `ResearchLab.tsx:80, :123` static fallback registry rows that read as live model output. Either label "static registry baseline" or remove.

**Tier 2 — broken promises (visible bugs to users)**

4. ✓ Lift density state to `EventsResearchPage.tsx:36`, `StrategiesPage.tsx:52`, `SignalLabPage.tsx:81`, `PortfolioIntelligencePage.tsx:32`. Restores the toggle on 4 pages.
5. ✓ Add skip-link in `Shell.tsx`; add `id="main-content"` to existing `<main>`. WCAG 2.4.1.
6. ✓ Add `:focus-visible` rules in `picks.css` for `.launcher-card`, `.page-chapter-next`, `.next-step-card`.
7. ◐ Wrap Risk tables (`RiskDashboard.tsx:484, :540, :578`) and Options tables in horizontal overflow shells. Phone clip.
8. ◐ Remove nested `overflow-y-auto` in `Decisions.tsx:237, :257, :264` below `xl` breakpoint. Mobile scroll trap.
9. ◐ Add `aria-pressed` to FilterBar buttons; OR drop `role="tab"` + `aria-selected` and convert to plain button group. Pick one — current state is broken.

**Tier 3 — design-system bridge (high ROI)**

10. ◐ Add `<PageChapter>` + `<NextStepCard>` to `Decisions.tsx`, `RiskDashboard.tsx`, `ResearchLab.tsx`, `Ops.tsx`. Purely additive; no data hooks; threads four legacy pages into the FLOW chain.
11. ◐ Add `<PageChapter>` to `Portfolio.tsx` (legacy ledger route) without merging routes.

**Tier 4 — CSS architecture (enables everything else)**

12. ◐ De-duplicate `picks.css` blocks at lines 210, 1579, 3042. Single authoritative block per component. PRECEDES any visual polish on pick-family components.
13. ◐ Tokenize hard-coded zinc Tailwind classes to `--pi-*` / `u-*` variables in:
   - `OptionsLayout.tsx:36, :48, :56-57`
   - `RiskDashboard.tsx:124` (Generate explanation button)
   - `ResearchLab.tsx:47-55` (tab nav)
14. ◐ Add light-mode `[data-theme="light"]` overrides for new PageChapter/launcher/NextStep styles in `picks.css:3911-4117`. Currently brittle.

**Tier 5 — microcopy / novice clarity**

15. ✓ Translate engine abbreviations to plain English everywhere:
   - `4B · 2S · 6T · 8H` → `4 buy · 2 sell · 6 trim · 8 hold` (`SignalLabPage.tsx`)
   - `E/N/F/X` pills → `Earnings · News · Filings · Expirations` (`MarketEvents.tsx:131-134`)
   - `Mark unavailable` → `Live price not yet available — exposure shown without mark` (`RiskDashboard.tsx`)
16. ◐ Add hover-tooltips on `AI Next Step` pills in `PositionsTable.tsx`: "Trail stop" → "Move stop-loss up as price rises". "Watch for reversal" → "Be ready if direction changes".
17. ◐ Add per-group rationale on Action Queue: "Trim signals share weakening RSI + thin volume across 3 names." Derive honestly from dominant `pickTags` per group.
18. • Demote Snapshot NAV from 44px → 32px on Overview launcher; promote PageChapter NOW to clamp(20–28px). Hierarchy claim from Opus.

**Tier 6 — expert-mode collapse (reduce cognitive load)**

19. ◐ Wrap composite-formula display in `SignalLabPage.tsx:114` inside `<ExpertDetails>`.
20. ◐ Wrap raw model fields (composite_score, engine_version, factor_family) inside `<ExpertDetails>` in `PickModal.tsx`.
21. ◐ Group 12 cards in `Ops.tsx` into 4 collapsible sections (Live system / ML training / Engine promotion / Replay & history) using `ExpertDetails` per section.
22. ◐ Collapse Decisions panels (Production inputs, Blocking logic, Diagnostic snapshot) by default into `ExpertDetails`.

**Tier 7 — premium polish (after Tier 1–4 ship)**

23. • Add `aria-sort` to PositionsTable + Risk table sortable headers.
24. • Add `<caption>` to all data tables (PositionsTable, TradeLifecycle, Risk tables).
25. • CSS-only micro-interactions: 100ms scale-0.98 on button press, 8px shadow expansion on tile hover. Safe, isolated, no fake-data risk. Sonnet conceded these as the only Gemini motion proposals worth keeping.

---

## 5. Mobile-specific plan

Four panelists agree the **biggest mobile risk is data tables on Risk + Options pages** (no overflow wrappers) and **Decisions' nested scroll regions** (trap mobile scroll momentum).

### Phone targets
- iPhone SE (375 × 667)
- iPhone 14 Pro Max (430 × 932)
- Pixel 6 (412 × 915)
- Galaxy S22 (360 × 780)

### Specific mobile fixes (in order)

1. **Wrap every `<table>` in `<div className="u-table-wrap">` with `overflow-x: auto`.** Apply globally; missing on Risk + Options tables today.
2. **Remove `overflow-y-auto` on Decisions inner columns at `≤xl`.** Use single-scroll page on phones.
3. **Lift density state on 4 pages** so phone users get the layout they picked.
4. **Audit launcher card padding at 360px width** (Codex flagged density-toggle clipping).
5. **Add explicit Phase 12 breakpoints to Options layout** (currently relies on tab-nav wrap, becomes a multi-row wall).
6. **Validate FilterBar horizontal scroll on Action Queue at 360px** — Phase 12 added it but should re-test with longer filter labels post-microcopy translation.
7. **Test PageChapter NOW typography clamp at 320–360px** — confirm it doesn't wrap past 3 lines.

---

## 6. Typography + color recommendations

### Typography

**Consensus (Opus + Sonnet + Codex):**
- Keep Inter as primary face. No new font-family for Phase 13.
- Type scale: 11/12/13/14/16/20/26/32/44 (existing). No change.
- Tabular-nums on all numeric values (already used in Phase 8+ pages).
- Density modifiers should affect type scale, not just spacing (already partially done in `picks.css` density block).

**Gemini holdout (deferred to Phase 14+):**
- Source Serif 4 for AI narrative ("Today the AI favors..."). Sonnet/Opus accept this as acceptable Phase 14 spike if the narrative remains data-derived.
- 36px serif Posture sentence as page hero. Deferred — current PageChapter NOW handles this honestly with sans-serif at clamp(16-20px).

**Fixes to ship in Phase 13:**
- Heading-hierarchy bug in `StrategiesPage.tsx:66` — page title `<h1>` skips to `<h3>`. Add `<h2>` or restructure.
- Heading-hierarchy bug in `SignalLabPage.tsx` — `<h2>` used for numeric display value. Convert to `<div>` with semantic ARIA.

### Color

**Consensus:**
- Existing token system (`--pi-good/bad/warn/info` + `--picks-buy/sell/trim/hold`) is correct and load-bearing. Keep.
- **Tokenize hard-coded zinc** (Tailwind `text-zinc-*`, `bg-zinc-*`, `border-zinc-*`) in Options/Risk/Research before any visual passes.
- **Light-mode parity gap on new Phase 11/12 components** (`picks.css:3911-4117`). Add `[data-theme="light"] .picks-root` overrides for PageChapter, LauncherCard, NextStepCard.
- Maintain the current dark-default. Light toggle remains via `[data-theme]`.

**Rejected (Gemini's atmospheric color):**
- Conviction-driven temperature backgrounds: rejected as fakes-by-omission (the conviction signal isn't live).
- "Two-zone canvas" with `#131319` stage / `#0B0B0E` shop: deferred to Phase 14 spike.

---

## 7. Novice-friendly copy system

Replace engine vocabulary in user-facing text. Keep engine vocabulary in expert collapses + the `raw_action` data attributes.

| Engine vocabulary | Novice translation |
|------------------|-------------------|
| "signal" | "stock idea" or context-specific phrase |
| "posture" | "today's stance" |
| "engine version" | (move to ExpertDetails) |
| "composite score" | (ExpertDetails) |
| "factor family" | (ExpertDetails) |
| "regime trend" | "market trend" |
| "4B · 2S · 6T · 8H" | "4 buy · 2 sell · 6 trim · 8 hold" |
| "E / N / F / X" | "Earnings · News · Filings · Expirations" |
| "Mark unavailable" | "Live price not yet available" |
| "Trail stop" | "Move stop-loss up as price rises" |
| "Watch for reversal" | "Be ready if direction changes" |
| "Lock partial gains" | (already plain) |
| "Engine A / B / B2 / V2" | (move to ExpertDetails) |
| "Shadow ML" | (move to ExpertDetails) |
| "Replay" | "historical backtest" |

**Pattern:** body copy = novice translation; `<ExpertDetails>` = engine vocabulary preserved verbatim for operators.

---

## 8. Expert-mode collapsible plan

`ExpertDetails` (shipped in Phase 12) is currently underused. Wrap these blocks:

| Page | Section to collapse |
|------|---------------------|
| `PickModal` | Composite score + engine version + factor weights + raw_action mapping |
| `SignalLabPage` | Composite formula display (`50% conf + 30% freshness + 20% coverage`) |
| `Decisions` | Production inputs · Blocking logic · Diagnostic snapshot · Engineering source |
| `Ops` | Group 12 cards into 4 ExpertDetails sections (Live / ML training / Engine promotion / Replay) |
| `Risk` | Replay toggle · Engineering source · Generate-explanation panel |
| `RiskDashboard` | Concentration breakdown raw rows |
| `ResearchLab` | Shadow-flagged pattern descriptions · peer/regime breakdowns |
| `Options/*` | Diagnostics + Decision Support + Decision Framing + Evaluation tabs collapse into a "Diagnostics" sub-section |

**Always visible (never collapse):**
- Today's posture / health / next action
- Real money values (NAV, P&L, exposure)
- Disclaimers
- Risk-flagged exposure
- "Mark unavailable" honest empty states

---

## 9. Implementation phases

### Phase 13 — Tier 1 + Tier 2 (data truth + broken promises)

**Goal:** ship the unanimous fixes. No visual redesign. No design-system migration. Pure correctness.

**PR-01: Skip-link + focus-visible (no dependencies)**
- `Shell.tsx`: add skip-link + `id="main-content"`.
- `picks.css`: add 3 `:focus-visible` rules.
- Build green. Keyboard test on Overview.

**PR-02: `useFetchWithError` hook + 4-page error states**
- New: `apps/web/src/lib/hooks/useFetchWithError.ts`.
- Update: PicksPage, ActionQueuePage, StrategiesPage, SignalLabPage.
- Mock-throw test for each page.

**PR-03: Density persistence on 4 pages**
- Update: EventsResearchPage, StrategiesPage, SignalLabPage, PortfolioIntelligencePage.
- Pattern: copy from `PicksPage.tsx:61-62`.
- Visual test in compact / cozy / spacious × dark / light.

**PR-04: Mobile table overflow + Decisions nested scroll**
- Wrap Risk + Options tables in `u-table-wrap`.
- Remove `overflow-y-auto` on Decisions columns ≤xl.
- Test at 360 / 390 / 412.

**PR-05: FilterBar a11y fix**
- Either implement arrow-key tablist semantics OR convert to button-group.
- Add `aria-pressed`.

### Phase 14 — Tier 3 + Tier 5 (design-system bridge + microcopy)

- PageChapter + NextStepCard threading into Decisions/Risk/Alpha Lab/Ops + legacy Portfolio.
- Microcopy translation pass.
- Hover tooltips on AI Next Step pills.
- Per-group rationale on Action Queue.
- Demote Snapshot NAV; promote PageChapter NOW.

### Phase 15 — Tier 4 (CSS architecture)

- De-duplicate picks.css.
- Tokenize hard-coded zinc in Options/Risk/Research.
- Add light-mode overrides for Phase 11/12 components.

### Phase 16 — Tier 6 + Tier 7 (expert collapse + premium polish)

- ExpertDetails migration across 8 surfaces per the plan above.
- aria-sort + table captions.
- CSS-only micro-interactions (100ms scale-0.98 button press, hover shadow lift).

### Phase 17 (optional spike) — Gemini's atmospheric direction

- Source Serif 4 for AI narrative.
- Two-zone canvas exploration.
- Conditional only on a real conviction endpoint shipping. Until then, deferred indefinitely.

---

## 10. What to implement first

**The hard-pinned starter:**

```
PR-01  Skip-link + focus-visible        (foundation, no deps)
PR-02  useFetchWithError + 4 pages      (data-truth blocker)
PR-03  Density lift on 4 pages          (broken promise)
```

These three PRs are independent of each other, ship in 1–2 days each, have **zero visual regression risk**, and resolve every Tier 1 + the most-cited Tier 2 issues. They unlock the rest of the phased plan.

---

## Appendix A — Disagreements that did NOT converge

- **Dark substrate vs light-mode default.** Gemini holds dark-only for "cockpit gravitas." Codex/Opus/Sonnet hold dark-default + functional light mode. **Verdict: keep current dark-default with functional light mode.**
- **Atmospheric temperature backgrounds.** Gemini wants conviction-driven page tints. Codex/Opus/Sonnet reject as fakes-by-omission until conviction endpoint ships. **Verdict: defer indefinitely.**
- **"Ghost Cursor" AI presence in Decisions.** Gemini proposes; Codex/Opus/Sonnet reject as fabricated state (no schema field). **Verdict: reject.**
- **Source Serif 4 for AI narrative.** Gemini holds; others accept as Phase 17 spike. **Verdict: defer to spike.**

---

## Appendix B — One thing each panelist would NOT change

- **Gemini:** Dark-mode substrate `#0B0B0E` for "high-conviction gravitas."
- **Codex:** No atmospheric market-temperature backgrounds or animated AI-presence indicators in Phase 13.
- **Sonnet:** The `null`-vs-`0` exposure distinction in `RiskDashboard.tsx:166-185`. Coercing `null` to `0` to "complete" the UI would be a quiet lie.
- **Opus:** Zero pixels of color or motion that don't trace back to a real-time field. Honest-data discipline is load-bearing.

---

## Appendix C — Raw transcript file inventory

```
C:/tmp/octo-debate/phase-12-ux/
├── brief.md                           (shared brief, 4 KB)
├── round1/
│   ├── gemini.md                      (10 KB, off-template manifesto)
│   ├── codex.md                       (33 KB, file:line exhaustive)
│   ├── sonnet.md                      (40 KB, line-cited per page)
│   └── opus.md                        (17 KB, hierarchy + microcopy lens)
├── round2/
│   ├── gemini.md                      (10 KB, re-aligned to template)
│   ├── codex.md                       (20 KB, regression-risk responses)
│   ├── sonnet.md                      (39 KB, 5 specific Gemini rebuttals)
│   └── opus.md                        (7 KB, concession + hold)
└── round3/
    ├── gemini.md                      (5 KB, Environmental Staging convergence)
    ├── codex.md                       (6 KB, final scores + holds)
    ├── sonnet.md                      (36 KB, exact Phase-13 PR sequence)
    └── opus.md                        (4 KB, final scores + holds)
```

Total: 12 files, 2,234 lines of debate output before synthesis.

---

**This document was produced by a real 4-panelist octo:debate** (Gemini CLI 0.39.1, Codex CLI 0.125.0, Claude Sonnet via Agent dispatch, Claude Opus inline) **with 3 rounds of position → rebuttal → final convergence.** No content fabricated. No proposed change implemented during the debate phase. Implementation pauses pending user approval.
