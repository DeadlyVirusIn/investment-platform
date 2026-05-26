"""Phase B — Options Opportunities API package.

Composes the canonical opportunity-card payload from:
  * options_shadow_decision_log (would_trade signals + gate passes)
  * options_strategy_bias (Bull/Bear/Neutral/Event/Developing taxonomy)
  * options_feature_daily (IV-rank / vol-regime context)
  * options_chain_snapshot (current mid + greeks for the option leg)
  * event_calendar (earnings / catalyst proximity, when present)

Read-only. Joins only. No mutation. Identity is preserved by the
underlying tables; this module purely ranks + projects.
"""
