"""Yahoo historical backfill — yfinance-based, lower confidence.

yfinance's `.news` only returns CURRENT news; we flag and use it only when
the caller explicitly tolerates the staleness risk. For earnings, yfinance
exposes `get_earnings_dates(limit=...)` which DOES return historical dates
but without proper `known_at` — flagged accordingly.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from loguru import logger

from apps.api.src.data.catalysts.backfill.base import (
    BackfillProvider, BackfillProviderError, EarningsRecord,
    NewsRecord, ProviderFetchResult,
)


class YahooBackfillProvider:
    name = "yahoo"

    def fetch(
        self, symbol: str, *, start: dt.date, end: dt.date,
    ) -> ProviderFetchResult:
        try:
            import yfinance as yf  # noqa: F401
        except ImportError as e:
            raise BackfillProviderError("yfinance not installed") from e
        out = ProviderFetchResult()
        # Yahoo news via yfinance is present-time only — skip for historical
        # backfill to avoid poisoning the news table with wrong timestamps.
        out.warnings.append(
            "yahoo: skipping news fetch (yfinance returns current-day "
            "news regardless of range)"
        )
        out.earnings = self._fetch_earnings(symbol, start=start, end=end)
        return out

    # ------------------------------------------------------------------
    def _fetch_earnings(
        self, symbol: str, *, start: dt.date, end: dt.date,
    ) -> list[EarningsRecord]:
        try:
            import yfinance as yf
            tkr = yf.Ticker(symbol)
            df = tkr.get_earnings_dates(limit=48) \
                 if hasattr(tkr, "get_earnings_dates") else None
        except Exception as e:
            logger.debug("yahoo earnings crash: {}", e)
            return []
        if df is None or getattr(df, "empty", True):
            return []
        out: list[EarningsRecord] = []
        for idx, row in df.iterrows():
            try:
                d = idx.date() if hasattr(idx, "date") else idx
            except Exception:
                continue
            if d < start or d > end:
                continue
            out.append(EarningsRecord(
                symbol=symbol.upper(),
                provider=self.name,
                event_date=d,
                event_time_hint=None,
                known_at=None,       # yfinance does not expose
                fiscal_period=None,
                fiscal_year=None,
                eps_estimate=_f(row.get("EPS Estimate")),
                eps_actual=_f(row.get("Reported EPS")),
                revenue_estimate=None,
                revenue_actual=None,
                source="yahoo",
                raw_payload=None,
            ))
        return out


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        import math
        x = float(v)
        if math.isnan(x):
            return None
        return x
    except (TypeError, ValueError):
        return None
