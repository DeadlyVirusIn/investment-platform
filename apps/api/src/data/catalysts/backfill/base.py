"""Backfill provider contract + shared types.

Each provider returns NewsRecord / EarningsRecord objects. Raises
BackfillProviderError on any failure so the service can fall through to the
next provider in priority without crashing.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol, Any


class BackfillProviderError(Exception):
    """Provider totally failed (auth, network, malformed, rate-limited)."""


@dataclass(frozen=True)
class NewsRecord:
    symbol: str
    source: str                  # article publisher (e.g. "Reuters")
    provider: str                # data fetcher (finnhub/yahoo/…)
    title: str
    url: str
    published_at: dt.datetime    # TZ-aware, authoritative upstream time
    summary: str | None = None
    category: str | None = None
    sentiment: float | None = None   # -1..+1 if upstream supplies
    raw_payload: dict[str, Any] | None = None

    def validate(self) -> None:
        if not self.title:
            raise BackfillProviderError("NewsRecord missing title")
        if not self.url:
            raise BackfillProviderError("NewsRecord missing url")
        if self.published_at.tzinfo is None:
            raise BackfillProviderError(
                "NewsRecord.published_at must be timezone-aware"
            )


@dataclass(frozen=True)
class EarningsRecord:
    symbol: str
    provider: str
    event_date: dt.date
    event_time_hint: str | None = None   # bmo|amc|intraday|unknown
    known_at: dt.datetime | None = None  # when market could know
    fiscal_period: str | None = None     # Q1 | FY
    fiscal_year: int | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_actual: float | None = None
    source: str | None = None
    raw_payload: dict[str, Any] | None = None

    def validate(self) -> None:
        if not self.symbol:
            raise BackfillProviderError("EarningsRecord missing symbol")
        if self.event_date is None:
            raise BackfillProviderError("EarningsRecord missing event_date")
        if self.known_at is not None and self.known_at.tzinfo is None:
            raise BackfillProviderError(
                "EarningsRecord.known_at must be timezone-aware"
            )


@dataclass
class ProviderFetchResult:
    news: list[NewsRecord] = field(default_factory=list)
    earnings: list[EarningsRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BackfillProvider(Protocol):
    """A historical catalyst source (news + earnings)."""

    name: str

    def fetch(
        self, symbol: str, *,
        start: dt.date, end: dt.date,
    ) -> ProviderFetchResult:
        ...
