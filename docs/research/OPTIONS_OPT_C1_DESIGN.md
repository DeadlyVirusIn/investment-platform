# Phase Opt-C1 — AI-native Options Suggestions + Paper Learning Desk

> **Design + planning only.** No code lands from this document.
> Pipeline activation (`OPTIONS_ENABLED`, scheduler rows, ThetaData
> key, first cycle) remains the SEPARATE Phase Opt-B3 decision.
>
> Scope: redesign `/options` Brief view from a diagnostics-first
> dashboard into a calm professional options journal + AI suggestions
> desk + lifecycle-aware tracker + ML learning surface. Working view
> (12 tabs) repositioned as advanced research workspace, not deleted.

---

## 1. Revised product vision

The `/options` page is the operator's **AI-native paper-trading
research desk** — equal parts:

- **Suggestions workspace** — what the AI is recommending today + why
- **Paper tracker** — every paper trade as a journal row with full
  lifecycle auditability
- **Learning surface** — what the system has learned from closed
  trades (gated until N≥30 closed)
- **Strategy explorer** — drill-down into strategy-family performance
- **Diagnostics (collapsed)** — engineering truth, secondary surface

Tone (per UX-4/UX-5 platform locks):

| Want | Avoid |
|---|---|
| Calm, institutional, intelligent, research-focused, novice-readable | Crowded, tab-chaotic, engineering-only, "nothing is running" emotional empty state |
| Trustworthy ("I can audit this") | "Bloomberg terminal" cognitive load |
| Operator-grade authority | Hidden plumbing exposed at Layer 1 |

Three operating modes the page must handle gracefully:

| Mode | Trigger | Default surface |
|---|---|---|
| **Dormant** | `OPTIONS_ENABLED=false` (today's reality) | Calm "engine offline" hero + supported-strategies catalog + lifecycle preview + collapsed diagnostics |
| **Active, pre-learning** | Pipeline live, < 30 closed paper trades | Suggestions workspace + tracker + diagnostics; learning panel says "not ready, N closed" |
| **Active, learning** | ≥ 30 closed paper trades + per-strategy ≥ 10 | Full suggestions + tracker + learning insights + strategy explorer |

The page is the SAME composition in all three modes — sections empty out gracefully rather than disappearing. Operator always knows where things will appear.

---

## 2. Final page hierarchy

```
/options  (default Brief view)
│
├── Today's Idea Hero  (1 line, big confidence chip — or "no idea today")
│
├── Suggestions Workspace
│   ├── candidate cards (active recs from shadow eval)
│   └── empty state: supported strategies + lifecycle flow preview
│
├── Paper Options Tracker
│   ├── Open positions section
│   ├── Recently closed (last 7 days)
│   └── empty state: "first trade lands when paper exec runs (Opt-B3)"
│
├── Learning Insights  (gated — see §4)
│   ├── win-rate by strategy
│   ├── confidence calibration
│   ├── strategy-family scoreboard
│   └── pre-threshold: progress bar to learning gate
│
├── Diagnostics  (collapsed by default; click to expand)
│   ├── Engine state
│   ├── ThetaData health
│   ├── Pipeline freshness
│   └── Configuration flags
│
└── Footer
    ├── Link → "Advanced Research Workspace" (Working view, 12 tabs)
    ├── Paper-only disclaimer
    └── ?view=working toggle (preserves Opt-A behavior)


/options?view=working  (Advanced Research Workspace)
│
├── Strategy Lab section
│   ├── Strategy Observatory
│   ├── Strategy Diagnostics
│   ├── Strategy Evaluation
│
├── Decision Support section
│   ├── Decision Support
│   ├── Decision Framing
│
├── Chain & Features section
│   ├── Chain
│   ├── Features
│   ├── Scenario Replay
│
├── Performance section
│   └── Paper Performance
│
└── Engineering section
    ├── Risk Dashboard
    └── Diagnostics (full)
```

The 12 tabs become 5 grouped sections under the Working header. Routes unchanged; only navigation IA shifts.

---

## 3. Component architecture

New components (Phase Opt-C1 scope):

| Component | Purpose | Key data deps |
|---|---|---|
| `OptionsTodayIdeaHero` | One-line hero showing top suggestion or "no idea today" | `/api/options/shadow?date=today` filtered to `would_trade=true`, top by confidence |
| `OptionsSuggestionsWorkspace` | Card grid of today's would-trade candidates | same as above + supported strategy list (static) |
| `OptionsSuggestionCard` | One candidate: ticker / strategy / direction / legs / confidence / max risk-reward / breakeven / thesis / data freshness / lifecycle chip | `options_shadow_decision_log` joined to `options_paper_trade` (status binding) |
| `OptionsTrackerTable` | Premium journal-style table for paper trades | `/api/options/paper-trades` + lifecycle event count |
| `OptionsTrackerRow` | One trade row with strategy chip + lifecycle pill + P&L | same |
| `OptionsTrackerFilters` | Search + sort + strategy filter + open/closed toggle | client-side |
| `OptionsLearningPanel` | Gated learning insights or progress-to-gate UI | `options_strategy_outcome` + closed-trade count + per-strategy aggregates |
| `OptionsLearningGate` | Pre-threshold UI: 3 progress bars (closed trades, per-strategy floor, calibration sample size) | counts only |
| `OptionsLearningWinRateChart` | Win rate per strategy with confidence interval | `options_strategy_outcome` aggregations |
| `OptionsLearningCalibrationDot` | Calibration plot (predicted vs realized win rate) | aggregations |
| `OptionsStrategyExplorerCard` | Click-through into a strategy family's history | `options_strategy_outcome` filtered by strategy |
| `OptionsLifecycleTimeline` | Visual timeline of FILL → MTM → CLOSE/EXPIRE/ASSIGN events | `options_trade_lifecycle_event` for one trade |
| `OptionsLifecycleChip` | Compact pill showing current state + age | trade.status + trade.opened_at/closed_at |
| `OptionsDiagnosticsAccordion` | Collapsible wrapper around the existing 6 diagnostic sub-cards | `/api/options/pipeline-status` |
| `OptionsAdvancedWorkspaceLink` | Footer affordance to ?view=working with grouped nav preview | none |

Reused components (no change):
- `OptionsStatusBanner` (from Opt-A)
- `OptionsPaperOnlyBanner`
- `OptionsDataAvailabilityBanner`

Removed/repurposed:
- `OptionsTodayIdeasCard` (Opt-A) — replaced by `OptionsTodayIdeaHero` + `OptionsSuggestionsWorkspace`
- `OptionsOpenTradesCard` + `OptionsClosedTradesCard` (Opt-A) — merged into `OptionsTrackerTable`
- `OptionsExplanationPanel` (Opt-A) — folded into Suggestions empty state

---

## 4. Desktop / mobile layouts

### Desktop (≥ 1024 px)

```
┌─────────────────────────────────────────────────────────────────┐
│  Options paper trading      [Brief|Working]   [Guardrails]     │
│  Read-only research surface · Paper-only                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  TODAY'S IDEA                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ NVDA  ●●●●○ 78%   BULL_CALL_SPREAD  exp 2026-06-18         │  │
│  │ Buy 440C / Sell 450C · max risk $125 · max profit $375     │  │
│  │ Reading: implied vol elevated, momentum confirmation       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  SUGGESTIONS WORKSPACE       Today · 3 candidates · 2 watch    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                         │
│  │ NVDA 78% │ │ AMD 64%  │ │ MSFT 61% │                         │
│  │ bull cs  │ │ iron cdr │ │ long put │                         │
│  └──────────┘ └──────────┘ └──────────┘                         │
│                                                                 │
│  PAPER TRACKER               14 open · 47 closed (lifetime)    │
│  [Open · Closed · All]   search [_____]   strategy [____ ▾]    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Date  Tckr  Strategy   Legs  Exp   Qty Entry Cur P&L   │   │
│  │ 5/04  AMZN  BULL_CALL  C/C  6/18   1   $125  $148 +18% │   │
│  │ 5/02  NVDA  IRON_CONDR 4×   6/18   1   $200  $145 -27% │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  LEARNING DESK               (gated — N=3/30 closed)           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Learning not ready · 27 more closed trades to threshold │   │
│  │ ▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 10%                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ▸ Diagnostics (collapsed)                                      │
│                                                                 │
│  → Open Advanced Research Workspace                             │
└─────────────────────────────────────────────────────────────────┘
```

### Tablet (640–1023 px)

- Suggestion cards: 2-col grid → 1-col stack at < 768
- Tracker: same table, horizontal scroll for cols beyond viewport
- Learning desk: full-width single-column

### Mobile (< 640 px)

- Today's Idea: simplified — ticker / strategy / confidence / 1-line thesis only
- Suggestions: 1-col stack
- Tracker: card view (one trade per card) instead of table; key cols only (Date / Ticker / Strategy / P&L / Status)
- Learning: vertical stack of progress bars + win-rate chart simplified to one-line
- Diagnostics: pre-collapsed; tap to expand
- Working view link: always visible at top of footer

---

## 5. Data dependency matrix

For each section: existing data, missing data, activation phase.

| Section | Existing data + endpoint | Missing data | Activation phase | Risk |
|---|---|---|---|---|
| **Today's Idea Hero** | `options_shadow_decision_log` (10 rows, manual seed only) via `/api/options/shadow` | Daily-fresh `would_trade=true` rows | Opt-B3 (cron wires shadow eval daily) | LOW — empty state truthful when no daily run |
| **Suggestions Workspace cards** | `options_shadow_decision_log` (full row w/ filter pass/fail breakdown); `options_strategy_observatory` (static catalog) via `/api/options/observatory` | Per-symbol thesis text (currently bare reason codes); per-strategy display name+formula | Opt-B3 + minor copy work | LOW — supported-strategies catalog already serves dormant state |
| **Today's Idea + suggestion → trade binding** | `options_paper_trade.proposal_hash` (Opt-B1) — links a suggestion to a created paper trade | Crosswalk from `options_shadow_decision_log.run_date+option_symbol` to `options_paper_trade.proposal_hash` | Opt-B3 paper exec writes both; new join column or runtime join | MEDIUM — requires careful join when paper exec runs |
| **Paper Tracker rows** | `/api/options/paper-trades` returns `PaperTradeHeader[]` (status, opened_at, closed_at, P&L, breakeven, max risk/profit, fill model) | Per-trade ML confidence at entry (operator wants); per-strategy display name | Phase Opt-C1 + minor backend adapter | LOW — confidence at entry can be derived from `options_shadow_decision_log` join |
| **Tracker — lifecycle chips** | `options_paper_trade.status` (PROPOSED/OPEN/CLOSED/EXPIRED/ASSIGNED) — Opt-B2 transitions populate | none | Opt-B3 pipeline activation | LOW |
| **Tracker — close reason** | `options_trade_lifecycle_event.payload_json.reason` (Opt-B2) | Read endpoint that surfaces latest CLOSED/EXPIRED/ASSIGNED event per trade | Phase Opt-C1 (new GET endpoint reading lifecycle events) | LOW |
| **Lifecycle Timeline** | `options_trade_lifecycle_event` (Opt-B2 sole writer) | Read endpoint `/api/options/trades/{trade_id}/lifecycle` returning event list | Phase Opt-C1 (new endpoint) | LOW |
| **Learning — win rate per strategy** | `options_strategy_outcome` (45 rows; existing per-horizon outcome scorer at `apps/api/src/domain/options_quality/outcome.py`) | Per-strategy aggregates endpoint | Phase Opt-C1 (new GET) — gated on closed-trade count | MEDIUM — sample-size gate must be enforced server-side |
| **Learning — confidence calibration** | `options_shadow_decision_log.score` + `options_strategy_outcome.realized_pnl` join | Calibration endpoint (binned predicted vs realized) | Phase Opt-C1 (new GET) — gated | MEDIUM — leakage rules apply (only CLOSED outcomes; horizon-aligned) |
| **Learning — best/worst strategies** | derived from win-rate + per-strategy P&L | Aggregate query | Phase Opt-C1 — gated | LOW |
| **Learning — rejection reasons** | `options_shadow_decision_log` filter-pass booleans (liquidity_pass, spread_pass, OI_pass, volume_pass, greeks_pass, IV_rank_pass, risk_pass) | Aggregate counts query | Phase Opt-C1 — no gate (purely diagnostic) | LOW |
| **Diagnostics (collapsed)** | `/api/options/pipeline-status` (Opt-A + Opt-B1) — full truth dump including ThetaData 5-state | none | already shipped | LOW |
| **Working view nav grouping** | existing 12 routes — no data change | none | Phase Opt-C1 (UI only) | LOW |
| **Strategy Explorer drill-down** | `options_strategy_outcome` per strategy + `options_paper_trade` filtered | Existing endpoints + client-side filter | Phase Opt-C1 — gated post-learning | LOW |

**Summary:** the bulk of Opt-C1 UX is supported by EXISTING data + 2-3 new read-only endpoints. Most "missing data" is post-activation — the page composes empty states truthfully until Opt-B3 lands.

---

## 6. Dormant-mode UX

The page must NOT feel broken when `OPTIONS_ENABLED=false`. Today's Opt-A surface is honest but emotionally empty. The Opt-C1 dormant mode upgrades this.

### Dormant page composition

```
TODAY'S IDEA
  ┌──────────────────────────────────────────────────────┐
  │  AI options suggestions are paused                   │
  │  Engine off · activates with Phase Opt-B3            │
  │                                                      │
  │  When live, this hero will surface today's highest   │
  │  confidence paper-only trade idea.                   │
  └──────────────────────────────────────────────────────┘

SUGGESTIONS WORKSPACE
  Supported strategy families (catalog — what the engine can suggest):
  ┌────────────────────┬────────────────────┬────────────────────┐
  │ Bull Call Spread   │ Iron Condor        │ Long Put           │
  │ directional · low risk · defined max-loss                    │
  └────────────────────┴────────────────────┴────────────────────┘
  ... (8 family chips from observatory)

  Lifecycle preview:
  PROPOSED ─FILL─> OPEN ─CLOSE/EXPIRE/ASSIGN─> (terminal)

PAPER TRACKER
  No paper options trades yet.
  Tracker activates with Phase Opt-B3. Each trade will show
  date, ticker, strategy, P&L, lifecycle status, and full
  audit trail.

LEARNING DESK
  Learning not ready — engine has not produced any closed
  trades yet. Threshold: 30 closed trades + ≥10 per strategy
  before the system reports calibrated insights.

▸ Diagnostics (collapsed)
  Engine state · ThetaData health · scheduler wiring · flag truths

→ Advanced Research Workspace (12 specialist tabs)
```

**Key dormant-mode rules:**
- No empty grid spinners
- No "loading…" infinite states
- Every section explains what it WILL show + when
- Catalog (supported strategies, lifecycle flow) gives the page substance even when engine is dormant
- Diagnostics collapsed — operator can still expand to see full truth

---

## 7. Active-mode UX

When `OPTIONS_ENABLED=true` AND today's shadow eval has run AND paper exec has produced at least one trade:

- **Today's Idea Hero**: top would_trade candidate by confidence; if tied, by lowest max_loss
- **Suggestions Workspace**: cards for every `would_trade=true` row from today; "watch" cards for rows with score in upper-quartile but failed one filter
- **Tracker**: real rows with sortable columns + filter chips
- **Learning Desk**: still gated until threshold (operator sees progress bar)
- **Diagnostics**: still collapsed by default, expandable

When BOTH active AND learning-threshold passed:
- Learning panel unfurls into win-rate-by-strategy + calibration + rejection reasons
- Strategy Explorer becomes interactive

---

## 8. ML gating plan

**Hard gates before any ML insight surfaces:**

| Gate | Threshold | Rationale |
|---|---|---|
| Total CLOSED paper trades | ≥ 30 | Floor for any aggregate estimate; below this, sample variance dominates |
| Per-strategy CLOSED trades | ≥ 10 | Per-strategy claims need per-strategy samples |
| Distinct strategy families with ≥ 10 CLOSED | ≥ 3 | Avoid one-strategy dataset masquerading as a portfolio insight |
| Calendar coverage (CLOSED trades) | ≥ 30 trading days | Avoid one-week regime artifact |
| `ML_OPTIONS_LEARNING_ENABLED` env flag | `true` | Operator-controlled master switch (default `false`) |

Below thresholds: the Learning Desk shows a calm progress UI:

```
LEARNING DESK
  Learning not ready · 8 of 30 closed trades · 22 to threshold
  ▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░ 27%

  Per-strategy samples (need ≥10 each in ≥3 strategies):
    BULL_CALL_SPREAD   3   ░░░░░░░░░░
    LONG_CALL          2   ░░░░░░░░░░
    IRON_CONDOR        1   ░░░░░░░░░░

  Calibration confidence intervals shown when sample size
  passes thresholds.
```

**After gates pass — what's shown:**

| Metric | Display | Confidence |
|---|---|---|
| Win rate per strategy | Bar chart with Wilson score interval (95%) | error bars on every bar |
| Average P&L per strategy | $ + % with 95% CI | shown |
| Calibration | Reliability diagram, 5 bins | per-bin sample size visible |
| Best/worst strategy | Sorted by Sharpe-equivalent (mean / σ) | only when ≥ 5 strategies pass per-strategy gate |
| Rejection reasons | Bar chart of filter-fail counts | always (diagnostic, not predictive) |

**Anti-overfitting protections:**

- Win rate: Wilson score interval, not point estimate
- Calibration: minimum 10 samples per bin or that bin is hidden
- Strategy ranking: minimum 30-day window (rolling) before claiming "best/worst"
- No backtesting on intraday data not yet available
- No claims about future performance — all stats labeled "to date, paper-only, sample N"

**Leakage prevention:**

- Outcome scorer (`apps/api/src/domain/options_quality/outcome.py`) already enforces: outcome bar must be `>= submitted_at + horizon_days`. Inherit this contract.
- Calibration join filters: only CLOSED trades; outcome.created_at > trade.opened_at + horizon_days
- Per-strategy aggregation excludes the most recent 5 trading days (avoid contamination from in-flight trades)

---

## 9. Advanced workspace plan (Working view)

The 12 tabs become 5 grouped sections under `?view=working`:

```
ADVANCED RESEARCH WORKSPACE
  ┌─────────────────────────────────────────────────────────────┐
  │ Strategy Lab     Decision Support     Chain & Features      │
  │ ─────────────    ─────────────────    ──────────────────    │
  │ Observatory      Decision Support     Chain                 │
  │ Diagnostics      Decision Framing     Features              │
  │ Evaluation                            Scenario Replay       │
  │                                                             │
  │ Performance              Engineering                        │
  │ ───────────              ───────────                        │
  │ Paper Performance        Risk Dashboard                     │
  │                          Diagnostics (full)                 │
  └─────────────────────────────────────────────────────────────┘
```

Routes unchanged. Navigation IA:
- Section headers as h2 anchors (`#strategy-lab`, `#decision-support`, etc.)
- Tab nav still works at the top for direct navigation
- Each section has a 1-line description so a novice in Working view knows what each cluster is for

This preserves the operator's mental model from Opt-A (12 tabs all reachable) while adding semantic grouping.

---

## 10. Lifecycle UX (visual treatment)

### Lifecycle chip (compact, inline on tracker rows)

```
[● PROPOSED] [● OPEN  · 3d held] [● CLOSED · target hit · 5d held] [● EXPIRED · OTM] [● ASSIGNED · ITM]
```

Tone:
- PROPOSED: neutral gray
- OPEN: success-green dim (active position)
- CLOSED: blue (completed normally)
- EXPIRED: amber (passive exit)
- ASSIGNED: orange-red (assignment occurred)

### Lifecycle timeline (expanded view, clicked from a tracker row)

```
TRADE TIMELINE — AMZN BULL_CALL_SPREAD #14

  ●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━●
  PROPOSED              OPEN                       CLOSED
  May 4 22:30 ET        May 5 09:31 ET             May 14 16:00 ET
                        fill: $1.25                target_hit
                                                   pnl: +$75

  EVENT LOG
  ─────────────────────────────────────────────
  May 4 22:30  PROPOSED   OPERATOR_API
  May 5 09:31  FILLED     SCHEDULED_JOB    fill_price=1.25
  May 9 16:00  MTM        SCHEDULED_JOB    mark=$1.85
  May 14 16:00 CLOSED     SCHEDULED_JOB    reason=target_hit
                                            close=$2.00 pnl=+$75
```

Timeline component:
- Horizontal timeline with state nodes
- Each node carries date + key fact
- Below: full event log table (sortable, filterable by event_type)
- For trades with EXPIRATION/ASSIGNMENT events: per-leg classification visible (OTM/ITM/PIN_RISK)

### Replay visibility

The lifecycle event log makes Opt-B2's idempotency visible:
- Duplicate-event no-ops are NOT shown (only one row per `(trade_id, event_type, event_at_utc)`)
- If operator manually re-runs a transition, no visual change — operator can verify by checking event count

### Terminal-state clarity

- Terminal-state chip color (CLOSED/EXPIRED/ASSIGNED) is visually distinct from active OPEN
- Tracker filter "Active only" toggle excludes terminal trades by default
- "All trades" view groups by status with section headers

---

## 11. Diagnostics repositioning

The current Opt-A diagnostics card is the operator's truth surface. Opt-C1 makes it secondary:

**Default state (Brief view):** collapsed accordion with one-line summary:
```
▸ Diagnostics  ·  engine dormant · ThetaData unconfigured · 0 cron rows
```

Click to expand → full Opt-A diagnostics view (configuration / scheduler wiring / chain ingest / shadow / paper trades / outcomes / ThetaData health).

**Operator-mode toggle:** `?view=ops` query parameter (matches existing pattern from `?view=working`):
- Default: diagnostics collapsed
- `?view=ops`: diagnostics expanded by default + always-visible engine state banner at top
- `?view=working`: diagnostics not shown (dedicated Engineering section under Working has the full diagnostic surface)

**Progressive disclosure:**
- Brief view (novice/operator everyday): collapsed
- Brief + ?view=ops (operator on-call): expanded
- Working view (deep dive): full Engineering section
- Diagnostics page direct (`/options/diagnostics` legacy URL): unchanged

---

## 12. Rollout phases

### Opt-C1 (this design's deliverable — UI/component work, ~12-16h dev)

Lands while pipeline still dormant. Lifts the page from diagnostics-first to product-first.

**Frontend only**, except for 2 small read-only endpoints:
- `GET /api/options/trades/{trade_id}/lifecycle` — event list for one trade
- `GET /api/options/learning/summary` — gated aggregates (returns `{enabled: false, reason: ...}` until thresholds pass)

Components built:
- `OptionsTodayIdeaHero`, `OptionsSuggestionsWorkspace`, `OptionsSuggestionCard`
- `OptionsTrackerTable`, `OptionsTrackerRow`, `OptionsTrackerFilters`
- `OptionsLearningPanel`, `OptionsLearningGate`, `OptionsLearningWinRateChart`, `OptionsLearningCalibrationDot`
- `OptionsLifecycleChip`, `OptionsLifecycleTimeline`
- `OptionsDiagnosticsAccordion` (wraps existing Opt-A diagnostics card)
- `OptionsAdvancedWorkspaceLink`
- Working view nav grouping (5 sections with headers)
- Mobile responsive variants for all of the above

**Verification:** dormant-mode UX shows supported-strategies catalog + lifecycle preview + learning gate + collapsed diagnostics. No fake suggestions / placeholder trades / synthetic learning insights.

### Opt-B3 (separate operator decision — pipeline activation)

When operator approves: cron wiring + flag flip + ThetaData key + first-cycle gates. Page composition unchanged; sections start populating with real data.

### Post-Opt-B3 stabilization (~30 trading days collection)

Page is "active, pre-learning". Suggestions appear, paper trades populate, lifecycle chips work. Learning desk shows progress-to-gate.

### Post-learning-threshold (~30+ closed trades, ≥10 per strategy in ≥3 strategies)

Learning desk activates. Win-rate, calibration, strategy explorer become interactive. ML insights surfaced honestly with sample sizes + confidence intervals.

### Opt-C2 (later, separate decision)

Possible additions after Opt-C1 settles + Opt-B3 lands:
- Per-strategy "what changed" diff annotations
- Trade journaling notes (operator-written rationale per trade)
- Backtest-vs-live comparison on the learning panel
- Alerts when a strategy crosses a confidence threshold up or down

---

## 13. Recommended implementation order (Opt-C1)

| Step | Scope | Dev time | Risk | Verify |
|---|---|---|---|---|
| **1. Component scaffolding** | All 14 new component files with empty-state-only renders. Wire into new `OptionsOverviewPage` composition | 2h | low | page renders dormant-mode layout end-to-end |
| **2. Lifecycle chip + tracker row** | `OptionsLifecycleChip`, `OptionsTrackerRow`, `OptionsTrackerTable` reading existing `/api/options/paper-trades`; lifecycle chip color+text per status | 2h | low | the 1 existing PROPOSED row renders with correct chip |
| **3. `GET /api/options/trades/{trade_id}/lifecycle` endpoint** | Read-only; serves `options_trade_lifecycle_event` rows for one trade. Backed by Opt-B2 sole writer | 1h | low | curl returns event list for the test PROPOSED trade |
| **4. Lifecycle timeline** | `OptionsLifecycleTimeline` consuming the new endpoint | 2h | low | timeline renders 0 events for the unfilled PROPOSED trade; will populate after Opt-B3 |
| **5. Suggestions workspace + cards** | `OptionsSuggestionsWorkspace`, `OptionsSuggestionCard` consuming `/api/options/shadow`; supported-strategies catalog from `/api/options/observatory`; empty state with catalog | 2h | low | shows 0 cards (shadow eval dormant) + catalog of 8 supported strategies |
| **6. Today's Idea Hero** | `OptionsTodayIdeaHero` — top of page; consumes same data as workspace; dormant copy | 1h | low | shows "AI options suggestions are paused" + activation context |
| **7. Tracker filters + sort + search** | `OptionsTrackerFilters` — client-side. Strategy chip filter, status toggle, search by ticker | 1.5h | low | filters work on the 1-row dataset |
| **8. `GET /api/options/learning/summary` endpoint** | Returns `{enabled: false, gate: {...progress...}}` while below threshold; full aggregates after; Wilson score CI; per-strategy minimum 10 enforced | 2h | medium | curl returns gate-progress JSON; `enabled: false` until thresholds met |
| **9. Learning panel + gate UI** | `OptionsLearningPanel`, `OptionsLearningGate`; progress bars; pre-threshold copy | 1.5h | low | progress bar shows 0/30 closed trades with calm gate copy |
| **10. Diagnostics accordion** | `OptionsDiagnosticsAccordion` wrapping the existing Opt-A diagnostics card; collapsed by default | 0.5h | low | one-line summary visible; click expands |
| **11. Working view nav grouping** | 5 section headers + grouped nav under `?view=working`; routes unchanged | 1h | low | all 12 sub-routes still reach via tab nav AND grouped section anchors |
| **12. Mobile + dark/light + responsive QA** | Each component verified at 360 / 768 / 1024 / 1440 px in both themes | 1.5h | low | screenshots at each breakpoint |
| **13. End-to-end DOM verification + commit** | Operator verifies all 6 sections render correctly in dormant mode; no fake data; collapsed diagnostics; advanced workspace link works | 1h | low | commit single PR |

**Total: ~18h dev across 1-2 sessions.**

---

## 14. Risks + mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | Page feels even MORE empty than Opt-A (more sections + more empty states) | Catalog of supported strategies + lifecycle preview + activation context fills space with real informational value |
| 2 | Learning insights leak via premature aggregation | Hard gates: 30 closed + 10/strategy + Wilson CI + per-bin floor + rolling-window exclusion |
| 3 | Tracker becomes a "trading terminal" feel — violates platform calm | Premium-journal styling: tabular-nums, subtle borders, no flashing, no live ticks. Reuse `.intraday-context-line` aesthetic |
| 4 | Mobile complexity — too many sections | Mobile uses card-stack + collapsed everything-but-essential; tracker switches from table to card list at < 640 |
| 5 | Working view loses discoverability after grouping | Footer link from Brief view + grouped section headers with descriptive subtitles |
| 6 | New `/learning/summary` endpoint must not leak future data | Server-side gate enforcement; horizon-aligned outcome joins; minimum sample sizes; tests for leakage |
| 7 | Lifecycle timeline misleading when events are sparse | Empty event log shows "First event arrives on FILL transition (Opt-B3)"; never shows fake history |
| 8 | Operator confusion between Brief / Working / Ops views | Clear toggles in header; URL params `?view=working` and `?view=ops` mirror `/portfolio` pattern |
| 9 | Existing 12-tab tests break | All routes preserved; only Layout component changes; existing route tests untouched |
| 10 | Suggestion → paper trade binding (which suggestion produced which trade) requires join | Phase Opt-B1 added `proposal_hash`; Opt-B3 paper exec writes both shadow row + paper trade row with shared identity. Enforced in Opt-B3, not Opt-C1 |

---

## 15. What this document does NOT do

- ❌ Does NOT activate the pipeline (`OPTIONS_ENABLED` stays `false`)
- ❌ Does NOT add scheduler / cron rows
- ❌ Does NOT create paper trades
- ❌ Does NOT enable ThetaData ingestion
- ❌ Does NOT propose new ML training runs
- ❌ Does NOT change recommendation engine
- ❌ Does NOT change strategy code
- ❌ Does NOT change EOD source-of-truth
- ❌ Does NOT propose Opt-B3 implementation
- ❌ Does NOT propose live broker integration
- ❌ Does NOT weaken same-bar execution rule
- ❌ Does NOT remove the 12 advanced tabs

---

## Validation gates before approval

1. Operator approves §1 product vision (suggestions + tracker + learning desk, not diagnostics console)
2. Operator approves §2 page hierarchy
3. Operator approves §8 ML gating thresholds (30 closed / 10 per strategy / 3 strategies / 30 trading days)
4. Operator approves §9 Working view grouping (5 sections preserve all 12 tabs)
5. Operator approves §13 implementation order (or proposes a different sequence)

---

*Document originated 2026-05-12 ~21:00 ET as the Phase Opt-C1
design pass. NOT yet implemented. Requires operator approval +
per-step verification before any code lands. Gating constraints
inherited from prior phases remain in force.*
