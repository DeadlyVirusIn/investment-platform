# Vision Alignment UI Audit

**Date**: 2026-05-20
**Branch**: phase-1/ledger
**Scope**: Read-only product-cohesion review. Compares the live UI to
the original product vision (calm premium novice-friendly AI mentor /
copilot — NOT terminal, NOT casino, NOT admin dashboard).

## A. Top 10 Highest-Impact UI/UX Mismatches

**1. Default landing exposes 13+ competing widgets above the fold**
- Surface: `apps/web/src/pages/PicksPage.tsx:205-307` (mounted at `/`
  via `OverviewRouteSwitch:46` → returns `<PicksPage/>`)
- Current: TopStrip (6 cells) + MarketTicker + StatusRail (3 segments) +
  DensityToggle + OverviewHero + PageChapter + PortfolioSnapshot
  (hero NAV + sparkline + 4 metric tiles + posture banner) + TodayPanel
  (3-column AI summary + action + 4 mini-cards) + 4-card LauncherGrid.
  ~24 numbers/badges above 100vh.
- Target: 30-second "what matters today." 3-5 calm anchors.
- Gap: cognitive overload; terminal-density.
- Smallest fix: collapse PortfolioSnapshot+TodayPanel into a single
  hero block (one NAV line + one sentence + one CTA). Move LauncherGrid
  below fold.
- Effort: M

**2. SideNav surfaces 12 items in 5 ops sections — operator menu, not novice menu**
- Surface: `apps/web/src/lib/ui/page_flow.ts:25-79`; `SideNav.tsx:34-86`
- Current: Overview / Events / Action Queue / Signal Lab / Decisions /
  Strategies / Options / Portfolio / Risk / Alpha Lab / Ops — labeled
  "MARKET / SIGNALS / EXECUTION / PORTFOLIO / SYSTEM" with monospace
  hotkey badges.
- Target: Today / Holdings / Ideas / Learn (per UX-5 lock).
- Gap: ops vocabulary in Layer 1.
- Smallest fix: mark Signal Lab / Decisions / Alpha Lab / Ops / Risk /
  Agents / Events as section `system`; collapse "SYSTEM" into a single
  "Advanced" expander.
- Effort: S

**3. TopStrip is six dense numeric cells (Bloomberg, not private banker)**
- Surface: `apps/web/src/components/shell/TopStrip.tsx:65-153`
- Current: NAV / Today P&L / Total return / Regime / Engine / Health —
  five of six are operator telemetry. Plus "guided/expert" + "dark/light"
  + "last run HH:MM:SS" toggles on the same row.
- Target: One calm header — name + portfolio value, nothing else
  competing.
- Gap: terminal personality.
- Smallest fix: hide `slot="regime"`, `slot="engine"`, `slot="health"`
  on Layer-1 routes (extend the same CSS pattern used on mobile
  `index.css:2735-2739`); demote "last run HH:MM:SS" to a hover tooltip
  on NAV.
- Effort: S

**4. StatusRail leaks engine vocabulary ("Engine A firing", "Await oversold setup (P15)")**
- Surface: `apps/web/src/components/shell/StatusRail.tsx:14-50`
- Current: "Stress · Engine A idle" / "Await oversold setup (P15)" /
  "Await credit + rates alignment" — Layer-3 engine vocabulary printed
  in a 30px persistent rail across every page.
- Target: Plain English. UX-5 lock: never expose Engine A/B / P15 in
  Layer 1.
- Gap: UX-5 violation.
- Smallest fix: route NEXT through `lib/ui/guidance.ts` (already exists)
  to translate engine literals into mentor phrases. Or hide StatusRail
  on `/overview`.
- Effort: S

**5. Decisions page framed as "audit workstation"**
- Surface: `apps/web/src/pages/Decisions.tsx:1, 93-202`
- Current: comment at line 1 calls it "3-column audit workstation".
  page_flow `why` is "Audit the decision trace and rationale behind each
  signal." 3-column 1024+ grid with `decisions-truth-banner` chip row +
  filter chips ("Recovered", "Flagged").
- Target: Trust-building "AI's recent moves" history — narrative, not
  audit.
- Gap: ops-mentor mismatch.
- Smallest fix: rename chapter to "AI activity history"; keep 3-col grid
  behind a "Show audit detail" toggle, default to single-column timeline.
- Effort: M

**6. PickModal surfaces engineering shrapnel — Engine version, Composite score, Family scores, Raw action**
- Surface: `apps/web/src/components/picks/PickModal.tsx:336-407`
- Current: Header includes `engine ${pick.engine_version}` (line 185).
  Technical details still spills `raw_action`, `raw_adjusted_action`,
  `composite_score`, `engine_version`, `family_scores` (lines 351-388).
  Layer-3 leaks into a Layer-1 modal.
- Target: PickModal is the novice's first deep-dive. No engine internals.
- Gap: UX-5 violation; cognitive cliff.
- Smallest fix: drop `engine ${pick.engine_version}` at line 185. Remove
  "Family scores" + "Composite score" rows from technical details.
- Effort: S

**7. AI track record invisible from Layer 1**
- Surface: `apps/web/src/components/operator/EquityDrawdownChart.tsx`
  is only mounted on `PortfolioTerminal.tsx:295`, `AlphaLab`,
  `RiskDashboard`, legacy `Overview`.
- Current: Default `/portfolio` lands on `CopilotHoldings` — no equity
  curve, no realized-P&L history, no past-prediction view. Novice cannot
  see "is the AI any good?" without flipping to `?view=working`.
- Target: Trust-building "AI's track record" surface visible from
  Layer 1.
- Gap: trust narrative missing.
- Smallest fix: append a small "AI portfolio history" block to
  `CopilotHoldings.tsx:163` that renders the existing `EquitySparkline`
  plus a one-sentence honest summary ("Up X% since Mar 14; biggest
  drawdown Y%").
- Effort: S

**8. Options nav holds 27 routes — 26 dormant**
- Surface: `apps/web/src/App.tsx:123-171`
- Current: 27 distinct `/options/*` routes all reachable. Options
  lifecycle is Gate 5 paused.
- Target: Single "Options (preview)" link, honest-disclosed.
- Gap: clutter; suggests scope the system doesn't honor.
- Smallest fix: keep only `/options` → OptionsOverviewPage in nav;
  route remainder behind `/options/advanced/*` and surface a single
  "Browse advanced" link inside the overview page.
- Effort: M

**9. PickModal reasoning sits below the action badge and price — buried**
- Surface: `apps/web/src/components/picks/PickModal.tsx:208-271`
- Current: Signal badge → AI's reasoning (ReasoningCard) → Reference
  price → Catalysts → Technical details. Beginner sees "buy" badge +
  entry/target/stop loss numbers BEFORE plain-English reasoning.
- Target: "Why?" is primary, prices are reference.
- Gap: order of trust-building reversed.
- Smallest fix: move `<ReasoningCard/>` section (lines 225-232) above
  the Signal badge (line 208). Reasoning is the first thing a mentor
  would say.
- Effort: S

**10. Action color tonality is loud (Robinhood/casino, not private banker)**
- Surface: `apps/web/src/lib/picks/picks.css:18-48`
- Current: BUY = `#34D399` emerald, SELL = `#F87171` red, plus radial
  `--picks-buy-glow` / `--picks-sell-glow` (rgba 0.30) creating "wash"
  behind cards. Hover applies `transform: translateY(-2px)` + bigger
  shadow.
- Target: Calm, premium, trustworthy. Color used for information, not
  theatre.
- Gap: trading-platform polish, not mentor calm.
- Smallest fix: drop glow tokens to `rgba(_,_,_,0.06)` and remove the
  `box-shadow: var(--picks-shadow-hover)` lift; keep the colored
  top-border as the only color cue.
- Effort: S

---

## B. Current vs Target Personality (10 attributes)

| Attribute | Current | Target |
|---|---|---|
| Density (numbers above fold on Home) | ~24 fields | < 6 |
| Tone of nav labels | Ops vocabulary ("Signal Lab", "Ops") | Mentor ("Today", "Ideas", "Learn") |
| Color use | Emerald/red glows + lifts on cards | Information color, no theatre |
| Persistent chrome | TopStrip 6 cells + Ticker + StatusRail (~140-160px) | TopStrip 2 cells (NAV + asof), no rail by default |
| Typography contrast | 11-13px body + uppercase 0.14em labels everywhere | 15-16px for AI voice, labels demoted |
| Engine vocabulary visibility | "Engine A firing", "P15", "stress regime" persistent | Hidden from Layer 1 unless user opts into Working view |
| Information hierarchy | Flat — every section equally prominent | Vertical — AI sentence → portfolio → ideas → rest |
| Number-to-prose ratio | ~80/20 | ~30/70 |
| Surface count | 50+ pages | 5 Layer-1, rest behind Advanced |
| Trust-building surface | Buried at `/portfolio?view=working` | First-class "AI track record" block on Today |

---

## C. Recommended Information Hierarchy (single Home / Today page)

1. **AI voice headline** — one calm sentence. Already exists in
   `OverviewHero.tsx`; promote it to the anchor of the page.
2. **Account value + tiny equity sparkline** — single line, one number,
   one sparkline. From `PortfolioSnapshot.tsx:113-251` (collapsed).
3. **Top action today** — one card. The single highest-conviction pick.
   From `TodayPanel.tsx:75-110` (extracted; drop AI Summary aside +
   mini-grid).
4. **AI's recent moves** — last 3-5 trades with outcomes. New
   composition from `useExecutedTrades`.
5. **What changed since you last visited** — already exists as `diff`
   line in `OverviewHero.tsx`.
6. **Browse more (3 quiet CTAs)** — Ideas / Holdings / Learn. Replace
   the 4-card `launcher-grid` with 3 muted text links.
7. **Footer disclaimer** — already present.

Everything else (Events, Signal Lab, Strategies, Risk, Ops, Alpha Lab)
moves behind an "Advanced" nav section.

---

## D. First Fold vs Second Fold vs Deep

**First fold (above 100vh):**
- Greeting / one-sentence AI read
- NAV + change
- Top action card (one symbol, one CTA)

**Second fold:**
- AI's recent moves (4-5 row strip)
- "What changed since you last visited"
- 3 quiet CTAs (Ideas / Holdings / Learn)

**Deep:**
- Full action queue
- Catalysts / events
- Strategies / options
- Decisions audit
- Ops / Risk / Alpha Lab

---

## E. Navigation Simplification

**Keep visible (Layer-1 nav):**
- Today (`/overview`) — rename from "Overview"
- Ideas (`/action-queue`) — rename from "Action Queue"
- Holdings (`/portfolio`) — rename from "Portfolio"
- Learn (new — points to a glossary/playbooks index)

**Demote to "Advanced" collapsible:**
- Events & Catalysts
- Strategies
- Options
- Risk
- Decisions

**Hide entirely (operator-only, reachable via direct URL):**
- Signal Lab, Alpha Lab, Ops, Agents, Diagnostics, Legacy/*

---

## F. Surface Tier Classification

**Novice-first (default landing, premium tone):**
- `/overview` → PicksPage
- `/portfolio` → CopilotHoldings (brief)
- `/action-queue` (rename Ideas)

**Mentor-secondary (learning, reachable from Layer 1):**
- New `/learn` route — sources from `apps/web/src/lib/novice/glossary`
- PickModal deep view
- Per-position story on CopilotHoldings

**Operator-only (advanced, hidden from default nav):**
- `/decisions`, `/signal-lab`, `/ops`, `/alpha-lab`, `/risk`,
  `/research`, `/agents`, `/diagnostics/pending-t1`,
  `/portfolio?view=working`

**Dormant-honestly-disclosed:**
- `/options/*` (already disclosed; consolidate 27 routes into 1 +
  Advanced subnav)

---

## G. Primary vs Secondary vs Operator Metrics

**Primary (first-fold):**
- NAV (`summary.equity`)
- AI posture sentence (`briefing.headline`)
- Top action symbol + action

**Secondary (second-fold):**
- Total return %
- Daily P&L
- Equity sparkline
- Recent trade count + outcome strip

**Operator-only (hidden from Layer 1):**
- Regime (currently in TopStrip)
- Engine status (currently in TopStrip + StatusRail)
- Anomaly counts (Health pill in TopStrip)
- "last run HH:MM:SS"
- Composite score, family scores, raw_action (currently in PickModal)
- "P15", "credit + rates alignment" (currently in StatusRail NEXT)

---

## H. First 30 Seconds Storyboard

| t | What the user should understand | What they currently see |
|---|---|---|
| 0s  | "I'm in my AI investing copilot. My account is fine." | TopStrip (6 dense numerics) + Ticker + StatusRail + OverviewHero one-sentence + DensityToggle — five competing reads. |
| 5s  | "Today the AI thinks X." | OverviewHero delivers this, but PortfolioSnapshot's NAV hero has higher visual weight. |
| 15s | "The single thing the AI wants me to look at is Y." | TodayPanel surfaces this — but sits below PortfolioSnapshot, one of three competing columns. |
| 30s | "I can trust this — here are its recent moves." | No surface. AI track record only at `/portfolio?view=working`. |

Story breaks at 30s because the trust-building surface is missing
from Layer 1.

---

## I. AI Portfolio / Trust Experience

**What exists:**
- Equity curve via `usePaperEquity` hook + `EquityDrawdownChart.tsx`,
  rendered on legacy/operator surfaces only.
- Tiny `EquitySparkline` on PicksPage today.
- Executed trades list on PortfolioTerminal (operator).
- Decisions timeline (operator-flavored).

**What's missing from Layer 1:**
- "How the AI has done" surface — equity since inception, biggest
  drawdown, win rate, last 5 closed trades with P&L.
- "AI's recent moves" strip — data exists via `useExecutedTrades`,
  not surfaced.

**Smallest fix (no new endpoints):**
- New component `<AITrackRecord/>` on PicksPage second-fold. Reads
  `usePaperEquity` + `useExecutedTrades`. Renders: one-line summary
  ("Up 1.2% since Mar 14; biggest dip −3.4% on Apr 22") + 4 most
  recent closed trades as `<TimeAgo · SYM · +X.X%>`.
- No websockets. No fake real-time. All data already polled.

**Discipline locks:**
- Show losses too (honest losses, not only winners)
- No "AI wins N in a row" framing
- Sparkline alone is not enough; needs the one-line honest synopsis

---

## J. Pages Actively Diluting the Vision

1. **Signal Lab** — "Validate model quality before acting on signals."
2. **Alpha Lab / Research** — Quant terminal vocabulary.
3. **Ops** — Admin dashboard.
4. **Risk** — Has its place; behind Advanced.
5. **ML Lab** — Reachable from `/ml-lab`, no novice purpose.
6. **Agents** — Multi-agent workflow dashboard; off-vision.
7. **Diagnostics / Pending T+1** — Diagnostic surface.
8. **Decisions** — Labeled "audit workstation" in source. Reframe as
   "AI activity history" and demote.
9. **Options 27 routes** — Collapse to one entry + Advanced subnav.
10. **Legacy /legacy/{...}** — Already off-nav; keep them invisible.

---

## Key file:line citations

- Default landing flow: `App.tsx:103` → `OverviewRouteSwitch.tsx:46` → `PicksPage.tsx`
- Nav definition: `lib/ui/page_flow.ts:25-79`
- Persistent chrome: `Shell.tsx:113-138` → TopStrip / MarketTicker / StatusRail
- Engine vocabulary leak in Layer 1: `StatusRail.tsx:26-32`
- PickModal section order: `PickModal.tsx:208-271`
- Action color theatre: `picks.css:18-48, 3949-3956`
- Trust surface buried: `PortfolioRouteSwitch.tsx:34`; no equity chart in `CopilotHoldings.tsx:54-180`
- Options route bloat: `App.tsx:123-171`
- Decisions framing: `Decisions.tsx:1, 95, 220-223`
- Glossary exists but no /learn route: `MetricHelpTooltip.tsx:10-12`, `lib/novice/glossary`

---

## Headline

The product is technically and semantically disciplined (Phase L,
Tier-A lint, HONEST-BANNER, UX-5 are all real), but the visible
default landing still reads like an ops console with a calm voice
glued on top.

**Single highest-leverage move**: collapse persistent chrome to one
calm row, hide engine vocabulary from Layer 1, and add an "AI track
record" block to the default `/overview` page so trust is built
without the user navigating elsewhere.
