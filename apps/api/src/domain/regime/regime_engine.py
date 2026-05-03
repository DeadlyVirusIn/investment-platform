"""Regime engine — SPY-driven market trend + volatility regime.

Pure functions below are deterministic and take sorted-asc price series. No
DB access in the pure layer. ``compute_regime_for_date`` is the thin
adapter that loads SPY bars from Postgres and returns a ``RegimeResult``
ready to persist.

Thresholds and minimums are defaults chosen to balance strictness vs
ability to emit a row with the ~250 bars of history currently ingested:

* SMA50 requires 50 prior closes.
* SMA200 requires 200 prior closes.
* Realized vol requires 21 prior closes (→ 20 returns).
* Percentile windows use ``min(252, available)`` samples with a floor of
  ``MIN_PCTILE_SAMPLES = 30`` — less than that returns ``None`` and the
  day is skipped.

All price inputs must be in ascending ts order and filtered to bars with
``ts <= as_of_date`` (anti-lookahead).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PriceBar

BENCHMARK_SYMBOL = "SPY"
TRADING_DAYS_PER_YEAR = 252

# Anchors for the trend classifier
UPTREND_PCT_ABOVE_200 = 0.0
DOWNTREND_PCT_BELOW_200 = -0.05

# Anchors for the vol classifier (percentile of rv20 over ~1y)
VOL_LOW_CUT = 0.33
VOL_HIGH_CUT = 0.80

MIN_SMA_LONG = 200
MIN_SMA_SHORT = 50
RV_WINDOW = 20
ATR_PERIOD = 14
PCTILE_WINDOW = TRADING_DAYS_PER_YEAR
MIN_PCTILE_SAMPLES = 30


# ---------------------------------------------------------------------------
# Pure types
# ---------------------------------------------------------------------------


@dataclass
class BarView:
    ts: dt.datetime
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass
class RegimeResult:
    as_of_date: dt.date
    benchmark_symbol: str
    market_trend: str       # 'uptrend' | 'downtrend' | 'sideways'
    vol_regime: str         # 'low' | 'normal' | 'high'
    breadth_regime: str | None
    sma50_over_sma200: bool
    realized_vol_20d: Decimal
    atr_pctile_1y: Decimal


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------


def _f(v: Decimal | float | int) -> float:
    return float(v)


def simple_moving_average(values: Sequence[Decimal], n: int) -> float | None:
    if len(values) < n or n <= 0:
        return None
    window = values[-n:]
    return sum(_f(v) for v in window) / n


def log_returns(closes: Sequence[Decimal]) -> list[float]:
    """Day-over-day log returns. Skips any pair where prev <= 0."""
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = _f(closes[i - 1])
        curr = _f(closes[i])
        if prev <= 0 or curr <= 0:
            continue
        out.append(math.log(curr / prev))
    return out


def _stdev(values: Sequence[float]) -> float | None:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(var)


def realized_vol_annualized(
    closes: Sequence[Decimal], window: int = RV_WINDOW
) -> float | None:
    """Annualized realized vol from ``window`` daily log returns."""
    if len(closes) < window + 1:
        return None
    tail = closes[-(window + 1):]
    rets = log_returns(tail)
    if len(rets) < 2:
        return None
    sd = _stdev(rets)
    if sd is None:
        return None
    return sd * math.sqrt(TRADING_DAYS_PER_YEAR)


def atr_percent(bars: Sequence[BarView], period: int = ATR_PERIOD) -> float | None:
    """ATR / last close, computed from a sorted-asc bar series."""
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        h, lo = _f(bars[i].high), _f(bars[i].low)
        prev_close = _f(bars[i - 1].close)
        tr = max(h - lo, abs(h - prev_close), abs(lo - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[-period:]) / period
    close = _f(bars[-1].close)
    if close <= 0:
        return None
    return atr / close


def percentile_rank(history: Sequence[float], today: float) -> float | None:
    """Fraction of historical samples strictly less than ``today``.

    Returns None when < ``MIN_PCTILE_SAMPLES`` non-null samples. Result is
    in [0.0, 1.0].
    """
    vals = [v for v in history if v is not None and math.isfinite(v)]
    if len(vals) < MIN_PCTILE_SAMPLES:
        return None
    below = sum(1 for v in vals if v < today)
    return below / len(vals)


# ---------------------------------------------------------------------------
# Classifiers
# ---------------------------------------------------------------------------


def classify_market_trend(
    close: float, sma50: float, sma200: float,
) -> str:
    pct_above_200 = (close - sma200) / sma200 if sma200 != 0 else 0.0
    if sma50 > sma200 and pct_above_200 > UPTREND_PCT_ABOVE_200:
        return "uptrend"
    if sma50 < sma200 and pct_above_200 < DOWNTREND_PCT_BELOW_200:
        return "downtrend"
    return "sideways"


def classify_vol_regime(rv_pctile_1y: float) -> str:
    if rv_pctile_1y < VOL_LOW_CUT:
        return "low"
    if rv_pctile_1y < VOL_HIGH_CUT:
        return "normal"
    return "high"


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _rv_history(closes: Sequence[Decimal], window: int = RV_WINDOW) -> list[float]:
    """Walk a rolling rv20 across the full close series, producing one rv20
    value per day from index ``window`` onward."""
    out: list[float] = []
    for i in range(window, len(closes)):
        slice_ = closes[i - window : i + 1]
        rv = realized_vol_annualized(slice_, window=window)
        if rv is not None:
            out.append(rv)
    return out


def _atr_history(bars: Sequence[BarView], period: int = ATR_PERIOD) -> list[float]:
    """Rolling ATR% series, one value per day starting at index ``period``."""
    out: list[float] = []
    for i in range(period, len(bars)):
        slice_ = bars[i - period : i + 1]
        a = atr_percent(slice_, period=period)
        if a is not None:
            out.append(a)
    return out


def compute_regime(
    bars: Sequence[BarView], as_of: dt.date,
) -> RegimeResult | None:
    """Return a RegimeResult from a sorted-asc SPY bar series, or None when
    insufficient history to classify trend + vol."""
    closes = [b.close for b in bars]
    if len(closes) < MIN_SMA_LONG:
        return None
    sma50 = simple_moving_average(closes, MIN_SMA_SHORT)
    sma200 = simple_moving_average(closes, MIN_SMA_LONG)
    if sma50 is None or sma200 is None:
        return None

    close_today = _f(closes[-1])
    market_trend = classify_market_trend(close_today, sma50, sma200)

    rv_today = realized_vol_annualized(closes, window=RV_WINDOW)
    if rv_today is None:
        return None

    # Percentile of today's rv20 across prior rv20 samples (exclude today).
    rv_hist = _rv_history(closes, window=RV_WINDOW)
    if not rv_hist:
        return None
    window_samples = rv_hist[-PCTILE_WINDOW:-1] if len(rv_hist) > 1 else []
    rv_pctile = percentile_rank(window_samples, rv_today)
    if rv_pctile is None:
        return None
    vol_regime = classify_vol_regime(rv_pctile)

    # ATR percentile — same window policy as rv.
    atr_today = atr_percent(bars, period=ATR_PERIOD)
    atr_hist = _atr_history(bars, period=ATR_PERIOD)
    atr_window = atr_hist[-PCTILE_WINDOW:-1] if len(atr_hist) > 1 else []
    atr_pctile = (
        percentile_rank(atr_window, atr_today)
        if atr_today is not None else None
    )
    if atr_pctile is None:
        return None

    return RegimeResult(
        as_of_date=as_of,
        benchmark_symbol=BENCHMARK_SYMBOL,
        market_trend=market_trend,
        vol_regime=vol_regime,
        breadth_regime=None,    # breadth intentionally skipped in Batch 2
        sma50_over_sma200=sma50 > sma200,
        realized_vol_20d=Decimal(str(round(rv_today, 6))),
        atr_pctile_1y=Decimal(str(round(atr_pctile, 6))),
    )


# ---------------------------------------------------------------------------
# DB-facing adapter
# ---------------------------------------------------------------------------


def _load_spy_bars(
    session: Session, as_of: dt.date, symbol: str = BENCHMARK_SYMBOL,
) -> list[BarView]:
    """Load all daily SPY bars with ``ts <= end of as_of day`` (anti-lookahead)."""
    upper = dt.datetime.combine(
        as_of, dt.time(23, 59, 59, 999999), tzinfo=dt.timezone.utc,
    )
    stmt = (
        select(PriceBar)
        .join(Asset, Asset.id == PriceBar.asset_id)
        .where(
            Asset.symbol == symbol,
            PriceBar.timeframe == "1d",
            PriceBar.ts <= upper,
        )
        .order_by(PriceBar.ts.asc())
    )
    return [
        BarView(ts=b.ts, high=b.high, low=b.low, close=b.close)
        for b in session.scalars(stmt)
        if b.high is not None and b.low is not None and b.close is not None
    ]


def compute_regime_for_date(
    session: Session, as_of: dt.date,
) -> RegimeResult | None:
    """Load SPY bars from the DB and compute the regime for ``as_of``."""
    bars = _load_spy_bars(session, as_of)
    return compute_regime(bars, as_of)
