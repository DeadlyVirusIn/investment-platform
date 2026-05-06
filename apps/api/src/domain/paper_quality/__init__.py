"""Pre-ML diagnostic scoring for paper trades. Read-only.

This package never writes to any table and never participates in
trade execution decisions. It scores existing rows in
`paper_trade` / `paper_position` / `paper_equity_snapshot` /
`price_bar` to surface a transparent, deterministic quality
metric that a human operator can review.
"""
