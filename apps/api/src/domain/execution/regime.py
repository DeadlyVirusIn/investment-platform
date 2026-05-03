"""Market-regime classifier + regime -> sizing-multiplier table.

Input: daily price series (e.g. SPY closes). Pure function, no DB.

Regime enum {trend_up, sideways, high_vol, low_vol}:

  - high_vol  — short-window vol / long-window vol > HIGH_VOL_RATIO
  - low_vol   — short / long < LOW_VOL_RATIO
  - trend_up  — SMA_short > SMA_long AND SMA_short rising vs prior
  - sideways  — default

Priority: vol regimes dominate (they matter most for sizing). If vol is
within band, fall through to trend detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, pstdev

# ---------------------------------------------------------------------------
# Regime parameters
# ---------------------------------------------------------------------------

VOL_WINDOW_SHORT: int = 20
VOL_WINDOW_LONG: int = 60
SMA_SHORT: int = 20
SMA_LONG: int = 50
SLOPE_LOOKBACK: int = 20       # compare SMA_short now vs SMA_short `SLOPE_LOOKBACK` bars ago

HIGH_VOL_RATIO: float = 1.5    # short/long vol above this -> high_vol
LOW_VOL_RATIO: float = 0.75    # short/long vol below this  -> low_vol

# Minimum bars required for classification
MIN_BARS_REQUIRED: int = VOL_WINDOW_LONG

# Regime -> sizing multiplier (gating table). Do NOT overfit; round numbers.
REGIME_MULTIPLIERS: dict[str, float] = {
    "trend_up": 1.00,     # full allocation on strong trend
    "low_vol":  1.00,     # full allocation when market quiet
    "sideways": 0.50,     # half size — chop; preserve capital
    "high_vol": 0.25,     # quarter size — tail risk, reduce exposure
}
DEFAULT_REGIME: str = "sideways"   # fallback on insufficient data
REGIMES: tuple[str, ...] = tuple(REGIME_MULTIPLIERS.keys())


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeSignal:
    regime: str                # one of REGIMES or DEFAULT_REGIME
    multiplier: float          # from REGIME_MULTIPLIERS
    vol_ratio: float | None    # short/long vol ratio
    sma_short: float | None
    sma_long: float | None
    slope_up: bool | None
    bars_available: int
    reason: str                # short why-tag


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _returns(prices: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(prices)):
        p_prev = prices[i - 1]
        if p_prev <= 0:
            continue
        out.append((prices[i] - p_prev) / p_prev)
    return out


def _rolling_std(returns: list[float], window: int) -> float | None:
    if len(returns) < window or window < 2:
        return None
    return pstdev(returns[-window:])


def _sma(prices: list[float], window: int) -> float | None:
    if len(prices) < window:
        return None
    return fmean(prices[-window:])


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def classify_regime(
    prices: list[float],
    *,
    vol_window_short: int = VOL_WINDOW_SHORT,
    vol_window_long: int = VOL_WINDOW_LONG,
    sma_short_w: int = SMA_SHORT,
    sma_long_w: int = SMA_LONG,
    slope_lookback: int = SLOPE_LOOKBACK,
    high_vol_ratio: float = HIGH_VOL_RATIO,
    low_vol_ratio: float = LOW_VOL_RATIO,
) -> RegimeSignal:
    """Classify current regime from trailing price series.

    `prices` is an ordered list of daily closes (most recent last). Returns
    a default `sideways` regime if insufficient bars.
    """
    n = len(prices)
    if n < vol_window_long:
        return RegimeSignal(
            regime=DEFAULT_REGIME,
            multiplier=REGIME_MULTIPLIERS[DEFAULT_REGIME],
            vol_ratio=None, sma_short=None, sma_long=None, slope_up=None,
            bars_available=n,
            reason=f"insufficient_bars:{n}<{vol_window_long}",
        )

    rets = _returns(prices)
    short_vol = _rolling_std(rets, vol_window_short)
    long_vol = _rolling_std(rets, vol_window_long)
    vol_ratio = (
        short_vol / long_vol
        if (short_vol is not None and long_vol is not None and long_vol > 0)
        else None
    )

    sma_s = _sma(prices, sma_short_w)
    sma_l = _sma(prices, sma_long_w)

    slope_up: bool | None = None
    # Slope: SMA_short now vs SMA_short `slope_lookback` bars ago
    if len(prices) >= sma_short_w + slope_lookback:
        sma_short_past = _sma(prices[:-slope_lookback], sma_short_w)
        if sma_short_past is not None and sma_s is not None:
            slope_up = sma_s > sma_short_past

    # Decision priority: vol extremes first, then trend, else sideways
    if vol_ratio is not None and vol_ratio > high_vol_ratio:
        regime = "high_vol"
        reason = f"vol_ratio={vol_ratio:.3f}>{high_vol_ratio}"
    elif vol_ratio is not None and vol_ratio < low_vol_ratio:
        regime = "low_vol"
        reason = f"vol_ratio={vol_ratio:.3f}<{low_vol_ratio}"
    elif (
        sma_s is not None and sma_l is not None
        and sma_s > sma_l and slope_up is True
    ):
        regime = "trend_up"
        reason = "sma_short>sma_long & slope_up"
    else:
        regime = "sideways"
        reason = "default_band"

    return RegimeSignal(
        regime=regime,
        multiplier=REGIME_MULTIPLIERS[regime],
        vol_ratio=vol_ratio,
        sma_short=sma_s,
        sma_long=sma_l,
        slope_up=slope_up,
        bars_available=n,
        reason=reason,
    )


def regime_multiplier(regime: str) -> float:
    """Look up multiplier for a regime label. Unknown -> default."""
    return REGIME_MULTIPLIERS.get(regime, REGIME_MULTIPLIERS[DEFAULT_REGIME])
