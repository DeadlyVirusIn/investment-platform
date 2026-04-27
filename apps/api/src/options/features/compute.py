"""Pure feature functions for the options feature engine (Phase 11D).

NO DB writes. NO strategy logic. NO trade creation. Stdlib + Decimal only.

Each feature is a deterministic pure function over a snapshot of accepted
chain quotes (post-liquidity-filter). Missing inputs return None and a
data-quality flag string the orchestrator collects.

Notation:
  * Quotes are `OptionChainQuote` instances (frozen dataclasses).
  * Money fields are Decimal; ratios are float (post-divide); counts int.
  * IV is decimal-form (0.20 means 20%), NEVER percentage form.
"""

from __future__ import annotations

import datetime
import math
import statistics
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Sequence

from apps.api.src.options.data_provider.base_adapter import OptionChainQuote


# ---------------------------------------------------------------------------
# Data-quality flag tokens (frozen — pattern-matched downstream)
# ---------------------------------------------------------------------------

FLAG_NO_QUOTES               = "NO_QUOTES"
FLAG_NO_CALLS                = "NO_CALLS"
FLAG_NO_PUTS                 = "NO_PUTS"
FLAG_NO_SPOT                 = "NO_SPOT"
FLAG_NO_PRICE_HISTORY        = "NO_PRICE_HISTORY"
FLAG_NO_30D_EXPIRY           = "NO_30D_EXPIRY"
FLAG_NO_60D_EXPIRY           = "NO_60D_EXPIRY"
FLAG_NO_90D_EXPIRY           = "NO_90D_EXPIRY"
FLAG_NO_25D_PUT              = "NO_25D_PUT"
FLAG_NO_25D_CALL             = "NO_25D_CALL"
FLAG_INSUFFICIENT_IV_HISTORY = "INSUFFICIENT_IV_HISTORY"
FLAG_INSUFFICIENT_VOL_HIST   = "INSUFFICIENT_VOLUME_HISTORY"
FLAG_NO_OPEN_INTEREST        = "NO_OPEN_INTEREST"
FLAG_NO_VOLUME               = "NO_VOLUME"


# Target horizons (calendar days)
ATM_TARGET_DTE        = 30
TERM_SHORT_DTE        = 30
TERM_LONG_DTE         = 90
DELTA_TARGET_PUT      = Decimal("-0.25")
DELTA_TARGET_CALL     = Decimal("0.25")
DELTA_TOLERANCE       = Decimal("0.10")
ATM_DELTA_TARGET      = Decimal("0.50")
RV_TRADING_DAYS       = 252
RV_LOOKBACK_DAYS      = 20
IV_HISTORY_LOOKBACK   = 252
UNUSUAL_VOL_LOOKBACK  = 20
UNUSUAL_VOL_MIN_HIST  = 5      # need ≥5 days to compute meaningful z


# ---------------------------------------------------------------------------
# Result wrappers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureValue:
    """A computed feature value plus any flags it raised."""
    value: Decimal | None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class WallStrikes:
    call_wall: Decimal | None
    put_wall: Decimal | None
    flags: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_dec(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _calls(quotes: Iterable[OptionChainQuote]) -> list[OptionChainQuote]:
    return [q for q in quotes if q.option_type == "CALL"]


def _puts(quotes: Iterable[OptionChainQuote]) -> list[OptionChainQuote]:
    return [q for q in quotes if q.option_type == "PUT"]


def _dte(expiry: datetime.date, as_of: datetime.date) -> int:
    return (expiry - as_of).days


def _select_expiry_near(
    quotes: Sequence[OptionChainQuote],
    as_of: datetime.date,
    target_dte: int,
) -> datetime.date | None:
    """Pick the expiry whose DTE is closest to target. None if no quotes."""
    expiries = sorted({q.expiry for q in quotes})
    if not expiries:
        return None
    return min(expiries, key=lambda e: abs(_dte(e, as_of) - target_dte))


def _atm_strike_for(
    quotes: Sequence[OptionChainQuote],
    expiry: datetime.date,
    spot: Decimal,
) -> OptionChainQuote | None:
    """Closest-to-ATM call quote at given expiry. None if no calls there."""
    candidates = [q for q in quotes
                  if q.option_type == "CALL" and q.expiry == expiry]
    if not candidates:
        return None
    return min(candidates, key=lambda q: abs(q.strike - spot))


def _delta_target(
    quotes: Sequence[OptionChainQuote],
    expiry: datetime.date,
    option_type: str,
    target_delta: Decimal,
    tol: Decimal = DELTA_TOLERANCE,
) -> OptionChainQuote | None:
    """Pick quote at given expiry/type whose delta is closest to target,
    within ±tol. Returns None if no candidate within tol."""
    candidates = [
        q for q in quotes
        if q.option_type == option_type
        and q.expiry == expiry
        and q.delta is not None
    ]
    if not candidates:
        return None
    best = min(candidates, key=lambda q: abs((q.delta or Decimal("0")) - target_delta))
    if abs((best.delta or Decimal("0")) - target_delta) > tol:
        return None
    return best


# ---------------------------------------------------------------------------
# Put/Call ratios
# ---------------------------------------------------------------------------

def put_call_volume_ratio(
    quotes: Sequence[OptionChainQuote],
) -> FeatureValue:
    if not quotes:
        return FeatureValue(None, (FLAG_NO_QUOTES,))
    calls_vol = sum((q.volume or 0) for q in _calls(quotes))
    puts_vol  = sum((q.volume or 0) for q in _puts(quotes))
    flags: list[str] = []
    if not _calls(quotes):
        flags.append(FLAG_NO_CALLS)
    if not _puts(quotes):
        flags.append(FLAG_NO_PUTS)
    if calls_vol == 0 and puts_vol == 0:
        return FeatureValue(None, tuple(flags) + (FLAG_NO_VOLUME,))
    if calls_vol == 0:
        # All volume on puts — ratio is undefined/infinite; flag + None
        return FeatureValue(None, tuple(flags) + (FLAG_NO_VOLUME,))
    return FeatureValue(Decimal(puts_vol) / Decimal(calls_vol), tuple(flags))


def put_call_oi_ratio(
    quotes: Sequence[OptionChainQuote],
) -> FeatureValue:
    if not quotes:
        return FeatureValue(None, (FLAG_NO_QUOTES,))
    calls_oi = sum((q.open_interest or 0) for q in _calls(quotes))
    puts_oi  = sum((q.open_interest or 0) for q in _puts(quotes))
    flags: list[str] = []
    if not _calls(quotes):
        flags.append(FLAG_NO_CALLS)
    if not _puts(quotes):
        flags.append(FLAG_NO_PUTS)
    if calls_oi == 0 and puts_oi == 0:
        return FeatureValue(None, tuple(flags) + (FLAG_NO_OPEN_INTEREST,))
    if calls_oi == 0:
        return FeatureValue(None, tuple(flags) + (FLAG_NO_OPEN_INTEREST,))
    return FeatureValue(Decimal(puts_oi) / Decimal(calls_oi), tuple(flags))


# ---------------------------------------------------------------------------
# ATM IV — the IV of the ATM call at the ~30d expiry
# ---------------------------------------------------------------------------

def atm_iv(
    quotes: Sequence[OptionChainQuote],
    *,
    as_of: datetime.date,
    spot: Decimal | None,
    target_dte: int = ATM_TARGET_DTE,
) -> FeatureValue:
    if not quotes:
        return FeatureValue(None, (FLAG_NO_QUOTES,))
    if spot is None:
        return FeatureValue(None, (FLAG_NO_SPOT,))
    expiry = _select_expiry_near(quotes, as_of, target_dte)
    if expiry is None:
        return FeatureValue(None, (FLAG_NO_30D_EXPIRY,))
    atm = _atm_strike_for(quotes, expiry, spot)
    if atm is None or atm.iv is None:
        return FeatureValue(None, (FLAG_NO_30D_EXPIRY,))
    return FeatureValue(atm.iv, ())


# ---------------------------------------------------------------------------
# IV rank + percentile (vs trailing 252d ATM IV history)
# ---------------------------------------------------------------------------

def iv_rank(
    current_iv: Decimal | None,
    history: Sequence[Decimal],
) -> FeatureValue:
    """IVR = (IV − min) / (max − min) over history. Float in [0, 1]."""
    if current_iv is None:
        return FeatureValue(None, ())
    hist = [h for h in history if h is not None]
    if len(hist) < 30:
        return FeatureValue(None, (FLAG_INSUFFICIENT_IV_HISTORY,))
    lo, hi = min(hist), max(hist)
    if hi == lo:
        return FeatureValue(Decimal("0"), ())
    return FeatureValue((current_iv - lo) / (hi - lo), ())


def iv_percentile(
    current_iv: Decimal | None,
    history: Sequence[Decimal],
) -> FeatureValue:
    """Pct of history strictly below current. Float in [0, 1]."""
    if current_iv is None:
        return FeatureValue(None, ())
    hist = [h for h in history if h is not None]
    if len(hist) < 30:
        return FeatureValue(None, (FLAG_INSUFFICIENT_IV_HISTORY,))
    below = sum(1 for h in hist if h < current_iv)
    return FeatureValue(Decimal(below) / Decimal(len(hist)), ())


# ---------------------------------------------------------------------------
# Realized vol (annualized stdev of log returns) + VRP
# ---------------------------------------------------------------------------

def realized_vol(
    closes: Sequence[Decimal] | None,
    *,
    lookback: int = RV_LOOKBACK_DAYS,
    trading_days: int = RV_TRADING_DAYS,
) -> FeatureValue:
    if closes is None or len(closes) < lookback + 1:
        return FeatureValue(None, (FLAG_NO_PRICE_HISTORY,))
    series = [float(c) for c in closes[-(lookback + 1):]]
    rets = [
        math.log(series[i] / series[i - 1])
        for i in range(1, len(series))
        if series[i - 1] > 0 and series[i] > 0
    ]
    if len(rets) < 2:
        return FeatureValue(None, (FLAG_NO_PRICE_HISTORY,))
    sd = statistics.stdev(rets)
    return FeatureValue(Decimal(str(sd * math.sqrt(trading_days))), ())


def vrp(
    atm_iv_value: Decimal | None,
    realized_vol_value: Decimal | None,
) -> FeatureValue:
    if atm_iv_value is None or realized_vol_value is None:
        return FeatureValue(None, ())
    return FeatureValue(atm_iv_value - realized_vol_value, ())


# ---------------------------------------------------------------------------
# Skew (25-delta put IV − 25-delta call IV) at ~30d
# ---------------------------------------------------------------------------

def skew_25_delta(
    quotes: Sequence[OptionChainQuote],
    *,
    as_of: datetime.date,
    target_dte: int = ATM_TARGET_DTE,
) -> FeatureValue:
    if not quotes:
        return FeatureValue(None, (FLAG_NO_QUOTES,))
    expiry = _select_expiry_near(quotes, as_of, target_dte)
    if expiry is None:
        return FeatureValue(None, (FLAG_NO_30D_EXPIRY,))
    put = _delta_target(quotes, expiry, "PUT", DELTA_TARGET_PUT)
    call = _delta_target(quotes, expiry, "CALL", DELTA_TARGET_CALL)
    flags: list[str] = []
    if put is None or put.iv is None:
        flags.append(FLAG_NO_25D_PUT)
    if call is None or call.iv is None:
        flags.append(FLAG_NO_25D_CALL)
    if flags:
        return FeatureValue(None, tuple(flags))
    return FeatureValue(put.iv - call.iv, ())


# ---------------------------------------------------------------------------
# Term structure: 30d ATM IV / 90d ATM IV (frozen at 30/90 per Phase 11D spec)
# ---------------------------------------------------------------------------

def term_structure(
    quotes: Sequence[OptionChainQuote],
    *,
    as_of: datetime.date,
    spot: Decimal | None,
    short_dte: int = TERM_SHORT_DTE,
    long_dte: int = TERM_LONG_DTE,
) -> FeatureValue:
    if not quotes:
        return FeatureValue(None, (FLAG_NO_QUOTES,))
    if spot is None:
        return FeatureValue(None, (FLAG_NO_SPOT,))
    short_exp = _select_expiry_near(quotes, as_of, short_dte)
    long_exp = _select_expiry_near(quotes, as_of, long_dte)
    flags: list[str] = []
    if short_exp is None:
        flags.append(FLAG_NO_30D_EXPIRY)
    if long_exp is None or long_exp == short_exp:
        flags.append(FLAG_NO_90D_EXPIRY)
    if flags:
        return FeatureValue(None, tuple(flags))
    short_atm = _atm_strike_for(quotes, short_exp, spot)
    long_atm = _atm_strike_for(quotes, long_exp, spot)
    if (short_atm is None or short_atm.iv is None
            or long_atm is None or long_atm.iv is None):
        return FeatureValue(None, (FLAG_NO_30D_EXPIRY, FLAG_NO_90D_EXPIRY))
    if long_atm.iv == 0:
        return FeatureValue(None, (FLAG_NO_90D_EXPIRY,))
    return FeatureValue(short_atm.iv / long_atm.iv, ())


# ---------------------------------------------------------------------------
# Unusual volume z-score: (today_total − μ) / σ over trailing N days
# ---------------------------------------------------------------------------

def unusual_volume_z(
    today_volume: int,
    history: Sequence[int],
) -> FeatureValue:
    """history is a list of daily totals for the trailing N days
    (excluding today). Returns z-score in σ-units."""
    hist = [int(h) for h in history if h is not None]
    if len(hist) < UNUSUAL_VOL_MIN_HIST:
        return FeatureValue(None, (FLAG_INSUFFICIENT_VOL_HIST,))
    mu = statistics.fmean(hist)
    sd = statistics.pstdev(hist)
    if sd == 0:
        return FeatureValue(Decimal("0"), ())
    return FeatureValue(Decimal(str((today_volume - mu) / sd)), ())


def unusual_call_volume_z(
    quotes: Sequence[OptionChainQuote],
    history: Sequence[int],
) -> FeatureValue:
    today = sum((q.volume or 0) for q in _calls(quotes))
    return unusual_volume_z(today, history)


def unusual_put_volume_z(
    quotes: Sequence[OptionChainQuote],
    history: Sequence[int],
) -> FeatureValue:
    today = sum((q.volume or 0) for q in _puts(quotes))
    return unusual_volume_z(today, history)


# ---------------------------------------------------------------------------
# Gamma exposure proxy:  Σ(γ · OI · 100 · sign)
#   sign = +1 for calls (dealer-short hedging buys), −1 for puts.
# This is a structural proxy, not a dollar-GEX number.
# ---------------------------------------------------------------------------

def gamma_exposure_proxy(
    quotes: Sequence[OptionChainQuote],
) -> FeatureValue:
    if not quotes:
        return FeatureValue(None, (FLAG_NO_QUOTES,))
    total = Decimal("0")
    contributing = 0
    for q in quotes:
        if q.gamma is None or q.open_interest is None:
            continue
        sign = Decimal("1") if q.option_type == "CALL" else Decimal("-1")
        total += q.gamma * Decimal(q.open_interest) * Decimal("100") * sign
        contributing += 1
    if contributing == 0:
        return FeatureValue(None, (FLAG_NO_OPEN_INTEREST,))
    return FeatureValue(total, ())


# ---------------------------------------------------------------------------
# Wall strikes: strike with max OI per side (max-pain analog, simplified)
# ---------------------------------------------------------------------------

def wall_strikes(
    quotes: Sequence[OptionChainQuote],
) -> WallStrikes:
    flags: list[str] = []
    calls = _calls(quotes)
    puts = _puts(quotes)
    call_wall = _max_oi_strike(calls)
    put_wall = _max_oi_strike(puts)
    if call_wall is None:
        flags.append(FLAG_NO_CALLS)
    if put_wall is None:
        flags.append(FLAG_NO_PUTS)
    return WallStrikes(call_wall=call_wall, put_wall=put_wall, flags=tuple(flags))


def _max_oi_strike(side: Sequence[OptionChainQuote]) -> Decimal | None:
    by_strike: dict[Decimal, int] = {}
    for q in side:
        if q.open_interest is None:
            continue
        by_strike[q.strike] = by_strike.get(q.strike, 0) + q.open_interest
    if not by_strike:
        return None
    return max(by_strike.items(), key=lambda kv: kv[1])[0]
