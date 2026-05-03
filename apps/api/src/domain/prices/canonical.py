"""Canonical bar model shared across providers."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RawProviderBar:
    """Provider-returned bar before normalization. Dates are strings per the
    provider's native format. Numeric fields are Decimal or None."""
    symbol: str
    date_iso: str                     # "YYYY-MM-DD" or full ISO
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    adjusted_close: Decimal | None
    volume: int | None


@dataclass
class CanonicalBar:
    """Internal canonical shape. All bars fed to validation/upsert use this."""
    symbol: str
    trade_date: dt.date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal | None
    volume: int | None
    source: str                       # provider name: "tiingo", "yahoo", ...
    fetched_at: dt.datetime


# Provider priority (higher = preferred). Used in reconcile + upsert policy.
SOURCE_PRIORITY: dict[str, int] = {
    "tiingo": 100,
    "yahoo": 50,
    "demo": 10,
    "test": 5,
}


def source_priority(name: str) -> int:
    return SOURCE_PRIORITY.get(name, 0)
