"""Phase C — Position Intelligence package.

AI trade management. Reads from options_paper_trade +
options_paper_trade_leg + options_chain_snapshot +
options_trade_lifecycle_event + market_event_calendar to compute
per-position intelligence: thesis health, theta impact, IV impact,
breakeven distance, profit-zone status, catalyst exposure, exit/
hold/roll guidance.

Read-only. No execution coupling. Honest empty state when 0 open
positions.
"""
