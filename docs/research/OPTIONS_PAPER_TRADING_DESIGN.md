---
phase: 11A
status: DESIGN ONLY
date: 2026-04-26
locks:
  v1_paper_only: true
  options_paper_only_flag: true        # OPTIONS_PAPER_ONLY=true permanent v1
  options_ml_can_affect_trades: false  # permanent v1
  fill_model: mid_plus_25_pct_spread
  fill_model_alt: mid_minus_one_tick
  fee_per_contract_per_leg_dollars: 0.65
  multi_leg_atomic_fills: true
  no_partial_fills_v1: true
  greeks_engine_canonical: QuantLib
  greeks_engine_fallback: py_vollib
  build_first: [expiration_handler, assignment_handler]
sources:
  synthesis: ~/.claude-octopus/discover/options-system-research/synthesis.md
  reviewers: [Codex, Gemini, Sonnet, Opus]
---

# Options Paper-Trading Engine — Design

**Status:** Design only. NO source code.
**Build invariant:** `expiration_handler.py` + `assignment_handler.py` ship FIRST, end-to-end-tested, before any strategy logic.
**Source:** Octo Discover synthesis (2026-04-26).

---

## 1. Why this discipline

Per Sonnet (pragmatic implementer) and reinforced by all 4 reviewers:

> **Most options paper-trading systems fail at expiration handling, not at strategy logic.** An ATM short put incorrectly assigned (or silently ignored) at expiry corrupts the entire P&L history. Build expiration + assignment handlers FIRST, before any strategy code, and end-to-end test against synthetic inputs.

Therefore Phase 11E build order:
1. `expiration_handler.py` + tests
2. `assignment_handler.py` + tests
3. `lifecycle.py` + tests (state-transition machine)
4. `fill_simulator.py` + tests
5. `risk_snapshot.py` + tests
6. THEN: `strategies/short_put_credit_spread.py`
7. THEN: `strategies/short_call_credit_spread.py`
8. THEN: `strategies/iron_condor.py`

---

## 2. Multi-leg trade representation

### 2.1 Schema (Phase 11B will materialize; included here for clarity)

```
options_paper_trade
  id                       BIGSERIAL PK
  underlying               TEXT
  strategy_name            TEXT       # e.g. "short_put_credit_spread"
  strategy_version         TEXT       # frozen at entry; for audit
  state                    TEXT       # PROPOSED|OPEN|EXPIRING|CLOSED|EXPIRED|ASSIGNED
  entry_at_utc             TIMESTAMPTZ
  exit_at_utc              TIMESTAMPTZ NULL
  entry_credit_dollars     NUMERIC(12, 4)  # signed; positive = credit received
  exit_debit_dollars       NUMERIC(12, 4) NULL
  realized_pnl_dollars     NUMERIC(12, 4) NULL
  fees_total_dollars       NUMERIC(12, 4)  # round-trip
  max_loss_dollars         NUMERIC(12, 4)
  max_profit_dollars       NUMERIC(12, 4)
  breakeven_lower          NUMERIC(12, 4) NULL
  breakeven_upper          NUMERIC(12, 4) NULL
  fill_model_version       TEXT       # frozen at entry; for replay
  rollback_reason          TEXT NULL  # for forced closes
  created_at_utc           TIMESTAMPTZ DEFAULT now()
  updated_at_utc           TIMESTAMPTZ DEFAULT now()

options_paper_trade_leg
  id                       BIGSERIAL PK
  trade_id                 BIGINT FK → options_paper_trade.id ON DELETE RESTRICT
  leg_index                INT       # 0-based; deterministic order per strategy
  option_symbol            TEXT      # OCC
  underlying               TEXT
  expiry                   DATE
  strike                   NUMERIC(12, 4)
  right                    TEXT      # "C" | "P"
  side                     TEXT      # "SELL" | "BUY"
  qty                      INT       # contracts
  -- entry quote snapshot (frozen at entry decision time)
  entry_quote_at_utc       TIMESTAMPTZ
  entry_bid                NUMERIC(12, 4)
  entry_ask                NUMERIC(12, 4)
  entry_mid                NUMERIC(12, 4)
  entry_iv                 NUMERIC(12, 6)
  entry_delta              NUMERIC(12, 6)
  entry_gamma              NUMERIC(12, 6)
  entry_theta              NUMERIC(12, 6)
  entry_vega               NUMERIC(12, 6)
  entry_fill_price         NUMERIC(12, 4)   # actual paper fill, not mid
  -- exit (null until close)
  exit_quote_at_utc        TIMESTAMPTZ NULL
  exit_bid                 NUMERIC(12, 4) NULL
  exit_ask                 NUMERIC(12, 4) NULL
  exit_mid                 NUMERIC(12, 4) NULL
  exit_iv                  NUMERIC(12, 6) NULL
  exit_delta               NUMERIC(12, 6) NULL
  exit_gamma               NUMERIC(12, 6) NULL
  exit_theta               NUMERIC(12, 6) NULL
  exit_vega                NUMERIC(12, 6) NULL
  exit_fill_price          NUMERIC(12, 4) NULL
  exit_reason              TEXT NULL   # 'PROFIT_TARGET'|'LOSS_LIMIT'|'TIME'|'EXPIRY_OTM'|'EXPIRY_ITM_ASSIGNED'|'PIN_RISK_FORCE_CLOSE'|...
```

**Atomicity:** all legs of a multi-leg trade share the same `trade_id`. The trade transitions states atomically: either all legs reach OPEN together or the trade is rejected.

### 2.2 Leg ordering convention

Per strategy, legs are stored in a deterministic order (Phase 11E spec):

| Strategy | Leg order |
|---|---|
| short_put_credit_spread | 0 = short put, 1 = long put |
| short_call_credit_spread | 0 = short call, 1 = long call |
| iron_condor | 0 = short put, 1 = long put, 2 = short call, 3 = long call |

Replay code can reconstruct strategy intent from leg ordering alone.

---

## 3. Fill model

### 3.1 v1 default: `mid_plus_25_pct_spread`

```
For SELL legs:
    fill_price = mid + 0.25 × (ask − mid)        # pay 75% toward ask (worse for seller)
For BUY legs:
    fill_price = mid + 0.25 × (ask − mid)        # pay 75% toward ask (worse for buyer? — no, this benefits buyer)

Wait — sign convention: when SELLING you receive credit; "worse" means receiving LESS:
For SELL (you receive premium): fill_credit_received = mid - 0.25 × (mid - bid)  (you accept 25% of spread below mid)
For BUY (you pay premium): fill_debit_paid = mid + 0.25 × (ask - mid)  (you pay 25% of spread above mid)
```

**Conservative fill = always slightly worse than mid in the direction that hurts.**

### 3.2 v1 alternative: `mid_minus_one_tick` (Sonnet's stricter version)

Per-leg slippage = 1 tick = $0.01 for ETF options at $0.01-tick exchanges.
- SELL legs: receive `mid − $0.01` per contract
- BUY legs: pay `mid + $0.01` per contract

Selectable via env `OPTIONS_DEFAULT_FILL_MODEL`. Default: `mid_plus_25_pct_spread` (Opus). Alternative: `mid_minus_one_tick` (Sonnet) for ETF-only universes where ticks are tight.

### 3.3 Multi-leg atomicity

- All legs fill simultaneously OR none fill (no partial fills v1)
- No leg-out modeling on entry — documented as a known model limitation
- For exits: same atomicity; a multi-leg position closes as a single transaction

### 3.4 Snapshot freshness

- Quote age: every leg's `entry_quote_at_utc` must satisfy `now() − quote_at ≤ 5s` at fill time
- If any leg fails: reject entire trade with reason `"STALE_QUOTE_AT_FILL"`
- This is conservative; real brokers would slip the trade, not reject

### 3.5 Fill model versioning

`fill_model_version` is frozen at trade entry. Any future change to the
fill model preserves historical trades' computed entry/exit prices —
new model only applies to NEW trades. Replay tooling can reconstruct
fills under either model.

---

## 4. Fees

| Fee component | Per leg | Source |
|---|---:|---|
| Commission | $0.65 | TastyTrade standard |
| Exchange / regulatory fees (ORF, OCC, etc.) | $0.10 (estimate) | Composite estimate |
| **Total per leg per side** | **$0.75** | Round-trip per leg = $1.50 |

**Per-trade examples:**

| Strategy | Legs | Entry fees | Exit fees | Round-trip total |
|---|---:|---:|---:|---:|
| Short put credit spread | 2 | $1.50 | $1.50 | $3.00 |
| Short call credit spread | 2 | $1.50 | $1.50 | $3.00 |
| Iron condor | 4 | $3.00 | $3.00 | $6.00 |

Fees deducted from realized P&L at close. Stored verbatim in `fees_total_dollars` for audit.

**Assignment fee:** $0.00 per contract (TastyTrade-style).
**Exercise fee:** $0.00 per contract.
**Frozen v1 — no fee tuning.**

---

## 5. Greeks at entry / exit / EOD

### 5.1 Entry

Greeks (delta, gamma, theta, vega, IV) for each leg are stored at entry from the chain snapshot at decision time. **Source: ThetaData pre-computed Greeks; canonical fallback: QuantLib (computed on demand if provider Greeks missing or sanity-failing).**

### 5.2 Exit

Same fields stored at exit (whether close, expiry, or assignment).

### 5.3 EOD mark-to-market

Nightly `options_paper_mtm_daily.py` job:
- For every OPEN trade: pull current chain snapshot, compute current_mid per leg, compute current portfolio Greeks
- Store one `options_risk_snapshot` row per trade per day
- Compute unrealized P&L = (current_mid_total_credit − entry_credit_total) for short-premium trades
- Surface delta drift, theta decay, vega P/L decomposition

### 5.4 Portfolio risk snapshot (daily)

Aggregate across all OPEN trades:
- Net delta (sum across positions, beta-weighted optional v2)
- Net gamma
- Net theta (daily decay revenue)
- Net vega (volatility exposure)
- Worst-case loss across positions (sum of max_loss per position)
- P/L decomposition (realized vs unrealized, delta P/L vs theta decay vs vega P/L)

---

## 6. Lifecycle states

```
                  ┌──────────────┐
                  │   PROPOSED   │  ← operator-clicked "paper trade"
                  └──────┬───────┘
                         │ all legs filled atomically
                         ▼
                  ┌──────────────┐
                  │     OPEN     │
                  └──────┬───────┘
            ┌────────────┼────────────────┐
            │            │                │
         (T-7 DTE)   (operator-close)  (any exit criterion)
            ▼            ▼                ▼
    ┌──────────────────────────────────────────┐
    │              EXPIRING (within 7 DTE)     │
    └──────┬─────────────┬──────────┬──────────┘
           │             │          │
       (close)       (expire)   (assign)
           ▼             ▼          ▼
       ┌────────┐  ┌──────────┐ ┌──────────┐
       │ CLOSED │  │ EXPIRED  │ │ ASSIGNED │
       └────────┘  └──────────┘ └──────────┘
```

State transitions are append-only (audit log). Each state transition writes to `options_paper_trade_event` table:
- `event_type` (one of the labels above)
- `event_at_utc`
- `triggered_by` (`SCHEDULED_JOB` | `OPERATOR_API` | `EXPIRATION_HANDLER` | `ASSIGNMENT_HANDLER`)
- `payload_json` (verbatim trigger context)

**Forbidden:** UPDATE on `options_paper_trade.state` without an
accompanying `options_paper_trade_event` row.

---

## 7. Expiration handler (BUILD FIRST)

**File:** `apps/api/src/options/paper/expiration_handler.py` (Phase 11E first deliverable).

### 7.1 Trigger

- Nightly worker job `options_expiration_check.py` runs at 17:30 ET (after market close)
- For each OPEN / EXPIRING trade where `min(expiry across legs) <= today + 7 days`: enter expiration evaluation
- For each OPEN / EXPIRING trade where `min(expiry) == today`: enter expiration finalization

### 7.2 Per-leg classification at expiration

For each leg at expiration day's settlement:

| Condition | Classification | Action |
|---|---|---|
| `right == "C"` AND `underlying_settle ≥ strike + ε` | ITM call | If SELL: assignment risk; if BUY: exercise potential |
| `right == "C"` AND `underlying_settle < strike − ε` | OTM call | Expire worthless |
| `right == "P"` AND `underlying_settle ≤ strike − ε` | ITM put | If SELL: assignment risk; if BUY: exercise potential |
| `right == "P"` AND `underlying_settle > strike + ε` | OTM put | Expire worthless |
| `\|underlying_settle − strike\| ≤ ε` (ε = $0.50) | **PIN RISK** | Flag, do NOT auto-resolve, alert operator |

ε = $0.50 v1 default. Operator-tunable in v2.

### 7.3 Multi-leg payoff at expiration

Per strategy, the payoff function is deterministic given underlying settlement and per-leg ITM/OTM/PIN classification:

**Short put credit spread:**
```
If short_put OTM AND long_put OTM:
    realized_pnl = entry_credit − fees   # max profit
elif short_put ITM AND long_put OTM:
    intrinsic = (strike_short_put − underlying_settle) × 100
    realized_pnl = entry_credit − intrinsic − fees   # partial loss
elif short_put ITM AND long_put ITM (underlying < long_put_strike):
    realized_pnl = entry_credit − (strike_short_put − strike_long_put) × 100 − fees   # max loss
elif PIN on either:
    flag PIN_RISK; do NOT close; alert operator
```

**Short call credit spread:** Mirror with sign flip.

**Iron condor:** Apply put-spread payoff + call-spread payoff independently. PIN on EITHER leg flags the entire trade.

### 7.4 Edge cases

| Edge case | Handling |
|---|---|
| Underlying settlement unavailable at EOD | Defer to next day; flag `EXPIRATION_DATA_MISSING` |
| Multi-day-expiration trade (legs with different expiries — disallowed v1) | Reject at entry; v1 strategies all share single expiry |
| ETF distribution / split on expiration day | Use post-corporate-action strike adjustment per OCC rules; flag for operator review |
| Holiday early close | Use 13:00 ET settlement; recompute expiration day per CBOE calendar |
| Underlying halt / circuit breaker on expiration day | Defer; flag `MARKET_HALT_AT_EXPIRY`; operator manually resolves |
| Cash-settled index option (n/a v1; ETFs only) | n/a |
| Negative underlying price (impossible for ETFs) | n/a |
| ITM short leg + matching long leg both ITM, but in unusual configurations | Apply leg-by-leg payoff; sum; verify against max_loss bound |

---

## 8. Assignment handler

**File:** `apps/api/src/options/paper/assignment_handler.py` (Phase 11E second deliverable).

### 8.1 Early assignment risk monitoring

For SHORT calls + SHORT puts, daily check:

| Condition | Risk level | Action |
|---|---|---|
| Short call AND ex-div within 3 days AND short call ITM AND intrinsic > expected_dividend | **HIGH** | Flag + recommend force-close before ex-div |
| Short put deep ITM (intrinsic > 0.5 × time value remaining) AND DTE ≤ 7 | **MEDIUM** | Flag + recommend force-close |
| All others | LOW | Monitor only |

### 8.2 Ex-dividend data source

Free NASDAQ ex-dividend calendar (or equivalent). Cached locally; refreshed weekly. v2 may upgrade to a paid feed if quality issues surface.

### 8.3 Assignment behavior in paper

Since v1 is paper-only with NO equity ledger linkage:

| Assignment event | Paper-system behavior |
|---|---|
| Short put assigned | Book full intrinsic loss as realized P&L; flag trade `ASSIGNED — long shares would result; manual close required`. NO real share position created. |
| Short call assigned | Book full intrinsic loss as realized P&L; flag trade `ASSIGNED — short shares would result; manual close required`. NO real share position created. |
| Long option exercised by us (rare; manual operator action only v1) | Operator-initiated only via close API; same booking as assignment but with sign flip |

**v1 paper does NOT create synthetic equity positions on assignment.**
The assignment is treated as a P&L finalization event, not a position
transformation. v2 may add equity-position simulation; v1 explicitly
defers this complexity.

### 8.4 Edge cases

| Edge case | Handling |
|---|---|
| Ex-dividend on holiday → ex-div date adjusted | Use NASDAQ official ex-div date; flag if ambiguous |
| Special dividend (e.g. SPY 4x normal) | Operator alert; force-close recommendation |
| Ticker change / merger / delisting affecting underlying | Force-close all positions on affected underlying; flag `CORPORATE_ACTION` |
| Option contract adjustment (split, special div) | Use post-adjustment strike + multiplier; document via event log |

---

## 9. Pin-risk handling

**Definition:** at expiration, underlying settles within ±$0.50 of any short strike.

**Behavior:**
- DO NOT auto-resolve the affected leg(s)
- Flag entire trade as `PIN_RISK`
- Set state to `EXPIRING` with `pin_risk_flagged = true`
- Operator alert via UI + email/Slack hook (v2)
- Operator manually closes via API; closure can use last available bid/ask snapshot at settlement time, not theoretical value
- If operator does not close within 24 hours: auto-realize at settlement-day-close mid (with logged caveat `PIN_RISK_AUTO_REALIZE_AT_MID`)

---

## 10. Risk snapshot (daily)

**Job:** `options_paper_mtm_daily.py` — runs daily at 17:00 ET (after market close, before expiration handler at 17:30 ET).

**For each OPEN trade:**
- Fetch latest chain snapshot for each leg
- Compute current per-leg mid + Greeks
- Store row in `options_risk_snapshot` table:
  - `trade_id`, `as_of_date`, `mid_value_per_leg`, `mid_value_total`
  - per-leg Greeks (delta, gamma, theta, vega, IV)
  - net trade Greeks
  - unrealized_pnl (vs entry credit)
  - days_to_expiry

**For portfolio aggregate (one row per as_of_date):**
- `options_portfolio_risk_snapshot`:
  - `as_of_date`
  - `n_open_trades`
  - `net_delta`, `net_gamma`, `net_theta`, `net_vega`
  - `total_unrealized_pnl`, `total_realized_pnl_to_date`
  - `worst_case_loss_dollars` (sum of remaining max_loss across open trades)
  - `nav_dollars` (paper portfolio notional)
  - `gross_exposure_dollars`

---

## 11. P&L tracking

### 11.1 Realized P&L (per closed trade)

```
realized_pnl_dollars = entry_credit_dollars - exit_debit_dollars - fees_total_dollars
```

For closed-by-expiration trades, `exit_debit_dollars` is the
expiration-payoff cost (intrinsic value of any ITM short leg, capped
at max_loss for spreads).

### 11.2 Unrealized P&L (per OPEN trade, daily)

```
unrealized_pnl_dollars = entry_credit_dollars - current_mid_value_total - estimated_exit_fees
```

Where `current_mid_value_total` is the current sum of per-leg mid prices
times qty times sign (+ for SELL, − for BUY).

### 11.3 Portfolio P&L

```
portfolio_realized_pnl_to_date = sum of realized_pnl_dollars across CLOSED+EXPIRED+ASSIGNED trades
portfolio_unrealized_pnl       = sum of unrealized_pnl_dollars across OPEN trades
portfolio_total_pnl            = portfolio_realized_pnl_to_date + portfolio_unrealized_pnl
```

Stored daily in `options_portfolio_risk_snapshot`.

---

## 12. WebUI

### 12.1 Five read-mostly screens + ONE write action

1. **Positions table** — Ticker / strategy / expiry / DTE / entry credit / current mid / unrealized P&L / net delta / net theta. Sortable. No sparklines.
2. **Vol dashboard** — IVR/IVP per underlying with 52-week range bar. Single page. GREEN (IVR > 50) / YELLOW (30–50) / RED (< 30).
3. **Expiration calendar** — This week's expirations + pin-risk status. Operator checkbox to mark "reviewed."
4. **Strategy screener** — On-demand (not real-time). Returns 5–10 candidate spreads meeting entry criteria. Operator clicks "paper trade" — the only write action in v1.
5. **ML advisory panel** — Sidebar. "Vol regime: HIGH (78% confidence)." "Skew alert: ELEVATED." Labeled `ADVISORY ONLY — not used in trade decisions`.

### 12.2 ONE write action

`POST /api/options/paper-trades` from the screener "paper trade" button. Body: candidate trade payload from the screener. Server validates entry criteria again (defense in depth) and creates the trade in `PROPOSED` → atomically fills to `OPEN`.

### 12.3 Vanity features rejected

- Real-time P&L streaming
- Options flow heat maps
- Dark-pool / unusual-activity overlays
- 3D Greeks surface visualizer
- Real-time gamma exposure charts

All deferred to v2 if operator demand arises.

---

## 13. Risks register

### 13.1 Expiration / assignment bugs (CRITICAL)

**Likelihood:** Medium (most-common failure mode in options paper systems).
**Impact:** All historical P&L corrupted; trust in system collapses.
**Mitigation:** Build expiration_handler + assignment_handler FIRST. End-to-end synthetic test suite covers all §7.4 + §8.4 edge cases before any strategy code ships. Append-only event log allows replay.

### 13.2 Liquidity issues

**Likelihood:** Medium (thin OI on edge strikes).
**Impact:** Paper fills represent unfillable trades.
**Mitigation:** Liquidity floor (OI ≥ 500, spread ≤ $0.10) at strategy_screener. Skip non-conforming strikes.

### 13.3 Stale quotes

**Likelihood:** Low (v1 uses 15-min cadence with 5s freshness gate at fill).
**Impact:** Optimistic fills.
**Mitigation:** `quote_age_seconds ≤ 5` at fill OR reject. Documented as v1 invariant.

### 13.4 IV anomalies

**Likelihood:** Medium (provider data errors, especially deep-OTM strikes).
**Impact:** Greeks computation explodes; strategy screener generates nonsense candidates.
**Mitigation:** Cross-validate ThetaData IV against py_vollib BSM-inversion on a sanity test set; clamp IV to [0.01, 5.0]; reject Greeks if `|delta| > 1.0` or `gamma < 0` or `vega < 0`.

### 13.5 Assignment edge cases

**Likelihood:** Low-Medium (ex-div on dividend ETFs).
**Impact:** Forgotten short call gets assigned; long shares created in real life would have been; in paper, P&L still finalizes correctly but realism diverges.
**Mitigation:** Explicit ex-div monitoring (§8.1); operator alert; force-close recommendation T-1 day. v1 paper never creates synthetic shares (§8.3).

### 13.6 Pin risk

**Likelihood:** Low (statistical rarity at any specific strike, but high-OI strikes attract pinning).
**Impact:** Undefined exposure on expiration day.
**Mitigation:** §9 protocol — flag, do NOT auto-resolve, operator manually closes within 24h or auto-realizes at settlement mid with logged caveat.

### 13.7 Multi-leg leg-out (real broker)

**Likelihood:** N/A v1 (paper assumes atomicity).
**Impact:** Real-broker fills will be worse than paper; v1 paper is optimistic on this dimension.
**Mitigation:** Documented as known v1 model limitation. v2 may add leg-out modeling.

### 13.8 Cross-system contamination with V2

**Likelihood:** Low (architecture forbids).
**Impact:** Options P&L appears in equity dashboards; equity gates read options state.
**Mitigation:** Per `OPTIONS_BOUNDARIES.md` — bidirectional grep CI checks.

---

## 14. Acceptance for paper-trading engine

1. `expiration_handler.py` ships first; passes 100% of §7.4 edge-case test suite
2. `assignment_handler.py` ships second; passes 100% of §8.4 edge-case test suite
3. `lifecycle.py` state machine has unit-test coverage for every transition arrow
4. `fill_simulator.py` produces deterministic fills given chain snapshot + fill_model_version
5. Multi-leg atomicity verified by integration test (all-or-none entry; all-or-none exit)
6. Daily MTM job runs idempotent on `(trade_id, as_of_date)`
7. Portfolio risk snapshot row created daily; not nullable on net Greeks fields when n_open_trades > 0
8. ONLY write API endpoint is `POST /api/options/paper-trades`; all others read-only
9. Pin-risk and assignment flags surface in WebUI within 24h of triggering condition
10. Bidirectional grep boundaries (per `OPTIONS_BOUNDARIES.md`) all pass CI

`STOP. Awaiting operator approval of full Phase 11A doc set.`
