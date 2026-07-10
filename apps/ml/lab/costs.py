"""Trading-cost model for Experiment Lab studies — gross vs net.

Slippage uses a half-spread proxy: liquid names pay a floor spread,
illiquid names pay k/sqrt(dollar_volume) capped. Deterministic — cost is
a pure function of (dollar_volume, parameters); no stochastic fills.
The nightly paper path currently applies NO commission/slippage
(MODEL_AND_DATA_FORENSICS: paper fill rule), so any study that ignores
costs overstates net results — this module exists to close that gap.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

DEFAULT_SPREAD_FLOOR_BPS = 1.0
# k / sqrt(dollar_volume): k=5000 → $1M ADV ⇒ 5 bps, $100M ADV ⇒ 0.5 bps (floored)
DEFAULT_IMPACT_K = 5000.0
DEFAULT_CAP_BPS = 50.0


def half_spread_slippage_bps(
    dollar_volume: float,
    *,
    spread_floor_bps: float = DEFAULT_SPREAD_FLOOR_BPS,
    k: float = DEFAULT_IMPACT_K,
    cap_bps: float = DEFAULT_CAP_BPS,
) -> float:
    """Per-side slippage in bps: max(floor, k/sqrt(dollar_volume)), capped.
    Unknown/zero liquidity is charged the cap — never a free fill."""
    if dollar_volume is None or dollar_volume <= 0:
        return cap_bps
    return max(spread_floor_bps, min(cap_bps, k / math.sqrt(dollar_volume)))


def apply_trade_costs(
    trades: Sequence[dict],
    *,
    commission_bps: float = 0.0,
    spread_floor_bps: float = DEFAULT_SPREAD_FLOOR_BPS,
    k: float = DEFAULT_IMPACT_K,
    cap_bps: float = DEFAULT_CAP_BPS,
    round_trip: bool = True,
) -> dict:
    """Apply commission + slippage to a trade list; returns gross vs net.

    Each trade dict needs: gross_return (fraction) and dollar_volume
    (average daily dollar volume of the name). round_trip=True charges
    commission+slippage on entry AND exit (2x per-side bps).
    """
    if not trades:
        raise ValueError("empty trade list")
    sides = 2 if round_trip else 1
    detailed: list[dict] = []
    for t in trades:
        gross = float(t["gross_return"])
        slip = half_spread_slippage_bps(
            float(t.get("dollar_volume") or 0.0),
            spread_floor_bps=spread_floor_bps, k=k, cap_bps=cap_bps,
        )
        cost_bps = (commission_bps + slip) * sides
        detailed.append({
            **t,
            "slippage_bps_per_side": slip,
            "commission_bps_per_side": commission_bps,
            "cost_bps_total": cost_bps,
            "net_return": gross - cost_bps / 1e4,
        })
    n = len(detailed)
    gross_mean = sum(d["gross_return"] for d in detailed) / n
    net_mean = sum(d["net_return"] for d in detailed) / n
    return {
        "n_trades": n,
        "commission_bps": float(commission_bps),
        "round_trip": round_trip,
        "gross_mean_return": gross_mean,
        "net_mean_return": net_mean,
        "mean_cost_bps": sum(d["cost_bps_total"] for d in detailed) / n,
        "trades": detailed,
    }


def cost_sweep(
    trades: Sequence[dict],
    commission_bps_grid: Sequence[float],
    **cost_kwargs,
) -> list[dict]:
    """Run apply_trade_costs across a commission grid; per-point summaries
    only (trade detail dropped — sweeps are for the sensitivity table)."""
    out = []
    for bps in commission_bps_grid:
        res = apply_trade_costs(trades, commission_bps=bps, **cost_kwargs)
        res.pop("trades")
        out.append(res)
    return out
