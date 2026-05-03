"""Dedupe key helpers — deterministic short strings for UPSERT.

Kept short (<80 chars) to fit the `dedupe_key` column.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re


_WS = re.compile(r"\s+")


def _normalize_title(title: str) -> str:
    t = (title or "").strip().lower()
    t = _WS.sub(" ", t)
    return t[:200]


def _short_hash(s: str, n: int = 40) -> str:
    return hashlib.sha1(s.encode("utf-8"), usedforsecurity=False).hexdigest()[:n]


def news_dedupe_key(
    *, symbol: str, provider: str,
    url: str | None,
    title: str,
    published_at: dt.datetime,
) -> str:
    """Stable dedupe key: symbol|provider|url_hash|day_bucket|title_hash."""
    url_part = _short_hash(url or "no-url", 12)
    day = published_at.astimezone(dt.timezone.utc).date().isoformat()
    title_part = _short_hash(_normalize_title(title), 16)
    return f"{symbol.upper()}|{provider}|{url_part}|{day}|{title_part}"[:80]


def earnings_dedupe_key(
    *, symbol: str, provider: str,
    event_date: dt.date,
    fiscal_period: str | None = None,
) -> str:
    fp = (fiscal_period or "na").replace(" ", "")[:6]
    return f"{symbol.upper()}|{provider}|{event_date.isoformat()}|{fp}"[:80]
