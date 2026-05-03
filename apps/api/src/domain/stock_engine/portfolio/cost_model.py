"""Deterministic cost model used by the rebalance engine.

Inputs
------
bar : latest available daily bar → OHLC for spread proxy
trade_notional : USD size of the order
avg_dollar_volume_20d : liquidity baseline (fallback = 1e9 to make impact 0)

Outputs
-------
slippage_bps : total expected slippage in basis points
fill_price   : quote_price adjusted by slippage (sign depends on side)
commission   : 0 for personal paper trading (stated default)

Formulas (pure; no DB access; no randomness)::

    spread_bps_proxy = 10_000 * (high - low) / close / 4
    impact_bps       = 10_000 * trade_notional / max(adv20 * 10, 1)
    slippage_bps     = max(2.0, 0.5 * (spread_bps_proxy + impact_bps))
    fill_price       = quote_price * (1 + sign * slippage_bps / 10_000)
        where sign = +1 for buy, -1 for sell
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

MIN_SLIPPAGE_BPS = Decimal("2.0")
IMPACT_DIVISOR = Decimal("10")
DEFAULT_COMMISSION = Decimal("0")


@dataclass(frozen=True)
class CostResult:
    slippage_bps: Decimal
    fill_price: Decimal
    commission: Decimal
    spread_bps_proxy: Decimal
    impact_bps: Decimal


def _d(v: Decimal | float | int | None) -> Decimal:
    if v is None:
        return Decimal("0")
    return v if isinstance(v, Decimal) else Decimal(str(v))


def compute_slippage_bps(
    *,
    close: Decimal,
    high: Decimal,
    low: Decimal,
    trade_notional: Decimal,
    avg_dollar_volume: Decimal | None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return (slippage_bps, spread_bps_proxy, impact_bps). Never negative."""
    close = _d(close)
    high = _d(high)
    low = _d(low)
    trade_notional = _d(trade_notional)
    adv = _d(avg_dollar_volume)

    if close <= 0:
        return MIN_SLIPPAGE_BPS, Decimal("0"), Decimal("0")

    spread_bps_proxy = (Decimal("10000") * (high - low) / close) / Decimal("4")
    if spread_bps_proxy < 0:
        spread_bps_proxy = Decimal("0")

    if adv <= 0:
        # Unknown liquidity → treat as very deep; impact = 0.
        impact_bps = Decimal("0")
    else:
        impact_bps = (Decimal("10000") * trade_notional) / (adv * IMPACT_DIVISOR)

    slip = max(MIN_SLIPPAGE_BPS, Decimal("0.5") * (spread_bps_proxy + impact_bps))
    return slip, spread_bps_proxy, impact_bps


def apply_cost(
    *,
    quote_price: Decimal,
    side: str,
    slippage_bps: Decimal,
) -> Decimal:
    sign = Decimal("1") if side == "buy" else Decimal("-1")
    return _d(quote_price) * (Decimal("1") + sign * _d(slippage_bps) / Decimal("10000"))


def cost_for_trade(
    *,
    side: str,
    quote_price: Decimal,
    high: Decimal,
    low: Decimal,
    trade_notional: Decimal,
    avg_dollar_volume: Decimal | None,
    commission: Decimal = DEFAULT_COMMISSION,
) -> CostResult:
    slip, spread, impact = compute_slippage_bps(
        close=quote_price, high=high, low=low,
        trade_notional=trade_notional, avg_dollar_volume=avg_dollar_volume,
    )
    fill = apply_cost(quote_price=quote_price, side=side, slippage_bps=slip)
    return CostResult(
        slippage_bps=slip,
        fill_price=fill,
        commission=_d(commission),
        spread_bps_proxy=spread,
        impact_bps=impact,
    )
