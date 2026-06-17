"""Polygon daily-bar provider (paid Massive/Polygon stock subscription).

Uses the historical daily aggregates endpoint:
    /v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}?adjusted=false

RAW OHLCV ONLY. BP27A proved Polygon's ``adjusted=true`` is SPLIT-only (NOT
dividend/total-return), so it disagrees with the Tiingo/Yahoo total-return
``adjusted_close`` by ~2% (more for high-dividend names). To avoid corrupting
the total-return ``adjusted_close`` column, this provider:
  * fetches ``adjusted=false`` -> ``close`` is the true raw close (matches the
    raw ``close`` Tiingo/Yahoo store), and
  * sets ``adjusted_close = None`` (Polygon supplies no total-return value).

It is registered at LOW priority (SOURCE_PRIORITY["polygon"]=40, below
tiingo/yahoo) so Tiingo/Yahoo remain the adjusted_close authority wherever
they have a complete bar; Polygon only fills gap dates (raw close; reads
coalesce to raw). A proper Polygon dividend-adjustment pipeline (splits +
dividends -> total-return) is deferred. Polygon timestamps ``t`` are epoch-ms
at the start of the daily window (midnight ET); the UTC date is the trading
day. Conforms to the DailyPriceProvider protocol.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import httpx
from loguru import logger

from apps.api.src.domain.prices.canonical import RawProviderBar, source_priority
from apps.api.src.domain.prices.providers.base import NoDataError, ProviderError


def _d(v: object) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


def _date_iso(epoch_ms: object) -> str:
    """Polygon daily ``t`` (epoch-ms, midnight ET) -> trading-day ISO date.

    Daily bars are stamped at midnight ET; the UTC instant lands on the same
    calendar day, so the UTC date is the trading day.
    """
    try:
        ts = int(epoch_ms) / 1000.0
    except (TypeError, ValueError):
        return ""
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date().isoformat()


class PolygonProvider:
    name = "polygon"
    priority = source_priority("polygon")

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key or ""
        self._base = "https://api.polygon.io"

    async def fetch_daily_bars(
        self,
        symbol: str,
        start_date: dt.date,
        end_date: dt.date,
    ) -> list[RawProviderBar]:
        if not self.api_key:
            raise ProviderError("POLYGON_API_KEY not configured")
        url = (
            f"{self._base}/v2/aggs/ticker/{symbol.upper()}"
            f"/range/1/day/{start_date.isoformat()}/{end_date.isoformat()}"
        )
        params = {
            "adjusted": "false",      # RAW OHLCV — see module docstring (BP27A)
            "sort": "asc",
            "limit": "50000",
            "apiKey": self.api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"polygon transport error: {exc}") from exc
        if resp.status_code == 404:
            raise NoDataError(f"polygon 404 for {symbol}")
        if resp.status_code >= 400:
            raise ProviderError(
                f"polygon {resp.status_code} for {symbol}: {resp.text[:200]}"
            )
        try:
            body = resp.json()
        except ValueError as exc:
            raise ProviderError(f"polygon non-JSON for {symbol}") from exc
        if not isinstance(body, dict):
            raise ProviderError(f"polygon unexpected shape for {symbol}")
        results = body.get("results")
        if not results:
            raise NoDataError(f"polygon empty window for {symbol}")

        out: list[RawProviderBar] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            out.append(RawProviderBar(
                symbol=symbol.upper(),
                date_iso=_date_iso(r.get("t")),
                open=_d(r.get("o")),
                high=_d(r.get("h")),
                low=_d(r.get("l")),
                close=_d(r.get("c")),       # raw close (adjusted=false)
                adjusted_close=None,        # Polygon has no total-return adj (BP27A)
                volume=int(r["v"]) if r.get("v") is not None else None,
            ))
        logger.debug("polygon fetched {} bars for {}", len(out), symbol)
        return out
