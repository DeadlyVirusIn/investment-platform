"""Point-in-time data accessor — enforces observation_date ≤ as_of_date.

Single source of truth for historical price + market-series reads inside a
replay run. Every call takes an explicit `as_of` and the accessor filters
on `observation_date <= as_of`. No live provider fallback. No today's date.

The accessor does NOT call Finnhub/yfinance live feeds for catalyst data —
catalyst history is served by PITCatalystService (see service mirror) and
treated as "partial / unavailable" unless the DB stores historical news.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session


class PITError(Exception):
    """Raised when a PIT query is asked for future data."""


@dataclass(frozen=True)
class PITPriceBar:
    symbol: str
    date: dt.date
    open:  float | None
    high:  float | None
    low:   float | None
    close: float | None
    volume: int | None


class PointInTimeDataAccessor:
    """Reads market_series_observation filtered to observation_date <= as_of."""

    def __init__(
        self, session: Session, *,
        bar_symbol_map: dict[str, str] | None = None,
    ):
        self._session = session
        self._map = {k.upper(): v for k, v in (bar_symbol_map or {}).items()}

    # --------------------------------------------------------------- bars ---

    def get_bars(
        self,
        symbol: str,
        *,
        as_of: dt.date,
        lookback_days: int = 300,
    ) -> pd.DataFrame:
        """Return OHLC frame for symbol on (as_of - lookback, as_of]."""
        self._assert_not_future(as_of)
        series_key = self._map.get(symbol.upper(), symbol)
        start = as_of - dt.timedelta(days=lookback_days)
        rows = self._session.execute(text("""
            SELECT observation_date AS date,
                   open, high, low, close, volume
            FROM market_series_observation
            WHERE series_key = :k
              AND observation_date > :start
              AND observation_date <= :asof
            ORDER BY observation_date ASC
        """), {
            "k": series_key,
            "start": start,
            "asof": as_of,
        }).mappings().all()
        if not rows:
            return pd.DataFrame(columns=["date", "open", "high", "low",
                                          "close", "volume", "symbol"])
        df = pd.DataFrame(rows)
        df["symbol"] = symbol
        return df

    def get_bar_on_or_before(
        self, symbol: str, *, as_of: dt.date,
    ) -> PITPriceBar | None:
        """Return the latest bar at or before as_of."""
        self._assert_not_future(as_of)
        series_key = self._map.get(symbol.upper(), symbol)
        row = self._session.execute(text("""
            SELECT observation_date AS date,
                   open, high, low, close, volume
            FROM market_series_observation
            WHERE series_key = :k
              AND observation_date <= :asof
            ORDER BY observation_date DESC
            LIMIT 1
        """), {"k": series_key, "asof": as_of}).mappings().first()
        if not row:
            return None
        return PITPriceBar(
            symbol=symbol,
            date=row["date"],
            open=_f(row["open"]),
            high=_f(row["high"]),
            low=_f(row["low"]),
            close=_f(row["close"]),
            volume=int(row["volume"]) if row["volume"] is not None else None,
        )

    def get_forward_bars(
        self,
        symbol: str, *,
        after: dt.date,
        horizon_days: int,
    ) -> pd.DataFrame:
        """Return bars strictly AFTER `after`, up to `horizon_days` trading
        days. Used only for outcome labelling — never exposed to features."""
        if horizon_days <= 0:
            raise ValueError("horizon_days must be positive")
        series_key = self._map.get(symbol.upper(), symbol)
        # Generous calendar-day window (1.8x) to cover weekend/holidays
        cal_window = int(horizon_days * 1.8) + 5
        end = after + dt.timedelta(days=cal_window)
        rows = self._session.execute(text("""
            SELECT observation_date AS date,
                   open, high, low, close, volume
            FROM market_series_observation
            WHERE series_key = :k
              AND observation_date > :after
              AND observation_date <= :end
            ORDER BY observation_date ASC
        """), {"k": series_key, "after": after, "end": end}).mappings().all()
        if not rows:
            return pd.DataFrame(columns=["date", "open", "high", "low",
                                          "close", "volume", "symbol"])
        df = pd.DataFrame(rows).head(horizon_days + 1)
        df["symbol"] = symbol
        return df

    # ------------------------------------------------------------- macro ---

    def get_macro_series(
        self, series_key: str, *, as_of: dt.date,
    ) -> pd.DataFrame:
        """Macro/rates series (FRED etc.) filtered to observation ≤ as_of."""
        self._assert_not_future(as_of)
        rows = self._session.execute(text("""
            SELECT observation_date AS date, close
            FROM market_series_observation
            WHERE series_key = :k
              AND observation_date <= :asof
            ORDER BY observation_date ASC
        """), {"k": series_key, "asof": as_of}).mappings().all()
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["date", "close"],
        )

    # --------------------------------------------------------- utilities ---

    def _assert_not_future(self, as_of: dt.date) -> None:
        today = dt.date.today()
        if as_of > today:
            raise PITError(f"as_of {as_of} > today {today} — PIT violation")


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
