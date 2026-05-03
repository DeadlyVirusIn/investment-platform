"""Triple-barrier outcome labeling. Pure functions. Decimal-only. No pandas.

Reference pseudocode (from research notes):

    def triple_barrier_label(close_series, entry_ts, sigma_t0, pt=2.0, sl=2.0, n_bars=63):
        p0 = close_series.loc[entry_ts]
        horizon = close_series.loc[entry_ts : entry_ts + n_bars]
        path = horizon / p0 - 1
        up_hit = path[path > pt * sigma_t0].index.min()
        dn_hit = path[path < -sl * sigma_t0].index.min()
        first = min(filter(pd.notna, [up_hit, dn_hit, horizon.index[-1]]))
        if first == up_hit: return +1
        if first == dn_hit: return -1
        return int(np.sign(path.iloc[-1]))

Label semantics:
    +1 = profit-target barrier hit first
    -1 = stop-loss barrier hit first
     0 = horizon reached with terminal return exactly zero
    (sign of terminal return when horizon wins and is non-zero)
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

PricePoint = tuple[dt.datetime, Decimal]


# ---------------------------------------------------------------------------
# Signal-type → time horizon mapping
# ---------------------------------------------------------------------------

HORIZON_TREND = 63         # ~3 trading months
HORIZON_MEAN_REVERSION = 10
HORIZON_DEFAULT = 30

# Evidence factor_keys produced by the feature engine, grouped by family.
# Keep literal — no regex, no guessing — so the mapping is auditable.
_TREND_FACTORS = frozenset({
    "price_vs_sma_long",
    "sma_20_vs_50",
    "trend_strength",
})
_MEAN_REV_FACTORS = frozenset({
    "rsi_14",
})


def classify_signal_type(evidence_factor_keys: list[str] | None) -> str:
    """Classify a recommendation as 'trend', 'mean_reversion', or 'default'
    from the factor_keys of its RecommendationEvidence rows.

    Rule: dominant family wins by count; ties → 'default'. Empty → 'default'.
    Unknown factor_keys are ignored (they don't vote).
    """
    if not evidence_factor_keys:
        return "default"
    trend = sum(1 for k in evidence_factor_keys if k in _TREND_FACTORS)
    mean_rev = sum(1 for k in evidence_factor_keys if k in _MEAN_REV_FACTORS)
    if trend == 0 and mean_rev == 0:
        return "default"
    if trend > mean_rev:
        return "trend"
    if mean_rev > trend:
        return "mean_reversion"
    return "default"


def horizon_for_signal(signal_type: str | None) -> int:
    """Return n_bars for triple-barrier horizon by signal type."""
    if signal_type == "trend":
        return HORIZON_TREND
    if signal_type == "mean_reversion":
        return HORIZON_MEAN_REVERSION
    return HORIZON_DEFAULT


# ---------------------------------------------------------------------------
# Sigma (rolling std of daily returns)
# ---------------------------------------------------------------------------


def _decimal_sqrt(x: Decimal, iterations: int = 30) -> Decimal:
    """Newton-Raphson sqrt for Decimal. Returns 0 for negatives (guard only)."""
    if x <= 0:
        return Decimal("0")
    guess = x / Decimal("2")
    for _ in range(iterations):
        if guess == 0:
            break
        guess = (guess + x / guess) / Decimal("2")
    return guess


def compute_sigma_from_returns(returns: list[Decimal]) -> Decimal | None:
    """Sample standard deviation of a return series. Returns None if < 2 points."""
    if len(returns) < 2:
        return None
    n = Decimal(len(returns))
    mean = sum(returns, Decimal("0")) / n
    var = sum(((r - mean) ** 2 for r in returns), Decimal("0")) / (n - Decimal("1"))
    return _decimal_sqrt(var)


def compute_sigma_t0(
    prices: list[Decimal], lookback: int = 20
) -> Decimal | None:
    """Rolling std of daily returns over the trailing `lookback` bars.

    Requires `lookback + 1` prices (to form `lookback` returns).
    Returns None when insufficient data.
    """
    if len(prices) < lookback + 1:
        return None
    window = prices[-(lookback + 1):]
    returns: list[Decimal] = []
    for i in range(1, len(window)):
        prev = window[i - 1]
        if prev == 0:
            continue
        returns.append((window[i] - prev) / prev)
    return compute_sigma_from_returns(returns)


# ---------------------------------------------------------------------------
# Triple-barrier core
# ---------------------------------------------------------------------------


@dataclass
class BarrierResult:
    label: int                    # -1, 0, or +1
    first_touch_at: dt.datetime   # ts of the first-touched bar (or horizon end)
    touch_return: Decimal         # return at first_touch
    terminal_return: Decimal      # return at horizon end
    entry_price: Decimal
    horizon_end_at: dt.datetime
    reason: str                   # "profit" | "stop" | "horizon"


def _find_entry_idx(
    series: list[PricePoint], entry_ts: dt.datetime
) -> int | None:
    """Index of the first bar with ts >= entry_ts."""
    for i, (ts, _) in enumerate(series):
        if ts >= entry_ts:
            return i
    return None


def triple_barrier_label(
    close_series: list[PricePoint],
    entry_ts: dt.datetime,
    sigma_t0: Decimal,
    pt: Decimal = Decimal("2.0"),
    sl: Decimal = Decimal("2.0"),
    n_bars: int = 63,
) -> BarrierResult | None:
    """Apply triple-barrier labeling.

    `close_series` must be sorted ascending by timestamp. Labels are computed
    strictly forward from `entry_ts` — no lookahead.

    Returns None when entry not found OR fewer than 2 future bars exist OR
    sigma is zero (no volatility, can't form barriers).
    """
    if sigma_t0 <= 0:
        return None
    entry_idx = _find_entry_idx(close_series, entry_ts)
    if entry_idx is None or entry_idx + 1 >= len(close_series):
        return None

    p0 = close_series[entry_idx][1]
    if p0 <= 0:
        return None

    end_idx = min(entry_idx + n_bars, len(close_series) - 1)
    if end_idx <= entry_idx:
        return None

    pt_thresh = pt * sigma_t0
    sl_thresh = sl * sigma_t0

    up_hit_idx: int | None = None
    dn_hit_idx: int | None = None
    for i in range(entry_idx + 1, end_idx + 1):
        ret = (close_series[i][1] - p0) / p0
        if up_hit_idx is None and ret >= pt_thresh:
            up_hit_idx = i
        if dn_hit_idx is None and ret <= -sl_thresh:
            dn_hit_idx = i
        if up_hit_idx is not None and dn_hit_idx is not None:
            break  # both hit; earliest wins in the logic below

    terminal_ret = (close_series[end_idx][1] - p0) / p0

    if up_hit_idx is not None and (dn_hit_idx is None or up_hit_idx <= dn_hit_idx):
        touch_ts, touch_px = close_series[up_hit_idx]
        return BarrierResult(
            label=1,
            first_touch_at=touch_ts,
            touch_return=(touch_px - p0) / p0,
            terminal_return=terminal_ret,
            entry_price=p0,
            horizon_end_at=close_series[end_idx][0],
            reason="profit",
        )
    if dn_hit_idx is not None:
        touch_ts, touch_px = close_series[dn_hit_idx]
        return BarrierResult(
            label=-1,
            first_touch_at=touch_ts,
            touch_return=(touch_px - p0) / p0,
            terminal_return=terminal_ret,
            entry_price=p0,
            horizon_end_at=close_series[end_idx][0],
            reason="stop",
        )

    # Horizon reached: per reference pseudocode, label = sign(terminal_return).
    if terminal_ret > 0:
        label = 1
    elif terminal_ret < 0:
        label = -1
    else:
        label = 0
    return BarrierResult(
        label=label,
        first_touch_at=close_series[end_idx][0],
        touch_return=terminal_ret,
        terminal_return=terminal_ret,
        entry_price=p0,
        horizon_end_at=close_series[end_idx][0],
        reason="horizon",
    )


# ---------------------------------------------------------------------------
# Realized returns at fixed horizons
# ---------------------------------------------------------------------------


def realized_return_at(
    close_series: list[PricePoint],
    entry_ts: dt.datetime,
    offset_days: int,
    entry_price: Decimal | None = None,
) -> tuple[Decimal, Decimal] | None:
    """Return (price_at_offset, realized_return) or None.

    Picks the first bar with ts >= (entry_ts + offset_days). Uses `entry_price`
    if provided (from RecommendationOutcome.price_at_recommendation); otherwise
    looks up the entry-bar price.
    """
    target = entry_ts + dt.timedelta(days=offset_days)
    target_idx: int | None = None
    for i, (ts, _) in enumerate(close_series):
        if ts >= target:
            target_idx = i
            break
    if target_idx is None:
        return None

    if entry_price is None:
        entry_idx = _find_entry_idx(close_series, entry_ts)
        if entry_idx is None:
            return None
        entry_price = close_series[entry_idx][1]

    if entry_price <= 0:
        return None
    target_price = close_series[target_idx][1]
    return target_price, (target_price - entry_price) / entry_price
