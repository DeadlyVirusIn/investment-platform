"""Options Strategy Observatory (Phase 11G).

Read-only observation layer over the options paper-trading stack.

NEVER recommends, ranks as "best", auto-creates trades, or influences
live trading. NEVER imports V2 / equity / governance / ML / execution
modules. NEVER writes to any DB table.

Provides:
  * Frozen v1 rule registry (eligibility criteria + human-readable
    explanations for each defined-risk strategy)
  * Pure-fn eligibility evaluator returning per-criterion pass/fail +
    reason text
  * Aggregations over paper trades (performance summary), chain rows
    + feature rows + lifecycle events (diagnostics), and a single
    (symbol, as_of_date) replay snapshot
"""
