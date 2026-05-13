# Phase Opt-C1 — Refinement pass (visual + product)

> Refinement of `OPTIONS_OPT_C1_DESIGN.md` after operator review.
> Backend integrity is solid (Opt-A/B1/B2). Remaining risk is
> **visual execution + cognitive load + emotional feel**.
>
> NO code lands from this document. Pipeline activation
> (`OPTIONS_ENABLED`, scheduler, ThetaData key, paper exec) remains
> the SEPARATE Phase Opt-B3 decision.

---

## 1. Refined product philosophy

The page is a **calm institutional research desk** for paper options
trading. Not a recommendation engine. Not a signal feed. Not a
dashboard.

Three operating principles:

| Principle | Meaning |
|---|---|
| **Research, not advice** | Surface candidates, scores, evidence — never "do this". The operator decides. |
| **Earned visibility** | Numbers appear only when the data backs them. No "78% confidence" before calibration. No "Top Pick" before track record. |
| **Lifecycle as truth** | Every claim ties back to a real lifecycle event. If something hasn't happened, the UI says so. |

What changed from the prior Opt-C1 design:

- "Today's Idea Hero" REMOVED — pseudo-authoritative, anchoring risk
- "78% confidence" labels REMOVED — uncalibrated probability
- Tracker reframed as **workflow journal** (5 grouped sections), not flat table
- Rejection reasons promoted from filter-fail breakdown to **first-class trust feature**
- Dormant mode upgraded with **educational layer** (supported strategies + lifecycle explainer + setup-quality formula explainer)

---

## 2. Revised visual hierarchy

Brief view (default `/options`):

```
┌─────────────────────────────────────────────────────────────────┐
│ Options paper trading                [Brief|Working]  [Guards]  │
│ Research surface · paper-only                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ TODAY'S RESEARCH CANDIDATES                  ⓘ                 │
│   3 candidates · 47 evaluated · 44 filtered out                │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐                           │
│   │ NVDA    │ │ AMD     │ │ MSFT    │                           │
│   │ ●●●●○   │ │ ●●●○○   │ │ ●●●○○   │                           │
│   │ bull cs │ │ iron cd │ │ long pt │                           │
│   └─────────┘ └─────────┘ └─────────┘                           │
│                                                                 │
│ FILTERED OUT TODAY                           ⓘ                 │
│   44 setups failed checks. Top reasons:                        │
│   • spread too wide (18) • IV rank too high (12)               │
│   • open interest below threshold (8) • risk budget (6)        │
│   ▸ See full breakdown                                          │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ PAPER OPTIONS JOURNAL                                           │
│                                                                 │
│   ▾ OPEN POSITIONS · 4                                          │
│     ┌─────────────────────────────────────────────────────┐    │
│     │ row · row · row · row                               │    │
│     └─────────────────────────────────────────────────────┘    │
│                                                                 │
│   ▾ EXPIRING SOON (≤ 5 days) · 2                               │
│     ┌─────────────────────────────────────────────────────┐    │
│     │ row · row                                           │    │
│     └─────────────────────────────────────────────────────┘    │
│                                                                 │
│   ▸ RECENTLY CLOSED (last 7d) · 8                              │
│   ▸ EXPIRED / ASSIGNED · 3                                      │
│   ▸ REJECTED CANDIDATES · 14                                    │
│   ▸ WATCHLIST (high score, not traded) · 6                     │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ LEARNING DESK              gated · 8/30 closed                 │
│   Insights unlock at 30 closed paper trades + 10 per strategy. │
│   ▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░ 27%                          │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ▸ Diagnostics  ·  engine dormant · ThetaData unconfigured       │
│                                                                 │
│ → Open Advanced Research Workspace (5 specialist sections)      │
└─────────────────────────────────────────────────────────────────┘
```

**Reading order = product priority:** today's research → why others were filtered out → what's in flight (the journal) → what we've learned → engineering truth (collapsed) → deep workspace.

---

## 3. Today's Research Candidates — refined concept

### Renaming + reframing

| Removed | Replaced with |
|---|---|
| "Top Pick" / "Best Trade" / "AI says" | "Today's Research Candidates" (section); "Setup" (per-card) |
| Single oversized hero card | Top **3 candidates max**, equal-weight cards |
| "78% confidence" pill | **Setup quality**: dot scale (●●●●○ = 4/5) + label ("strong setup" / "moderate setup" / "early read") |
| Anchored "win probability" | Probability shown ONLY post-calibration (post-learning-threshold) with confidence interval |

### What a candidate card shows

```
┌────────────────────────────────────────┐
│ NVDA    ●●●●○                          │
│ Bull Call Spread · exp 2026-06-18      │
│                                        │
│ Buy 440C / Sell 450C                   │
│ max risk $125 · max profit $375        │
│ breakeven $441.25                      │
│                                        │
│ Reading                                │
│ Trend confirmation + IV in lower       │
│ quartile. 18d to expiry, defined risk. │
│                                        │
│ Setup quality: strong · model rank 1/3 │
│ Lifecycle: candidate (not yet traded)  │
│                                        │
│ ▸ Why this passed all 7 checks         │
│ ▸ Open chain detail                    │
└────────────────────────────────────────┘
```

Field-by-field rationale:

| Field | Source | Why |
|---|---|---|
| Ticker + dot quality | `options_shadow_decision_log.score` mapped to 5-bucket dot scale | Calibrated to research score, not win probability |
| Strategy + expiry | `strategy_name` + leg expiries | Concrete, not abstract |
| Legs | `options_paper_trade_leg` shape | Operator can verify the actual position |
| Risk/reward + breakeven | already on `options_paper_trade` | Trustworthy: max-loss is contractual |
| Reading (1-2 sentences) | derived from filter-pass evidence + reason codes | Honest narrative; never invents |
| Setup quality label | dot count + dormant-state catalog mapping | Calibrated language until calibration data exists |
| Model rank | candidate's rank within today's would-trade list (1/N) | Relative, not absolute |
| Lifecycle pill | `candidate` (not yet traded) / `proposed` / `open` (etc.) | Ties suggestion to lifecycle truth |
| "Why passed" disclosure | filter-pass booleans (liquidity / spread / OI / volume / greeks / IV / risk) | Audit trail, expandable |

### What is NEVER shown on the candidate card

- Win probability (until calibration)
- Expected return %
- Confidence as a percentage
- "Recommended position size"
- "AI advises..."
- Model name
- Anything that implies guarantee

### Setup quality dot scale (5 buckets)

| Score percentile | Dots | Label |
|---|---|---|
| ≥ 90th | ●●●●● | exceptional setup |
| 70–89 | ●●●●○ | strong setup |
| 50–69 | ●●●○○ | moderate setup |
| 30–49 | ●●○○○ | weak setup |
| < 30 | ●○○○○ | early read |

Percentile is computed against the past 30 days of `would_trade=true` shadow decisions for the SAME strategy family. Dormant state: shows the formula in the explainer, not actual dots.

---

## 4. Rejection-reason UX (trust feature)

The single biggest trust-builder. The DB already carries 7 filter-pass booleans per shadow decision row. Surface them honestly.

### Section: "Filtered Out Today"

```
FILTERED OUT TODAY                                            ⓘ
44 setups failed checks today. The system evaluates every
candidate against 7 thresholds before promoting it for paper
trading. Below are the top reasons setups were filtered out:

  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Spread too wide              ████████████████ 18
  IV rank above threshold      ████████████ 12
  Open interest below floor    ████████ 8
  Risk budget exceeded         ██████ 6
  Liquidity insufficient       ████ 4
  Greeks out of range          ███ 3
  Earnings within 7 days       ██ 2
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ▸ Browse rejected candidates (44)
```

### Per-rejected-candidate card (expanded view)

```
TICKER  · Strategy attempted         Setup quality (raw): ●●○○○
                                     Reason filtered: spread 0.42 > 0.25 cap

  PASSED:  liquidity · OI · volume · greeks · risk · earnings
  FAILED:  spread · IV rank
                  ↳ spread = $0.42 (cap: $0.25)
                  ↳ IV rank = 78% (cap: 65%)

  Note: filter thresholds are operator-configured.
  See Working → Strategy Diagnostics for tuning history.
```

### Placement strategy

- **Brief view default**: compact section right below "Today's Research Candidates" — top 7 reasons as a sortable bar chart, with link to full breakdown
- **Tracker workflow group**: "Rejected Candidates" as one of the 6 grouped sections (collapsed by default) — full per-candidate detail on expand
- **Working view → Strategy Diagnostics**: existing tab gets new "rejection breakdown by strategy" panel

### Progressive disclosure

| Surface | Density | Audience |
|---|---|---|
| Brief — bar chart | Top 7 reasons + counts | Novice + operator at-a-glance |
| Brief — "Browse rejected" link | Full list of 44 today | Curious operator |
| Tracker — Rejected group | Full list grouped by reason | Audit / pattern review |
| Working — Strategy Diagnostics | Per-strategy threshold tuning + rejection history | Engineering / threshold calibration |

### Novice-friendly wording (translation table)

| Internal flag | Novice copy |
|---|---|
| `liquidity_pass=false` | "Not enough trading activity" |
| `spread_pass=false` | "Bid-ask spread too wide" |
| `open_interest_pass=false` | "Few existing positions on this contract" |
| `volume_pass=false` | "Low volume today" |
| `greeks_pass=false` | "Risk shape out of range (delta/gamma)" |
| `iv_rank_pass=false` | "Implied volatility too elevated" |
| `risk_pass=false` | "Risk would exceed budget" |
| (new) `earnings_window` | "Earnings announcement too close" |

### Why this is a trust feature

Showing rejections does THREE things at once:
1. Proves the system is actually evaluating, not just suggesting whatever
2. Makes the operator confident in the quality bar
3. Educates the operator about what makes a good setup over time — repeated exposure to "spread too wide" teaches the heuristic

This is the single most important addition. Should be visible in **all three modes** (dormant: shows criteria + sample reasons; pre-learning: shows real rejection counts; learning: same + per-reason historical accuracy).

---

## 5. Tracker as paper-options journal

### From flat table → grouped workflow

The tracker is reorganized into 6 collapsible sections. Each section is a workflow stage. Default state per section listed:

| Section | Default | Sort | Mobile |
|---|---|---|---|
| **OPEN POSITIONS** | expanded | days held desc | card stack |
| **EXPIRING SOON** (≤ 5 days to nearest expiry) | expanded | days-to-expiry asc | card stack |
| **RECENTLY CLOSED** (last 7 days) | expanded | closed_at desc | card stack |
| **EXPIRED / ASSIGNED** | collapsed | closed_at desc | card stack |
| **REJECTED CANDIDATES** (today + last 7 days) | collapsed | reason → time desc | card stack |
| **WATCHLIST** (high-score setups not yet traded) | collapsed | score desc | card stack |

Each section header is a one-line summary (count + key metric), expandable to a table on desktop / card list on mobile.

### Row schema (12 columns) — desktop table

```
Date    Ticker  Strategy        Legs         Exp     Qty Entry    Cur     P&L      %     Status   Quality
5/04    AMZN    Bull Call Spd   c440/c450    6/18    1   $125     $148    +$23     +18%  OPEN     ●●●●○
5/02    NVDA    Iron Condor     4-leg        6/18    1   $200     $145    -$55     -27%  OPEN     ●●●○○
4/30    HR      Long Call       c25          5/15    1   $40      $0      -$40     -100% EXPIRED  ●●○○○
4/22    AVGO    Bull Put Spd    p180/p175    5/15    1   -$80     $0      +$80     +100% CLOSED   ●●●●○
                                                                                          target_hit
```

Column rationale:
- **Date** — entry date (compact MM/DD)
- **Ticker** — bold mono
- **Strategy** — friendly name; full DB strategy_name on hover tooltip
- **Legs** — compressed (c440/c450 = call 440 / call 450; 4-leg = iron condor with 4 legs)
- **Exp** — earliest expiry across legs (compact MM/DD)
- **Qty** — contracts
- **Entry** — entry credit/debit dollars
- **Cur** — current mark (live MTM during market hours; last MTM otherwise)
- **P&L** — $ realized or unrealized
- **%** — % of entry
- **Status** — lifecycle chip (color-coded per Opt-B2 state)
- **Quality** — setup quality dots at entry (post-learning: includes win-rate context for that strategy)

Below row (when expanded): close reason chip + lifecycle event count + link to full timeline.

### Mobile row (card view, < 640 px)

```
┌──────────────────────────────────────────────┐
│ AMZN  Bull Call Spread        ●●●●○         │
│ 5/04 · exp 6/18 · qty 1                     │
│ Entry $125 · Cur $148                        │
│ +$23  +18%                              OPEN │
└──────────────────────────────────────────────┘
```

### Visual density guidance

- Row height: 44 px (matches platform row standard)
- Row separator: 1 px hairline at 6% opacity
- Tabular nums for all numeric columns
- Status chip: small + colored per Opt-B2 state semantics
- Quality dots: 5 dots, filled per percentile bucket
- Hover: subtle background tint (matches existing tape hover)
- No alternating row colors (cleaner)
- No flashing on update (TanStack Query swaps in place)

### Lifecycle emphasis

Status chip color (per Opt-B2):
- `PROPOSED` → neutral gray (small subset; post Opt-B3 transient state)
- `OPEN` → success-green dim
- `EXPIRING` → amber (system-flagged within N days of expiry)
- `CLOSED` → blue
- `EXPIRED` → amber
- `ASSIGNED` → orange-red

Days-held / days-to-expiry shown next to chip as small mono text:
- OPEN: "3d held"
- EXPIRING: "2d to exp"
- CLOSED: "5d held → target_hit"

---

## 6. Dormant-mode refinement

Goal: dormant mode should feel **substantive + educational**, not "broken".

### Layout (dormant)

```
┌─────────────────────────────────────────────────────────────────┐
│ TODAY'S RESEARCH CANDIDATES                                     │
│   AI options research is paused                                 │
│   Engine dormant · activates with Phase Opt-B3                  │
│                                                                 │
│   What appears here when live:                                  │
│   • Top 3 candidates that passed all 7 quality checks           │
│   • Each card: setup quality, legs, risk/reward, breakeven      │
│   • Reading: 1-2 sentence narrative from filter evidence        │
│   • Lifecycle pill: candidate → proposed → open → terminal      │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ FILTERED OUT TODAY (preview)                                    │
│   When live, this section shows real rejection reasons today.  │
│   Below: the 7 quality checks the system runs on every setup.  │
│                                                                 │
│   ┌──────────────────────────────────────────────────────┐     │
│   │ Liquidity · Spread · Open Interest · Volume          │     │
│   │ Greeks · IV Rank · Risk Budget                       │     │
│   │ + earnings-window guard                              │     │
│   └──────────────────────────────────────────────────────┘     │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ SUPPORTED STRATEGY FAMILIES                          8 families │
│ ┌─────────────────┬─────────────────┬─────────────────┐         │
│ │ Long Call       │ Bull Call Spd   │ Bear Put Spd    │         │
│ │ directional ↑   │ defined risk ↑  │ defined risk ↓  │         │
│ │ ▸ explainer     │ ▸ explainer     │ ▸ explainer     │         │
│ └─────────────────┴─────────────────┴─────────────────┘         │
│ ... (5 more)                                                    │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ HOW THE ENGINE EVALUATES SETUPS                                 │
│                                                                 │
│   Step 1: Collect chains       (ThetaData, EOD)                │
│   Step 2: Score candidates     (per-strategy formula)          │
│   Step 3: Apply 7 filters      (liquidity/spread/OI/etc.)      │
│   Step 4: Rank survivors       (top 3 per day)                 │
│   Step 5: Paper exec writes    (T+1 fill, never same-bar)      │
│   Step 6: Lifecycle tracked    (PROPOSED → OPEN → terminal)    │
│                                                                 │
│   ▸ See sample lifecycle (no real trade — illustrative)         │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ PAPER OPTIONS JOURNAL                                           │
│   No paper trades yet. Journal activates with Phase Opt-B3.    │
│   When live, six workflow sections appear: Open · Expiring     │
│   Soon · Recently Closed · Expired/Assigned · Rejected ·       │
│   Watchlist.                                                    │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ LEARNING DESK                                                   │
│   Learning unlocks at 30+ closed paper trades.                 │
│   At threshold: win rate per strategy, calibration plot,       │
│   strategy explorer.                                            │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ ▸ Diagnostics  ·  engine dormant · ThetaData unconfigured       │
│ → Open Advanced Research Workspace (5 specialist sections)      │
└─────────────────────────────────────────────────────────────────┘
```

### Empty-state philosophy (one rule)

> **Every empty section explains its purpose + what will populate it + when.**

No "loading…" forever. No grayed-out placeholders that look broken. No fake numbers. The page tells the operator what they will see when the engine is live, and gives them educational substance in the meantime.

### Dormant components (new + reused)

| Component | Dormant state |
|---|---|
| `OptionsSuggestionsWorkspace` | Empty state with "what appears here" copy + section list |
| `OptionsRejectionsSection` | "Filtered out today (preview)" + list of 7 quality checks |
| `OptionsStrategyCatalog` (NEW) | 8-card grid of supported strategy families with explainers |
| `OptionsEvaluationFlow` (NEW) | 6-step illustrated evaluation flow |
| `OptionsTrackerWorkflow` | "No trades yet — six workflow sections will appear" |
| `OptionsLearningPanel` | Progress-to-gate copy |
| `OptionsDiagnosticsAccordion` | Collapsed, one-line summary |

---

## 7. Research notebook — future direction (architectural placeholder)

NOT implemented in Opt-C1. Documented here so future expansion fits cleanly.

### Concept

Each paper trade can carry **operator-written notes + system-detected context** organized as a research notebook entry. This becomes the operator's institutional memory.

### Note types

| Type | Source | When |
|---|---|---|
| `catalyst_note` | operator-written | pre-trade or at entry |
| `iv_regime_note` | system-detected | at entry (auto-attached) |
| `earnings_context` | system-detected | at entry (auto-attached when ≤ 14d to earnings) |
| `momentum_note` | operator-written or system | at entry |
| `volatility_compression` | system-detected | at entry (when IV rank in lower decile) |
| `thesis_evolution` | operator-written | mid-trade (when thesis changes) |
| `post_trade_lesson` | operator-written | at close (or up to 7d after) |

### Schema (future, not Opt-C1)

```sql
CREATE TABLE options_trade_note (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trade_id        BIGINT NOT NULL REFERENCES options_paper_trade(id),
  note_type       VARCHAR(32) NOT NULL,
  source          VARCHAR(16) NOT NULL,    -- "operator" | "system"
  body            TEXT NOT NULL,
  attachments     JSONB,                   -- charts, links, refs
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_trade_note_trade ON options_trade_note (trade_id, created_at DESC);
```

### Integration points (future)

- **Tracker row** → click "Notes" pill (count of notes attached)
- **Lifecycle timeline** → notes appear as inline markers next to lifecycle events
- **Learning desk** → "what worked / what didn't" reads from `post_trade_lesson` notes
- **Strategy explorer** → pattern-match across notes for repeat themes

### Architectural placeholder in Opt-C1

The Opt-C1 component layout RESERVES a notes column on the tracker row schema (rendered as a "Notes (0)" placeholder pill in dormant + active modes). Click does nothing until Opt-C3 lands the notebook layer.

This is purely a layout reservation — no DB column, no endpoint, no functionality yet. Just visual hint that future expansion is planned.

---

## 8. Visual mockups

### Suggestion card (full mode, desktop)

```
┌─────────────────────────────────────────┐
│  NVDA               ●●●●○  rank 1/3     │
│  Bull Call Spread · exp 6/18 (18d)      │
│  ─────────────────────────────────────  │
│  Buy 440C  ·  Sell 450C                 │
│  max risk    $125                       │
│  max profit  $375                       │
│  breakeven   $441.25                    │
│  ─────────────────────────────────────  │
│  Reading                                │
│  Trend confirmation; IV in lower        │
│  quartile; earnings 21d out.            │
│  ─────────────────────────────────────  │
│  Setup quality: strong                  │
│  Lifecycle: candidate                   │
│  ▸ Why this passed all 7 checks         │
│  ▸ Open chain                           │
└─────────────────────────────────────────┘
```

### Suggestion card (mobile, < 640 px)

```
┌─────────────────────────────────────┐
│ NVDA              ●●●●○  1/3        │
│ Bull Call Spread · 18d              │
│ Buy 440C / Sell 450C                │
│ max risk $125 · max profit $375     │
│ Trend + low IV · earnings 21d out   │
│ ▸ Why                               │
└─────────────────────────────────────┘
```

### Tracker row (desktop)

```
5/04  AMZN  Bull Call Spd  c440/c450  6/18  1  $125  $148  +$23  +18%  ●OPEN 3d held  ●●●●○
5/02  NVDA  Iron Condor    4-leg      6/18  1  $200  $145  -$55  -27%  ●OPEN 5d held  ●●●○○
4/30  HR    Long Call      c25        5/15  1  $40   $0    -$40  -100% ●EXPIRED OTM    ●●○○○
4/22  AVGO  Bull Put Spd   p180/p175  5/15  1  -$80  $0    +$80  +100% ●CLOSED target  ●●●●○
```

### Tracker row (mobile)

```
┌──────────────────────────────────┐
│ AMZN · Bull Call Spread          │
│ ●OPEN  3d held       ●●●●○      │
│ 5/04 · exp 6/18 · qty 1          │
│ Entry $125 · Cur $148            │
│ +$23 (+18%)                      │
└──────────────────────────────────┘
```

### Lifecycle timeline (desktop, expanded from tracker row)

```
TRADE TIMELINE  ·  AMZN Bull Call Spread #14  ·  status: OPEN  3d held

  ●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━○
  PROPOSED              OPEN                       expected exit
  May 4 22:30 ET        May 5 09:31 ET             May 14 16:00 ET
  proposal_hash:        fill: $1.25                target $1.85 / stop $0.50
  abc123def456…         ml_quality: ●●●●○

  EVENT LOG
  ─────────────────────────────────────────────────────────────────
  May 4 22:30 PROPOSED  OPERATOR_API   reason=fill        chain=c4521
  May 5 09:31 FILLED    SCHEDULED_JOB  reason=fill        fill=$1.25
  May 8 16:00 MTM       SCHEDULED_JOB  mark=$1.62                    
  May 9 16:00 MTM       SCHEDULED_JOB  mark=$1.74                    
  ...
```

### Lifecycle chip (compact, inline on tracker row)

```
[●  PROPOSED]                   [●  OPEN  3d held]
[●  EXPIRING  2d to exp]        [●  CLOSED  target_hit]
[●  EXPIRED  OTM]               [●  ASSIGNED  ITM]
```

Color tones:
- PROPOSED: `var(--fg-3)` (neutral gray)
- OPEN: `var(--success)` dimmed (success-green, calm)
- EXPIRING: `var(--warning)` (amber, attention)
- CLOSED: `var(--accent)` (blue)
- EXPIRED: `var(--warning)` (amber, distinct copy)
- ASSIGNED: `var(--danger)` muted (orange-red, distinct copy)

### Learning gate (pre-threshold)

```
LEARNING DESK                                  gated · 8/30 closed

Insights unlock after the engine produces a meaningful sample of
closed paper trades.

  Closed trades            ▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░  8/30   27%
  Distinct strategies      ▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░  1/3    33%
  Per-strategy floor (top) ▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░  3/10   30%
  Trading-day coverage     ▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░  4d/30  13%

  When all gates pass:
  • Win rate per strategy with 95% confidence interval
  • Calibration plot (predicted vs realized win rate)
  • Strategy family scoreboard
  • Best/worst contributors
  • Rejection-reason historical accuracy
```

### Learning desk (post-threshold)

```
LEARNING DESK                                          47 closed

Win rate by strategy (95% CI · sample size shown)
  Bull Call Spread    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░  62% [54-69]  N=22
  Iron Condor         ▓▓▓▓▓▓▓▓▓▓░░░░░░  55% [46-63]  N=15
  Long Call           ▓▓▓▓▓▓░░░░░░░░░░  41% [29-54]  N=10

Calibration  (predicted vs realized win rate, 5 bins, N≥10/bin)
  ●               ●
       ●     ●            ← well-calibrated
              ●
  predicted →

  ▸ Strategy family scoreboard
  ▸ Rejection-reason historical accuracy
```

### Diagnostics accordion (collapsed default)

```
▸ Diagnostics  ·  engine dormant · ThetaData unconfigured · 0 cron rows
```

Click → expands to full Opt-A diagnostics card (config / scheduler / chain / shadow / paper trades / outcomes / ThetaData health).

---

## 9. Working view refinement

Renamed: **"Advanced Research Workspace"**.

Section headers + descriptions:

```
ADVANCED RESEARCH WORKSPACE
───────────────────────────────────────────────────────────────

  STRATEGY LAB
  Inspect strategy templates, their evaluation logic, and
  per-strategy performance over time.
  ▸ Observatory · Diagnostics · Evaluation

  DECISION SUPPORT
  Review individual decision contexts and the framing the
  engine applied to each candidate.
  ▸ Decision Support · Decision Framing

  CHAIN & FEATURES
  Raw chain data, computed features, and scenario replay
  for any (symbol, expiry).
  ▸ Chain · Features · Scenario Replay

  PERFORMANCE
  Aggregate paper-trading performance across all strategies.
  ▸ Paper Performance

  ENGINEERING
  Pipeline diagnostics, risk dashboards, and full system
  truth surface.
  ▸ Risk Dashboard · Diagnostics

When to use this workspace:
You're investigating a specific strategy, decision, or chain.
For day-to-day research + paper-tracking, use the Brief view.

[← Back to Brief view]
```

### Discoverability + onboarding

- Brief view footer carries the link with description: "12 specialist tabs grouped into 5 sections — for deep-dive research"
- First-time visitors to Working view see a one-time tooltip: "Brief view is the everyday surface; Working view is for investigations"
- Each section header is a sticky h2 anchor — operator can deep-link to `/options?view=working#strategy-lab`

### Mobile handling

- Working view on mobile collapses each section into an accordion
- Within an accordion: tabs become a vertical list of 1-row links
- Footer always carries "← Back to Brief view"

---

## 10. Anti-patterns to avoid (visual + product)

| Anti-pattern | Why bad | What to do instead |
|---|---|---|
| "78% confidence" pill | Anchoring + uncalibrated | "●●●●○ strong setup" + dot scale |
| "Top Pick" / "Best Trade" | Pseudo-authoritative | "Today's Research Candidates" (3 max) |
| Single oversized hero card | Anchoring + drama | 3 equal-weight cards |
| Win probability pre-calibration | Misleading | Hide until calibration thresholds pass |
| Fake suggestions in dormant mode | Dishonest | Supported strategy catalog + lifecycle preview + evaluation flow |
| Flashing P&L | Crypto-dashboard energy | TanStack Query in-place swap, no flash |
| Neon green/red P&L | Tone violation | Calm `var(--success)` / `var(--danger)`, not saturated |
| Big empty cards | Looks broken | Empty states with "what will appear here + when" copy |
| Tracker as flat table | Spreadsheet dump | 6 grouped workflow sections, defaults expanded as relevant |
| Diagnostics-first surface | Engineering console feel | Diagnostics collapsed accordion |
| 12-tab horizontal nav at top | Tab chaos | 5 grouped sections, brief view default, working view for deep dive |
| "AI says…" / "AI recommends…" | Authority without evidence | "Reading: trend + low IV; 7/7 checks passed" |
| Hidden rejection reasons | Operator can't audit | Filtered Out Today section + rejected candidates group |
| Live ticking quotes on the desk | Day-trading-terminal feel | EOD/cycle-driven; refresh on poll, not flash |

---

## 11. Future research-notebook integration plan (Opt-C3 placeholder)

Already covered in §7. Architectural placeholder only in Opt-C1: tracker row reserves a "Notes (0)" pill column that's non-functional until Opt-C3.

---

## 12. Final recommended Opt-C1 implementation order

15 steps · ~22h dev across 2-3 sessions · single PR.

| Step | Scope | Dev time | Verify |
|---|---|---|---|
| **1. Strategy catalog component (NEW)** | `OptionsStrategyCatalog` — 8-card grid of supported families with explainers; reads `/api/options/observatory` (existing) | 1.5h | catalog renders 8 strategy cards with calm explainer copy |
| **2. Evaluation flow component (NEW)** | `OptionsEvaluationFlow` — 6-step illustrated flow (Collect → Score → Filter → Rank → Exec → Lifecycle); pure SVG/CSS | 1.5h | flow renders inline on dormant mode |
| **3. Setup quality dot scale + percentile mapper** | Pure helper: maps shadow `score` to 5 dot buckets; computes percentile against last 30d would_trade rows for same strategy | 1h | helper unit-tested with synthetic scores |
| **4. Suggestion card (refined)** | `OptionsSuggestionCard` — 3-up grid component with dot scale + lifecycle pill + "Why passed" disclosure | 2h | dormant: empty grid + "what appears here"; active: real cards |
| **5. Today's Research Candidates section** | `OptionsResearchCandidates` — composes 3 cards + section header + count; reads `/api/options/shadow` filtered to `would_trade=true` | 1h | dormant: empty state + step-1 catalog |
| **6. Filtered Out Today section** | `OptionsRejectionsSection` — bar chart of top 7 reasons + "Browse rejected" link; reads filter-pass booleans from shadow log | 2h | dormant: 7 quality-check chips; active: real bar chart |
| **7. Rejected candidates list (in tracker workflow group)** | `OptionsRejectedCandidatesGroup` — collapsible list of failed candidates with PASS/FAIL evidence per row | 1.5h | empty when no rejections; live when shadow eval runs |
| **8. Lifecycle chip + days-meta** | `OptionsLifecycleChip` (refined) — color + label + days-held/days-to-exp inline | 1h | renders all 6 states with correct tones |
| **9. Tracker workflow grouping** | `OptionsTrackerWorkflow` — 6 collapsible sections; per-section sort defaults; reads `/api/options/paper-trades` + groups client-side | 2.5h | dormant: empty + "6 workflow sections will appear"; active: groups populate |
| **10. Tracker row (refined)** | `OptionsTrackerRow` — desktop 12-col table; mobile card view; quality dots + lifecycle chip + days meta | 2h | renders existing 1-row dataset correctly |
| **11. Lifecycle timeline endpoint + component** | `GET /api/options/trades/{id}/lifecycle` returns event list; `OptionsLifecycleTimeline` consumes | 2h | new endpoint serves Opt-B2 events; timeline shows 0 events for unfilled trade |
| **12. Learning gate + threshold UI** | `OptionsLearningGate` — 4 progress bars (closed / strategies / per-strategy / coverage); pre-threshold copy | 1.5h | bars at 0/30, 0/3, 0/10, 0/30 in dormant mode |
| **13. Learning summary endpoint (gated)** | `GET /api/options/learning/summary` — returns `{enabled: false, gate: {...}}` until thresholds; full aggregates after; Wilson CI | 2h | curl returns gate-progress; never returns aggregates below threshold |
| **14. Diagnostics accordion + view toggles** | `OptionsDiagnosticsAccordion` wraps Opt-A card; collapsed default; `?view=ops` expands by default | 0.5h | one-line summary visible; expand works |
| **15. Working view repositioning** | 5 grouped sections under `?view=working` with headers + descriptions; mobile accordion | 1.5h | all 12 sub-routes still reachable; section headers anchor correctly |

**+ mobile / dark / light QA across all 15 components: ~1h**

**Total: ~22h dev. Single PR. No backend tables added. Two new read-only endpoints.**

### Step-1-through-7 ordering rationale

Steps 1–7 land the dormant-mode improvements first. After step 7, the dormant page already feels substantively better than current Opt-A (catalog + evaluation flow + rejection criteria preview). Steps 8–11 add lifecycle infrastructure. Steps 12–13 add the learning gate. Steps 14–15 finish the diagnostics + working-view repositioning. Single coherent commit at the end.

---

## 13. Discipline locks (still in force)

- ❌ NO pipeline activation; `OPTIONS_ENABLED` stays `false`
- ❌ NO scheduler / cron rows added
- ❌ NO paper trades created
- ❌ NO live broker integration
- ❌ NO same-bar execution
- ❌ NO fake/synthetic suggestions
- ❌ NO placeholder trades
- ❌ NO hidden scheduler changes
- ❌ NO production ML trainer/scorer
- ❌ NO uncalibrated win-probability claims
- ❌ NO authority-coded copy ("AI says…")
- ❌ NO 12-tab removal — preserved at `?view=working`
- ❌ NO new DB tables (notes table is Opt-C3 future, not Opt-C1)
- ❌ NO recommendation engine changes
- ❌ NO strategy code changes

---

## 14. Validation gates before any code

1. Operator approves §1 product philosophy (research desk, not signal feed)
2. Operator approves §3 "Today's Research Candidates" reframing (top 3, no hero, no win-prob until calibrated)
3. Operator approves §4 rejection-reason UX as a first-class trust feature
4. Operator approves §5 tracker workflow grouping (6 sections, not flat table)
5. Operator approves §6 dormant-mode philosophy (empty states explain purpose + future)
6. Operator approves §8 setup-quality dot scale + percentile mapping
7. Operator approves §9 Working view rename + 5-section IA
8. Operator approves §12 implementation order (15 steps, ~22h, single PR)

---

*Document originated 2026-05-12 ~22:00 ET as the Phase Opt-C1
refinement pass. NOT yet implemented. Requires operator approval +
per-step verification before any code lands. Gating constraints
inherited from prior phases remain in force.*
