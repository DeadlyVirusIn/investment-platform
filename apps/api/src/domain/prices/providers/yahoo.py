"""Yahoo Finance daily-bar provider (via yfinance). Fallback only."""

from __future__ import annotations

import asyncio
import datetime as dt
from decimal import Decimal

from loguru import logger

from apps.api.src.domain.prices.canonical import RawProviderBar, source_priority
from apps.api.src.domain.prices.providers.base import NoDataError, ProviderError


def _d(v: object) -> Decimal | None:
    if v is None:
        return None
    try:
        if hasattr(v, "item"):  # numpy scalar
            v = v.item()
        # pandas NaN check
        if isinstance(v, float) and v != v:
            return None
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


class YahooProvider:
    name = "yahoo"
    priority = source_priority("yahoo")

    async def fetch_daily_bars(
        self,
        symbol: str,
        start_date: dt.date,
        end_date: dt.date,
    ) -> list[RawProviderBar]:
        return await asyncio.to_thread(
            self._fetch_sync, symbol, start_date, end_date,
        )

    def _fetch_sync(
        self,
        symbol: str,
        start_date: dt.date,
        end_date: dt.date,
    ) -> list[RawProviderBar]:
        try:
            import yfinance as yf  # lazy import so tests can monkeypatch
        except ImportError as exc:
            raise ProviderError("yfinance not installed") from exc

        # yfinance end is exclusive; bump by 1 day to include end_date bar.
        end_inclusive = end_date + dt.timedelta(days=1)
        try:
            ticker = yf.Ticker(symbol.upper())
            df = ticker.history(
                start=start_date.isoformat(),
                end=end_inclusive.isoformat(),
                interval="1d",
                auto_adjust=False,     # keep raw close + separate adj close
                actions=False,
                raise_errors=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"yahoo error for {symbol}: {exc}") from exc

        if df is None or df.empty:
            raise NoDataError(f"yahoo empty window for {symbol}")

        out: list[RawProviderBar] = []
        for idx, row in df.iterrows():
            # idx may be Timestamp → normalize to YYYY-MM-DD
            if hasattr(idx, "date"):
                date_iso = idx.date().isoformat()
            else:
                date_iso = str(idx)[:10]
            out.append(RawProviderBar(
                symbol=symbol.upper(),
                date_iso=date_iso,
                open=_d(row.get("Open")),
                high=_d(row.get("High")),
                low=_d(row.get("Low")),
                close=_d(row.get("Close")),
                adjusted_close=_d(row.get("Adj Close")),
                volume=(int(row["Volume"]) if row.get("Volume") is not None
                        and not (isinstance(row["Volume"], float) and row["Volume"] != row["Volume"])
                        else None),
            ))
        logger.debug("yahoo fetched {} bars for {}", len(out), symbol)
        return out
