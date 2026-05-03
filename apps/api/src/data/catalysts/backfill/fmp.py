"""FMP backfill — future-ready stub.

Implemented to be pluggable; if FMP_API_KEY is not set, raises so the
service skips it. Endpoints chosen are stable across FMP tiers; adjust
paths when the subscription arrives.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

import httpx

from apps.api.src.data.catalysts.backfill.base import (
    BackfillProvider, BackfillProviderError, EarningsRecord,
    NewsRecord, ProviderFetchResult,
)

BASE_URL = "https://financialmodelingprep.com/api/v3"
TIMEOUT = 10.0


class FMPBackfillProvider:
    name = "fmp"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("FMP_API_KEY", "")

    def fetch(
        self, symbol: str, *, start: dt.date, end: dt.date,
    ) -> ProviderFetchResult:
        if not self._api_key:
            raise BackfillProviderError("FMP_API_KEY not set")
        out = ProviderFetchResult()
        try:
            out.news = self._news(symbol, start=start, end=end)
        except BackfillProviderError as e:
            out.warnings.append(f"fmp news: {e}")
        try:
            out.earnings = self._earnings(symbol, start=start, end=end)
        except BackfillProviderError as e:
            out.warnings.append(f"fmp earnings: {e}")
        return out

    # ------------------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any]) -> Any:
        merged = {"apikey": self._api_key, **params}
        try:
            with httpx.Client(timeout=TIMEOUT) as c:
                r = c.get(f"{BASE_URL}{path}", params=merged)
        except httpx.HTTPError as e:
            raise BackfillProviderError(
                f"fmp HTTP {type(e).__name__}"
            ) from e
        if r.status_code >= 400:
            raise BackfillProviderError(f"fmp {r.status_code}")
        try:
            return r.json()
        except ValueError as e:
            raise BackfillProviderError(f"fmp bad JSON: {e}") from e

    def _news(
        self, symbol: str, *, start: dt.date, end: dt.date,
    ) -> list[NewsRecord]:
        rows = self._get("/stock_news", {
            "tickers": symbol, "limit": 500,
            "from": start.isoformat(), "to": end.isoformat(),
        })
        if not isinstance(rows, list):
            return []
        out: list[NewsRecord] = []
        for r in rows:
            pub_raw = r.get("publishedDate")
            if not pub_raw:
                continue
            try:
                pub = dt.datetime.fromisoformat(
                    pub_raw.replace("Z", "+00:00"),
                )
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=dt.timezone.utc)
            except ValueError:
                continue
            out.append(NewsRecord(
                symbol=symbol.upper(),
                source=str(r.get("site") or "fmp"),
                provider=self.name,
                title=str(r.get("title") or "").strip(),
                url=str(r.get("url") or ""),
                published_at=pub,
                summary=r.get("text"),
                raw_payload=r,
            ))
        return [n for n in out if n.title and n.url]

    def _earnings(
        self, symbol: str, *, start: dt.date, end: dt.date,
    ) -> list[EarningsRecord]:
        rows = self._get(
            f"/historical/earning_calendar/{symbol}", {},
        )
        if not isinstance(rows, list):
            return []
        out: list[EarningsRecord] = []
        for r in rows:
            date_str = r.get("date")
            if not date_str:
                continue
            try:
                ev_date = dt.date.fromisoformat(date_str)
            except ValueError:
                continue
            if ev_date < start or ev_date > end:
                continue
            # FMP exposes `updatedFromDate` which is a rough proxy for known_at
            known_at = None
            if r.get("updatedFromDate"):
                try:
                    known_at = dt.datetime.fromisoformat(
                        r["updatedFromDate"]
                    ).replace(tzinfo=dt.timezone.utc)
                except ValueError:
                    known_at = None
            out.append(EarningsRecord(
                symbol=symbol.upper(),
                provider=self.name,
                event_date=ev_date,
                event_time_hint=(r.get("time") or "").lower() or None,
                known_at=known_at,
                fiscal_period=r.get("fiscalDateEnding"),
                fiscal_year=None,
                eps_estimate=_f(r.get("epsEstimated")),
                eps_actual=_f(r.get("eps")),
                revenue_estimate=_f(r.get("revenueEstimated")),
                revenue_actual=_f(r.get("revenue")),
                source="fmp",
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
