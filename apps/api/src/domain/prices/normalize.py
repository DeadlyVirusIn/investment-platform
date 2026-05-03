"""Raw → canonical normalization. Pure functions."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.prices.canonical import CanonicalBar, RawProviderBar


def parse_date(date_iso: str) -> dt.date | None:
    """Accept YYYY-MM-DD or a full ISO timestamp; return the date portion."""
    if not date_iso:
        return None
    try:
        if "T" in date_iso or " " in date_iso:
            sep = "T" if "T" in date_iso else " "
            date_only = date_iso.split(sep, 1)[0]
        else:
            date_only = date_iso[:10]
        return dt.date.fromisoformat(date_only)
    except ValueError:
        return None


def to_canonical(
    raw: RawProviderBar,
    *,
    source: str,
    fetched_at: dt.datetime | None = None,
) -> CanonicalBar | None:
    """Best-effort RawProviderBar → CanonicalBar.

    Returns None when a hard field is missing and cannot be constructed
    (missing date, missing any of OHLC). Validation layer will also guard;
    this function is a conservative first filter.
    """
    date = parse_date(raw.date_iso)
    if date is None:
        return None
    if (
        raw.open is None
        or raw.high is None
        or raw.low is None
        or raw.close is None
    ):
        return None
    return CanonicalBar(
        symbol=raw.symbol.upper(),
        trade_date=date,
        open=raw.open,
        high=raw.high,
        low=raw.low,
        close=raw.close,
        adjusted_close=raw.adjusted_close,
        volume=raw.volume,
        source=source,
        fetched_at=fetched_at or dt.datetime.now(dt.timezone.utc),
    )


def normalize_batch(
    raws: list[RawProviderBar],
    *,
    source: str,
    fetched_at: dt.datetime | None = None,
) -> tuple[list[CanonicalBar], int]:
    """Normalize a list; returns (canonical_bars, dropped_count)."""
    out: list[CanonicalBar] = []
    dropped = 0
    for r in raws:
        c = to_canonical(r, source=source, fetched_at=fetched_at)
        if c is None:
            dropped += 1
        else:
            out.append(c)
    return out, dropped
