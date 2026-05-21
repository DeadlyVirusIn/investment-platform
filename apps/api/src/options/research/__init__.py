"""Phase D — AI conviction layer (Research).

Per-underlying read of:
  * AI posture (bias mix from options_strategy_candidate)
  * Volatility regime (iv_rank_252d + atm_iv + vrp_30d tier)
  * Strategy-family fit (composite_score rank by bias)
  * Catalyst timeline (market_event_calendar next 90d)
  * Expected move (atm_iv * spot * sqrt(DTE/365))
  * Top opportunities + open positions linkage

Read-only. Reuses Phase B + B7 + C data. No new state. No
execution coupling.
"""
