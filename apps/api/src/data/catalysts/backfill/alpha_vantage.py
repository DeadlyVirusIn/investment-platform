"""Alpha Vantage backfill — rate-limited free tier (5/min).

Endpoints used:
  NEWS_SENTIMENT    — per-symbol news with published_time in UTC
  EARNINGS          — historical reported earnings

Only enabled when ALPHA_VANTAGE_API_KEY is set; otherwise provider raises
BackfillProviderError and the service moves on.
"""

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

BASE_URL = "https://www.alphavantage.co/query"
TIMEOUT = 12.0


class AlphaVantageBackfillProvider:
    name = "alpha_vantage"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY", "")

    def fetch(
        self, symbol: str, *, start: dt.date, end: dt.date,
    ) -> ProviderFetchResult:
        if not self._api_key:
            raise BackfillProviderError("ALPHA_VANTAGE_API_KEY not set")
        out = ProviderFetchResult()
        out.news = self._fetch_news(symbol, start=start, end=end)
        out.earnings = self._fetch_earnings(symbol, start=start, end=end)
        return out

    # ------------------------------------------------------------------
    def _get(self, params: dict[str, Any]) -> Any:
        merged = {"apikey": self._api_key, **params}
        try:
            with httpx.Client(timeout=TIMEOUT) as c:
                r = c.get(BASE_URL, params=merged)
        except httpx.HTTPError as e:
            raise BackfillProviderError(
                f"alpha_vantage HTTP {type(e).__name__}"
            ) from e
        if r.status_code >= 400:
            raise BackfillProviderError(f"alpha_vantage {r.status_code}")
        try:
            payload = r.json()
        except ValueError as e:
            raise BackfillProviderError(
                f"alpha_vantage bad JSON: {e}"
            ) from e
        if isinstance(payload, dict) and "Note" in payload:
            raise BackfillProviderError(
                f"alpha_vantage rate-limit note: {payload['Note']}"
            )
        return payload

    # ------------------------------------------------------------------
    def _fetch_news(
        self, symbol: str, *, start: dt.date, end: dt.date,
    ) -> list[NewsRecord]:
        payload = self._get({
            "function": "NEWS_SENTIMENT",
            "tickers":  symbol,
            "time_from": start.strftime("%Y%m%dT0000"),
            "time_to":   end.strftime("%Y%m%dT2359"),
            "limit":    200,
        })
        rows = (payload or {}).get("feed") or []
        out: list[NewsRecord] = []
        for r in rows:
            try:
                ts = r.get("time_published")
                if not ts:
                    continue
                pub = dt.datetime.strptime(ts, "%Y%m%dT%H%M%S") \
                         .replace(tzinfo=dt.timezone.utc)
                # Overall sentiment available per article (numeric)
                s_overall = _f(r.get("overall_sentiment_score"))
                out.append(NewsRecord(
                    symbol=symbol.upper(),
                    source=str(r.get("source") or "alpha_vantage"),
                    provider=self.name,
                    title=str(r.get("title") or "").strip(),
                    url=str(r.get("url") or ""),
                    published_at=pub,
                    summary=r.get("summary"),
                    category=(r.get("topics") or [{}])[0].get("topic")
                              if r.get("topics") else None,
                    sentiment=s_overall,
                    raw_payload=r,
                ))
            except Exception as e:
                logger.debug("alpha_vantage news row skipped: {}", e)
                continue
        return [n for n in out if n.title and n.url]

    def _fetch_earnings(
        self, symbol: str, *, start: dt.date, end: dt.date,
    ) -> list[EarningsRecord]:
        try:
            payload = self._get({
                "function": "EARNINGS",
                "symbol":   symbol,
            })
        except BackfillProviderError:
            return []
        qrows = (payload or {}).get("quarterlyEarnings") or []
        out: list[EarningsRecord] = []
        for r in qrows:
            date_str = r.get("reportedDate")
            if not date_str:
                continue
            try:
                ev_date = dt.date.fromisoformat(date_str)
            except ValueError:
                continue
            if ev_date < start or ev_date > end:
                continue
            out.append(EarningsRecord(
                symbol=symbol.upper(),
                provider=self.name,
                event_date=ev_date,
                event_time_hint=None,
                known_at=None,
                fiscal_period=r.get("fiscalDateEnding"),
                fiscal_year=None,
                eps_estimate=_f(r.get("estimatedEPS")),
                eps_actual=_f(r.get("reportedEPS")),
                revenue_estimate=None,
                revenue_actual=None,
                source="alpha_vantage",
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
