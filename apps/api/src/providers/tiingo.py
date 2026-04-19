"""Tiingo market-data adapter.

Every HTTP call is:
  1. Rate-limited via TokenBucket (500 req/day default).
  2. Retried with exponential back-off + jitter on 429 / 5xx (up to 3 attempts).
  3. Archived verbatim to provider_raw_archive BEFORE normalisation.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from apps.api.src.providers import RateLimit, TokenBucket


# ---------------------------------------------------------------------------
# Retry predicate – only retry on 429 / 5xx
# ---------------------------------------------------------------------------

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class TiingoAdapter:
    """Fetches market data from the Tiingo REST API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.tiingo.com/tiingo",
        rate_limit: RateLimit | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._bucket = TokenBucket(rate_limit or RateLimit(per_day=500))

    # ------------------------------------------------------------------
    # Internal HTTP helper
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=30),
        reraise=True,
    )
    async def _get(
        self,
        path: str,
        params: dict[str, str],
    ) -> httpx.Response:
        await self._bucket.acquire()
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params={**params, "token": self._api_key})
        response.raise_for_status()
        return response

    # ------------------------------------------------------------------
    # Archive helper (needs a live DB session passed in)
    # ------------------------------------------------------------------

    def _params_hash(self, params: dict[str, str]) -> str:
        canonical = json.dumps(params, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _content_hash(self, body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    async def _fetch_and_archive(
        self,
        session: Any,
        path: str,
        params: dict[str, str],
    ) -> httpx.Response:
        """Execute GET, archive raw response, then return response object."""
        from apps.api.src.ingestion.raw_archive import archive_response

        response = await self._get(path, params)
        endpoint = f"{self._base_url}{path}"
        archive_response(
            session=session,
            provider="tiingo",
            endpoint=endpoint,
            params=params,
            payload_bytes=response.content,
            status_code=response.status_code,
        )
        return response

    # ------------------------------------------------------------------
    # fetch_prices
    # ------------------------------------------------------------------

    async def fetch_prices(
        self,
        symbol: str,
        start: datetime.date,
        end: datetime.date,
        *,
        session: Any = None,
    ) -> list[dict[str, Any]]:
        """Return normalised price-bar dicts for *symbol* over [start, end].

        Each dict contains:
          symbol, ts (ISO-8601 str), open, high, low, close,
          adjusted_close, volume, provider='tiingo'
        """
        path = f"/daily/{symbol.upper()}/prices"
        params: dict[str, str] = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "resampleFreq": "daily",
        }

        if session is not None:
            response = await self._fetch_and_archive(session, path, params)
        else:
            logger.warning("fetch_prices called without DB session – skipping archive")
            response = await self._get(path, params)

        rows: list[dict[str, Any]] = response.json()
        return [self._normalise_price_row(symbol, row) for row in rows]

    def _normalise_price_row(self, symbol: str, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbol": symbol.upper(),
            "ts": row.get("date", ""),
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "adjusted_close": row.get("adjClose"),
            "volume": row.get("volume"),
            "provider": "tiingo",
        }

    # ------------------------------------------------------------------
    # Unimplemented methods – Phase 1+
    # ------------------------------------------------------------------

    async def fetch_corporate_actions(
        self,
        symbol: str,
        start: datetime.date,
        end: datetime.date,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("fetch_corporate_actions not yet implemented for Tiingo")

    async def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError("fetch_fundamentals not yet implemented for Tiingo")

    async def fetch_macro_series(
        self,
        series_id: str,
        start: datetime.date,
        end: datetime.date,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("fetch_macro_series not yet implemented for Tiingo")

    async def list_symbols(self) -> list[str]:
        raise NotImplementedError("list_symbols not yet implemented for Tiingo")
