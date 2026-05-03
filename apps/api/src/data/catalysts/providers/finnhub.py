"""Finnhub adapter — free tier: 60 req/min, earnings + company news.

Endpoints used:
  /calendar/earnings?symbol=AAPL&from=YYYY-MM-DD&to=YYYY-MM-DD
  /company-news?symbol=AAPL&from=YYYY-MM-DD&to=YYYY-MM-DD

If `FINNHUB_API_KEY` is empty, raises ProviderError on every call — the
fallback chain handles this gracefully by moving to the next provider.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
from loguru import logger

from apps.api.src.data.catalysts.types import Headline, UpcomingEvent
from apps.api.src.data.reliability.chain import (
    MissingData, ProviderError,
)

BASE_URL = "https://finnhub.io/api/v1"
TIMEOUT_SECS = 6.0


class FinnhubProvider:
    name = "finnhub"

    def __init__(self, api_key: str):
        self._api_key = api_key or ""

    # --------- internal ---------

    def _require_key(self) -> str:
        if not self._api_key:
            raise ProviderError("FINNHUB_API_KEY not configured")
        return self._api_key

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        key = self._require_key()
        params = {**params, "token": key}
        try:
            with httpx.Client(timeout=TIMEOUT_SECS) as client:
                r = client.get(f"{BASE_URL}{path}", params=params)
        except httpx.HTTPError as e:
            raise ProviderError(f"finnhub HTTP {type(e).__name__}") from e
        if r.status_code == 429:
            raise ProviderError("finnhub rate limited (429)")
        if r.status_code >= 400:
            raise ProviderError(f"finnhub {r.status_code}")
        try:
            return r.json()
        except ValueError as e:
            raise ProviderError(f"finnhub bad JSON: {e}") from e

    # --------- public ---------

    def fetch_next_event(self, symbol: str) -> UpcomingEvent | None:
        today = dt.date.today()
        horizon = today + dt.timedelta(days=60)
        payload = self._get("/calendar/earnings", {
            "symbol": symbol,
            "from": today.isoformat(),
            "to": horizon.isoformat(),
        })
        rows = (payload or {}).get("earningsCalendar") or []
        if not rows:
            raise MissingData(f"no earnings found for {symbol}")
        # First upcoming (Finnhub returns ascending)
        row = sorted(rows, key=lambda r: r.get("date", ""))[0]
        date_str = row.get("date")
        if not date_str:
            raise MissingData("earnings row missing date")
        try:
            ev_date = dt.date.fromisoformat(date_str)
        except ValueError as e:
            raise MissingData(f"bad date: {date_str}") from e
        return UpcomingEvent(
            kind="earnings",
            date=ev_date,
            title=f"{symbol} earnings",
            confirmed=row.get("epsEstimate") is not None,
        )

    def fetch_recent_headlines(
        self, symbol: str, *, limit: int = 3,
    ) -> list[Headline]:
        today = dt.date.today()
        from_date = today - dt.timedelta(days=3)
        payload = self._get("/company-news", {
            "symbol": symbol,
            "from": from_date.isoformat(),
            "to": today.isoformat(),
        })
        if not isinstance(payload, list) or not payload:
            raise MissingData(f"no news for {symbol}")
        # Sort newest first
        rows = sorted(
            payload,
            key=lambda r: r.get("datetime", 0),
            reverse=True,
        )[:limit]
        out: list[Headline] = []
        for r in rows:
            try:
                ts_raw = r.get("datetime")
                pub = dt.datetime.fromtimestamp(int(ts_raw), tz=dt.timezone.utc) \
                      if ts_raw else None
                out.append(Headline(
                    title=str(r.get("headline") or "").strip(),
                    source=str(r.get("source") or "finnhub"),
                    url=r.get("url"),
                    published_at=pub,
                    sentiment=None,    # free tier omits sentiment
                    relevance=None,
                ))
            except Exception as e:
                logger.debug("finnhub: skipped malformed row: {}", e)
                continue
        if not out:
            raise MissingData("all news rows malformed")
        return out
