"""Phase E — Options Journal (strategist memory) package.

Unified timeline read across:
  * options_shadow_decision_log     — "AI saw setup"
  * options_strategy_candidate      — "AI interpreted setup"
  * options_paper_trade             — "trade proposed / filled / closed"
  * options_trade_lifecycle_event   — "lifecycle progressed"
  * options_assignment_event        — "assigned"
  * options_expiration_event        — "expired"

Plus per-trade thesis-evolution timeline.

Read-only. No new state. No execution coupling.
"""
