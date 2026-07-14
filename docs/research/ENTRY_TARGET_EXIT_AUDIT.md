# Entry / Target / Exit — Backend Data Audit & Implementation (Sprint L)

Date: 2026-06-18
Branch: `mvp/ideas-you-can-follow`

## Purpose

Sprint K added a beginner "Plan" block (Entry / Target / Exit if wrong /
Timeframe) to stock idea cards. This audit records **what backend data
actually exists** to back those numbers, which implementation option we
chose, and what is honest placeholder vs real engine-derived — so nobody
later mistakes the planning zones for an engine target/stop engine.

## What was traced

Ground truth = the live recommendation payload
(`GET /recommendations?latest=true`) inspected on the running dev stack,
plus the recommendation/evidence schema.

| Candidate field | Exists? | Where |
|---|---|---|
| current price | **Yes (derived)** | `evidence[price_vs_sma_long].narrative` → `"Price 357.03 vs long SMA 306.73 (16.40%)"` |
| ATR | **Yes (as %)** | `evidence[atr_pct_14].value` → `0.0327` (ATR ÷ price) |
| recent support/resistance | **Partial** | `evidence[sma_20_vs_50].narrative` → `"SMA(20)=328.64 vs SMA(50)=310.17"` (SMA50 used as a support proxy) |
| stop-loss logic (per-rec) | **No** | not in rec payload; only the paper-exit *cycle* has policy (see below) |
| target / exit price logic | **No** | engine emits an action (Buy/Hold/Trim), not price levels |
| recommendation horizon | **No** | no per-rec horizon field; engine is a swing design (weeks–months) |
| risk score | **Yes** | `family_scores.volatility_risk`, `evidence[max_drawdown]`, `evidence[atr_pct_14]` |
| volatility score | **Yes** | `family_scores.volatility_risk` |

Other real evidence factors present: `trend_strength`, `rsi_14`,
`beta_vs_spy` (None in engine v1), `portfolio_weight`.

### Strategy / paper-exit logic (separate subsystem)

A paper **exit cycle** exists server-side (`run_paper_exit_cycle`,
TP/SL/max-hold rules) but it operates on *open paper positions*, not on a
recommendation pre-trade. It does **not** expose a per-recommendation
target/stop price, so it cannot drive a card's Plan today.

## Decision: Option B (compute from price + ATR), honest fallback = Option C

- **Option A (expose existing stop/target):** rejected — no per-rec
  target/stop price exists to expose.
- **Option B (compute from ATR + price):** **chosen.** Both current price
  and ATR% are real, already computed, and defensible. We derive
  conservative *paper-planning* zones and label them an estimate.
- **Option C (honest placeholders):** used as the fallback whenever price
  or ATR is missing, and for non-Buy actions (Hold/Trim/Sell) where a buy
  plan doesn't apply.

## Formula (implemented in `apps/web/src/v2/lib/ideaPlan.ts`)

```
atr      = price * atr_pct_14
entry    = [price − 0.5·atr , price + 0.5·atr]      # don't chase gaps
exit     = price − 2·atr   (or "below SMA50 support" when SMA50 < price)
target   = price + 3·atr   # 1.5R against the 2·ATR risk
timeframe = "Medium-term: weeks to months."         # swing design horizon
```

Rationale:
- ±0.5·ATR entry band ≈ "near today's price," discourages chasing.
- 2·ATR stop = standard volatility-normalised risk unit; survives normal noise.
- 3·ATR target = 1.5 reward:risk, conservative and not over-promising.

Every computed Plan is rendered with the disclaimer:
> "Paper planning estimate from price + volatility (ATR) — not investment
> advice. Practice it in paper first."

## What is real vs placeholder

- **Real engine-derived inputs:** current price, ATR%, SMA50 (all from
  `rec.evidence`, computed by the engine from market bars).
- **Heuristic (ours, not the engine's):** the 0.5/2/3·ATR multiples and the
  1.5R target. These are *display heuristics*, clearly labelled as planning
  estimates — they are **not** an engine-optimised target/stop.
- **Honest placeholder:** shown when evidence lacks price/ATR, or action ≠ Buy.

## TODO — future engine-native levels

When the engine grows true level logic, replace the frontend heuristic:

- [ ] `recommendation.entry_zone_low / entry_zone_high`
- [ ] `recommendation.stop_price` (engine risk model, not 2·ATR proxy)
- [ ] `recommendation.target_price` (engine, with method tag)
- [ ] `recommendation.horizon_days` (per-name, replaces the global swing label)
- [ ] structured `support_level` / `resistance_level` (instead of parsing
      SMA narratives)

Until then, `ideaPlan()` is the single source of truth and stays explicitly
labelled an estimate.
