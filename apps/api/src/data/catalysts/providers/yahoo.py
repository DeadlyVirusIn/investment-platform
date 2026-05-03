"""Yahoo Finance adapter — free, no key, rate-limit-tolerant.

Uses yfinance library already in deps. Earnings via `.get_earnings_dates()`;
news via `.news` attribute.

yfinance is chatty and occasionally raises IndexError / JSONDecodeError on
missing data — we translate them to ProviderError so the chain can recover.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from loguru import logger

from apps.api.src.data.catalysts.types import Headline, UpcomingEvent
from apps.api.src.data.reliability.chain import MissingData, ProviderError


class YahooProvider:
    name = "yahoo"

    def fetch_next_event(self, symbol: str) -> UpcomingEvent | None:
        try:
            import yfinance as yf
        except ImportError as e:
            raise ProviderError("yfinance not installed") from e
        try:
            tkr = yf.Ticker(symbol)
            # Prefer calendar (upcoming confirmed)
            cal = getattr(tkr, "calendar", None)
            next_date = _extract_earnings_date(cal)
            if next_date:
                return UpcomingEvent(
                    kind="earnings",
                    date=next_date,
                    title=f"{symbol} earnings",
                    confirmed=True,
                )
            # Fallback: earnings_dates DataFrame
            df = tkr.get_earnings_dates(limit=4) \
                 if hasattr(tkr, "get_earnings_dates") else None
            if df is None or getattr(df, "empty", True):
                raise MissingData(f"no earnings schedule for {symbol}")
            today = dt.date.today()
            for idx in df.index:
                try:
                    d = idx.date() if hasattr(idx, "date") else idx
                except Exception:
                    continue
                if d >= today:
                    return UpcomingEvent(
                        kind="earnings", date=d,
                        title=f"{symbol} earnings",
                        confirmed=False,
                    )
            raise MissingData(f"all earnings dates in past for {symbol}")
        except MissingData:
            raise
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"yahoo earnings crash: {type(e).__name__}") from e

    def fetch_recent_headlines(
        self, symbol: str, *, limit: int = 3,
    ) -> list[Headline]:
        try:
            import yfinance as yf
        except ImportError as e:
            raise ProviderError("yfinance not installed") from e
        try:
            items = yf.Ticker(symbol).news or []
        except Exception as e:
            raise ProviderError(f"yahoo news crash: {type(e).__name__}") from e
        if not items:
            raise MissingData(f"no news for {symbol}")
        out: list[Headline] = []
        for it in items[:limit * 2]:
            try:
                ts = it.get("providerPublishTime")
                pub = dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc) \
                      if ts else None
                title = str(it.get("title") or "").strip()
                if not title:
                    continue
                out.append(Headline(
                    title=title,
                    source=str(it.get("publisher") or "yahoo"),
                    url=it.get("link"),
                    published_at=pub,
                    sentiment=None,
                    relevance=None,
                ))
            except Exception as e:
                logger.debug("yahoo: skipped malformed news row: {}", e)
                continue
            if len(out) >= limit:
                break
        if not out:
            raise MissingData(f"{symbol} news all malformed")
        return out


def _extract_earnings_date(calendar: Any) -> dt.date | None:
    """Calendar is a dict or DataFrame depending on yfinance version."""
    if calendar is None:
        return None
    if isinstance(calendar, dict):
        raw = calendar.get("Earnings Date") or calendar.get("earningsDate")
        if isinstance(raw, list) and raw:
            val = raw[0]
        else:
            val = raw
        if val is None:
            return None
        if isinstance(val, dt.datetime):
            return val.date()
        if isinstance(val, dt.date):
            return val
        try:
            return dt.date.fromisoformat(str(val)[:10])
        except ValueError:
            return None
    # DataFrame shape
    try:
        val = calendar.loc["Earnings Date"][0]
        if hasattr(val, "date"):
            return val.date()
        return dt.date.fromisoformat(str(val)[:10])
    except Exception:
        return None
