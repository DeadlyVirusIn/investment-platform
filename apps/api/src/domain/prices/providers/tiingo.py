"""Tiingo daily-bar provider wrapping the existing HTTP adapter."""

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


class TiingoProvider:
    name = "tiingo"
    priority = source_priority("tiingo")

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key or ""
        self._base = "https://api.tiingo.com/tiingo"

    async def fetch_daily_bars(
        self,
        symbol: str,
        start_date: dt.date,
        end_date: dt.date,
    ) -> list[RawProviderBar]:
        if not self.api_key:
            raise ProviderError("TIINGO_API_KEY not configured")
        url = f"{self._base}/daily/{symbol.upper()}/prices"
        params = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "resampleFreq": "daily",
            "token": self.api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"tiingo transport error: {exc}") from exc
        if resp.status_code == 404:
            raise NoDataError(f"tiingo 404 for {symbol}")
        if resp.status_code >= 400:
            raise ProviderError(
                f"tiingo {resp.status_code} for {symbol}: {resp.text[:200]}"
            )
        try:
            rows = resp.json()
        except ValueError as exc:
            raise ProviderError(f"tiingo non-JSON for {symbol}") from exc
        if not isinstance(rows, list):
            raise ProviderError(f"tiingo unexpected shape for {symbol}")
        if not rows:
            raise NoDataError(f"tiingo empty window for {symbol}")

        out: list[RawProviderBar] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            out.append(RawProviderBar(
                symbol=symbol.upper(),
                date_iso=str(r.get("date", "")),
                open=_d(r.get("open")),
                high=_d(r.get("high")),
                low=_d(r.get("low")),
                close=_d(r.get("close")),
                adjusted_close=_d(r.get("adjClose")),
                volume=int(r["volume"]) if r.get("volume") is not None else None,
            ))
        logger.debug("tiingo fetched {} bars for {}", len(out), symbol)
        return out
