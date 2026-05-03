"""Catalyst providers — pluggable HTTP adapters.

Keys to implement:
  - fetch_next_event(symbol) -> UpcomingEvent | None
  - fetch_recent_headlines(symbol, limit) -> list[Headline]

Raise `ProviderError` (from reliability.chain) on any failure so the chain
can fall through.
"""
