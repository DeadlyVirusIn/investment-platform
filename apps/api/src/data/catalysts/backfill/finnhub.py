"""Finnhub historical backfill — company news + earnings calendar."""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

import httpx
from loguru import logger

from apps.api.src.data.catalysts.backfill.base import (
    BackfillProvider, BackfillProviderError, EarningsRecord,
    NewsRecord, ProviderFetchResult,
)

BASE_URL = "https://finnhub.io/api/v1"
TIMEOUT = 8.0


class FinnhubBackfillProvider:
    name = "finnhub"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("FINNHUB_API_KEY", "")

    # ------------------------------------------------------------------
    def fetch(
        self, symbol: str, *, start: dt.date, end: dt.date,
    ) -> ProviderFetchResult:
        if not self._api_key:
            raise BackfillProviderError("FINNHUB_API_KEY not configured")
        out = ProviderFetchResult()
        out.news = self._fetch_news(symbol, start=start, end=end)
        out.earnings = self._fetch_earnings(symbol, start=start, end=end)
        return out

    # ------------------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any]) -> Any:
        full = {"token": self._api_key, **params}
        try:
            with httpx.Client(timeout=TIMEOUT) as c:
                r = c.get(f"{BASE_URL}{path}", params=full)
        except httpx.HTTPError as e:
            raise BackfillProviderError(
                f"finnhub HTTP {type(e).__name__}"
            ) from e
        if r.status_code == 429:
            raise BackfillProviderError("finnhub 429 rate-limited")
        if r.status_code >= 400:
            raise BackfillProviderError(f"finnhub {r.status_code}")
        try:
            return r.json()
        except ValueError as e:
            raise BackfillProviderError(f"finnhub bad JSON: {e}") from e

    # ------------------------------------------------------------------
    def _fetch_news(
        self, symbol: str, *, start: dt.date, end: dt.date,
    ) -> list[NewsRecord]:
        rows = self._get("/company-news", {
            "symbol": symbol,
            "from":   start.isoformat(),
            "to":     end.isoformat(),
        })
        if not isinstance(rows, list):
            return []
        out: list[NewsRecord] = []
        for r in rows:
            try:
                ts = r.get("datetime")
                if not ts:
                    continue
                pub = dt.datetime.fromtimestamp(
                    int(ts), tz=dt.timezone.utc,
                )
                out.append(NewsRecord(
                    symbol=symbol.upper(),
                    source=str(r.get("source") or "finnhub"),
                    provider=self.name,
                    title=str(r.get("headline") or "").strip(),
                    url=str(r.get("url") or ""),
                    published_at=pub,
                    summary=r.get("summary"),
                    category=r.get("category"),
                    sentiment=None,
                    raw_payload=r,
                ))
            except Exception as e:
                logger.debug("finnhub news row skipped: {}", e)
                continue
        return [n for n in out if n.title and n.url]

    def _fetch_earnings(
        self, symbol: str, *, start: dt.date, end: dt.date,
    ) -> list[EarningsRecord]:
        try:
            payload = self._get("/calendar/earnings", {
                "symbol": symbol,
                "from":   start.isoformat(),
                "to":     end.isoformat(),
            })
        except BackfillProviderError:
            return []
        rows = (payload or {}).get("earningsCalendar") or []
        out: list[EarningsRecord] = []
        for r in rows:
            date_str = r.get("date")
            if not date_str:
                continue
            try:
                ev_date = dt.date.fromisoformat(date_str)
            except ValueError:
                continue
            fiscal_year = r.get("year")
            time_hint = (r.get("hour") or "").lower() or None
            # known_at not surfaced by Finnhub — leave None; coverage
            # report will downgrade confidence accordingly.
            out.append(EarningsRecord(
                symbol=symbol.upper(),
                provider=self.name,
                event_date=ev_date,
                event_time_hint=time_hint,
                known_at=None,
                fiscal_period=(
                    f"Q{r['quarter']}" if r.get("quarter") else None
                ),
                fiscal_year=int(fiscal_year) if fiscal_year else None,
                eps_estimate=_f(r.get("epsEstimate")),
                eps_actual=_f(r.get("epsActual")),
                revenue_estimate=_f(r.get("revenueEstimate")),
                revenue_actual=_f(r.get("revenueActual")),
                source="finnhub",
                raw_payload=r,
            ))
        return out


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
