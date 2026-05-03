"""Daily-price provider protocol + shared errors."""

from __future__ import annotations

import datetime as dt
from typing import Protocol

from apps.api.src.domain.prices.canonical import RawProviderBar


class ProviderError(Exception):
    """Generic provider failure (HTTP error, auth failure, parse error)."""


class NoDataError(ProviderError):
    """Provider returned no bars for the requested window. Distinct from
    outright failure — caller may choose to fall back without retry."""


class DailyPriceProvider(Protocol):
    name: str
    priority: int

    async def fetch_daily_bars(
        self,
        symbol: str,
        start_date: dt.date,
        end_date: dt.date,
    ) -> list[RawProviderBar]:
        ...
