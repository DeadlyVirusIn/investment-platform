"""Governance layer — observation + recommendation only.

These modules NEVER mutate trading state, never enable ML execution,
never modify risk parameters, never delete trades. They compute state
machines from observed data and emit recommendations + flags consumed
by Ops UI / nightly job logs.

Hard contract:
  • read-only against paper_trade_log + ml_*  + decision_log
  • no writes to engine config, hybrid mode, or scheduler
  • no auto-promotion
  • all outputs are advisory; operator decides
"""
