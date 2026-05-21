---
phase: 11A
status: DESIGN ONLY
date: 2026-04-26
locks:
  v1_strategies: [short_put_credit_spread, short_call_credit_spread, iron_condor]
  v1_strategies_build_order: [short_put_credit_spread, short_call_credit_spread, iron_condor]
  underlyings: [SPY, QQQ, IWM, GLD, TLT]
  dte_range: [30, 60]
  short_strike_delta_range: [0.15, 0.30]
  min_open_interest_at_short_strike: 500
  max_bid_ask_spread_dollars: 0.10
  position_size_max_loss_pct_of_portfolio: 0.01
  max_concurrent_positions: 5
  no_naked_options: true
  no_0dte: true
  no_calendar_or_diagonal_v1: true
  no_single_names_v1: true
  no_earnings_plays_v1: true
sources:
  synthesis: ~/.claude-octopus/discover/options-system-research/synthesis.md
  reviewers: [Codex, Gemini, Sonnet, Opus]
  practitioner_evidence: [TastyTrade IVR backtests, OptionAlpha defined-risk research, AQR Israelov/Nielsen]
  academic_evidence: [Bakshi/Cao/Chen 1997 (VRP), Goyal/Saretto 2009, Hull 2017]
---

# Options Strategy Universe — v1

**Status:** Design only. NO source code.
**Decision:** Three defined-risk strategies on five ETFs. Build in order. No naked. No 0DTE.
**Rationale source:** Octo Discover synthesis (2026-04-26).

---

## 1. Strategy summary

| # | Strategy | Direction | Premium | Defined-risk | v1 build order | Use case |
|---:|---|---|---|:-:|:-:|---|
| 1 | Short put credit spread | Bullish / neutral-up | Short | ✓ | **1st** | High IVR, expect underlying flat or up |
| 2 | Short call credit spread | Bearish / neutral-down | Short | ✓ | **2nd** | High IVR, expect underlying flat or down |
| 3 | Iron condor | Neutral (range-bound) | Short | ✓ | **3rd (only after #1+#2 work)** | High IVR, expect underlying range-bound |

**v1 universe restrictions:**
- Underlyings: **SPY, QQQ, IWM, GLD, TLT** only
- DTE at entry: **30–60 days**
- Short strike delta: **0.15–0.30** (≈ 70–85% probability OTM at expiry)
- Min OI at short strike: **500 contracts**
- Max bid/ask spread: **$0.10**
- Max concurrent positions: **5**
- Max loss per position: **1% of paper portfolio NAV**

---

## 2. Per-strategy specifications

### 2.1 Short put credit spread (a.k.a. "bull put spread")

**Build order:** 1st (simplest defined-risk; foundation for all subsequent strategies).

**Legs:**
| Leg | Side | Right | Qty | Strike selection |
|---:|---|---|---:|---|
| 1 | Sell | Put | 1 | Short strike at delta ≈ -0.20 (range -0.30 to -0.15) |
| 2 | Buy | Put | 1 | Long strike 5–10 points below short strike (defines max loss) |

**Net position:**
- Net credit received at entry
- Max profit = net credit
- Max loss = (short_strike − long_strike) × 100 − net_credit_per_contract
- Breakeven = short_strike − (net_credit / 100)

**Entry criteria (all must hold):**
- IVR ≥ 50 (high-IV environment)
- Underlying within 1 standard deviation of 30-day mean
- Short strike OI ≥ 500
- Short strike bid/ask spread ≤ $0.10
- Long strike OI ≥ 100
- 30 ≤ DTE ≤ 60
- Net credit ≥ 30% of spread width (e.g. $0.30 credit on $1 wide spread)
- Position max-loss ≤ 1% of paper portfolio NAV

**Exit criteria (any triggers close):**
- Profit target: 50% of max profit captured (close at 0.50 × net_credit remaining)
- Loss limit: -100% of net credit (close when current debit = 2× initial credit)
- Time: T-21 DTE (close when ≤ 21 days remain to avoid gamma acceleration)
- Force-close: short leg becomes ITM AND DTE ≤ 7 (prevents assignment / pin risk)

**Greeks at entry (typical):**
- Net delta: +0.05 to +0.15 (long-bias)
- Net gamma: small negative
- Net theta: positive (time decay benefits short)
- Net vega: negative (volatility expansion hurts)

**Risks specific to this strategy:**
- Sharp underlying drop within first 14 DTE → vega + delta both hurt
- Early assignment if short put goes deep ITM → operator alert + force-close logic

---

### 2.2 Short call credit spread (a.k.a. "bear call spread")

**Build order:** 2nd. Mirror of #1.

**Legs:**
| Leg | Side | Right | Qty | Strike selection |
|---:|---|---|---:|---|
| 1 | Sell | Call | 1 | Short strike at delta ≈ +0.20 (range +0.15 to +0.30) |
| 2 | Buy | Call | 1 | Long strike 5–10 points above short strike |

**Net position:**
- Net credit received at entry
- Max profit = net credit
- Max loss = (long_strike − short_strike) × 100 − net_credit_per_contract
- Breakeven = short_strike + (net_credit / 100)

**Entry criteria:** Mirror of §2.1 with sign flips. Plus:
- Underlying NOT in strong uptrend (operator-defined: e.g. 30d realized return < +5%)
- For dividend-paying underlyings (e.g. SPY): short strike NOT ITM during ex-div week (avoid early exercise)

**Exit criteria:** Mirror of §2.1.

**Greeks at entry (typical):**
- Net delta: -0.05 to -0.15 (short-bias)
- Net gamma: small negative
- Net theta: positive
- Net vega: negative

**Risks specific to this strategy:**
- Underlying gap-up within first 14 DTE
- **Early assignment risk on short call if ex-dividend within 3 days AND short call is ITM AND intrinsic value < expected dividend** (see `OPTIONS_PAPER_TRADING_DESIGN.md` §Assignment handler)

---

### 2.3 Iron condor

**Build order:** 3rd. **Only after #1 and #2 are working end-to-end with full lifecycle (entry → MTM → expiration / assignment / close).**

**Legs (4 total):**
| Leg | Side | Right | Qty | Strike selection |
|---:|---|---|---:|---|
| 1 | Sell | Put | 1 | Short put strike at delta ≈ -0.20 |
| 2 | Buy | Put | 1 | Long put strike 5–10 below short put strike |
| 3 | Sell | Call | 1 | Short call strike at delta ≈ +0.20 |
| 4 | Buy | Call | 1 | Long call strike 5–10 above short call strike |

**Net position:**
- Net credit = put-spread credit + call-spread credit
- Max profit = net credit
- Max loss = MAX(put_spread_width, call_spread_width) × 100 − net_credit_per_contract
- Breakevens: lower = put_short_strike − (net_credit / 100); upper = call_short_strike + (net_credit / 100)

**Entry criteria (all must hold):**
- All criteria from §2.1 AND §2.2
- Both short legs at delta ≈ ±0.20 (symmetric)
- Both spread widths equal (e.g. both $5 wide)
- Underlying within 0.5σ of 30-day mean (true neutral)

**Exit criteria:**
- Profit target: 50% of max profit
- Loss limit: -100% of net credit
- Time: T-21 DTE
- **Side-specific force-close:** if EITHER short leg becomes ITM, close affected side independently (managed condor) — flag for operator
- Force-close entire position: T-7 DTE if either short leg ITM (pin risk)

**Greeks at entry (typical):**
- Net delta: ≈ 0 (truly neutral)
- Net gamma: small negative (peaks near short strikes)
- Net theta: positive (largest of the three strategies)
- Net vega: negative (largest of the three)

**Risks specific to this strategy:**
- Doubles the legs → 4× the assignment / expiration / fee complexity
- Both sides can lose simultaneously in vol-expansion regimes
- Pin risk on EITHER short leg
- 4 contracts × commission = highest per-trade cost

---

## 3. Universe constraints + rationale

### 3.1 Underlyings: SPY, QQQ, IWM, GLD, TLT

Five most-liquid ETF options globally:

| Underlying | Avg bid/ask spread on ATM front-month | Avg daily option volume | Why included |
|---|---|---|---|
| SPY | $0.01 | 5M+ contracts | Index proxy; deepest liquidity |
| QQQ | $0.01 | 2M+ contracts | NDX proxy; tech beta |
| IWM | $0.01 | 1M+ contracts | Small-cap; uncorrelated with SPY/QQQ |
| GLD | $0.01–0.02 | 200K+ contracts | Gold; uncorrelated risk-off proxy |
| TLT | $0.01–0.02 | 500K+ contracts | Long-duration treasuries; rates / inflation play |

**Excluded v1:**
- Single names (AAPL, NVDA, etc.): higher spreads, ex-div + earnings complications
- Sector ETFs (XLE, XLF): smaller volume; spread risk
- VIX / VXX / UVXY: contango / mean-reversion structure makes vol strategies non-comparable to underlying-equity strategies
- Levered ETFs (TQQQ, SQQQ): decay structure breaks IVR/IVP interpretation
- Crypto-related (IBIT, BITO): nascent option markets, wide spreads

### 3.2 DTE 30–60 (no weeklies, no 0DTE, no LEAPS)

- **0DTE excluded:** gamma risk non-linear; cannot be modeled with EOD or 15-min-snapshot data; pin risk extreme; not appropriate for v1's snapshot cadence
- **Weeklies (< 30 DTE) excluded:** gamma acceleration in last 21 DTE creates large MTM swings; force-close at T-21 DTE is the v1 discipline
- **LEAPS (> 60 DTE) excluded:** vega-dominant; theta-collection thesis weakened; capital efficiency lower
- **30–60 DTE sweet spot:** TastyTrade's 10-year backtest series identifies 45 DTE as the empirical optimum for short-premium

### 3.3 Short strike delta 0.15–0.30

- Lower delta (more OTM): higher win rate but lower credit, longer to recovery on adverse moves
- Higher delta (closer to ATM): higher credit but lower win rate, more pin risk
- **0.15–0.30** = TastyTrade convention; matches their "1 standard deviation" heuristic

### 3.4 Min OI 500 + max spread $0.10

- OI 500 ensures strike is liquid enough for fair-value mid pricing
- Spread $0.10 ensures fill model (mid + 25% × spread) doesn't blow up
- For ETFs in §3.1, both criteria are easily met for ATM ± 2σ strikes; tighter universe avoids backtest fictions

### 3.5 Max 5 concurrent positions, 1% NAV max-loss per position

- Position-size cap: 1% × NAV × (max_loss_per_contract / 100) → bounds total drawdown to 5% in worst case (all 5 positions max-loss simultaneously)
- Leaves 95% NAV in cash buffer (paper portfolio is conceptual; v1 doesn't allocate real capital)

---

## 4. Forbidden v1 strategies

### 4.1 Naked short calls / puts — FORBIDDEN

Undefined risk on short calls; far-OTM put → near-infinite loss tail. The single most common cause of options blow-ups (LJM 2018, Optionsellers 2018). Forbidden indefinitely; v2 reconsideration requires a separate design + explicit operator approval.

### 4.2 0DTE — FORBIDDEN

Gamma risk non-linear; pin risk extreme; cannot be modeled with v1's 15-min snapshot cadence. Hard constant `MIN_DTE = 21` enforced at strategy_screener.

### 4.3 Calendar / diagonal spreads — DEFERRED to v2

Roll mechanics (closing front month, rolling to back) add lifecycle complexity. Time-spread theta dynamics require modeling vol changes across expiries. Deferred until v1 is operational.

### 4.4 Earnings plays — DEFERRED

IV crush dynamics; pre-/post-earnings vega timing. Requires earnings calendar integration + IV crush model. Deferred to v2.

### 4.5 Single-stock options — DEFERRED

Higher spreads, dividend complications, earnings windows, takeover risk. v1 ETFs only.

### 4.6 Variance / VIX options — DEFERRED

Non-equity-style payoffs; VRO settlement (VIX options); contango / backwardation regime dynamics. Defer indefinitely.

### 4.7 Anything sharing state with V2 promotion-trigger framework — FORBIDDEN

Schema, settings, code, UI all separated. See `OPTIONS_BOUNDARIES.md`.

---

## 5. Strategy selector logic (v1)

**Rule-based ONLY.** No ML in selection path.

```
For each underlying in {SPY, QQQ, IWM, GLD, TLT}:
    1. Compute current IVR, IVP, term structure slope (nightly)
    2. If IVR < 50: skip (insufficient premium for short-premium strategies)
    3. If IVR ≥ 50:
        a. If 30d underlying drift > +3%: candidate = short_put_credit_spread (bullish)
        b. If 30d underlying drift < -3%: candidate = short_call_credit_spread (bearish)
        c. If |30d underlying drift| ≤ 3% AND iron_condor_enabled:
                candidate = iron_condor (neutral)
    4. Generate candidate per §2.1 / §2.2 / §2.3 entry criteria
    5. Surface in WebUI screener for operator selection (manual click)
```

**No automatic execution.** Screener proposes; operator clicks.

**ML advisory output** (vol regime classifier, skew alert) appears in
sidebar — labeled `ADVISORY ONLY` — never alters the rule-based
selector.

---

## 6. Acceptance for strategy universe

1. Each strategy implementation (Phase 11E) implements:
   - `entry_criteria(features, chain) → list[Candidate]`
   - `entry_legs(candidate) → list[Leg]`
   - `exit_criteria(position) → bool`
   - `max_loss(legs)` / `max_profit(legs)` / `breakeven(legs)`
2. All four functions are pure (no DB, no I/O)
3. Unit tests cover entry-criteria pass/fail at boundaries (IVR=49 vs 50, OI=499 vs 500, spread=$0.11 vs $0.10, DTE=29 vs 30 vs 60 vs 61)
4. Iron condor is gated on flag `IRON_CONDOR_ENABLED` (default false v1; true after #1+#2 ship)
5. Operator-approval discipline: operator clicks "paper trade" on a candidate; never auto-creates a paper trade

`STOP. Awaiting operator approval of full Phase 11A doc set.`
