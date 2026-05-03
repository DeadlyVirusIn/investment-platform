"""Exit-rule evaluator for open positions.

Pure function. Returns an ordered list of ``ExitDecision`` — one per
position that must close, with an explicit reason tag.

Rules (evaluated per position, first match wins)::

    1. stop_loss       : unrealized return <= STOP_LOSS_PCT  (default -10%)
    2. regime_exit     : regime.market_trend == 'downtrend'
    3. horizon_exit    : holding_days >= MAX_HOLDING_DAYS    (default 10)
    4. universe_exit   : asset_id no longer in active universe
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping

STOP_LOSS_PCT = Decimal("-0.10")
MAX_HOLDING_DAYS = 10


@dataclass(frozen=True)
class PositionView:
    asset_id: str
    quantity: Decimal
    avg_cost: Decimal
    opened_at: dt.datetime


@dataclass(frozen=True)
class RegimeView:
    market_trend: str | None           # 'uptrend' | 'downtrend' | 'sideways' | None


@dataclass(frozen=True)
class ExitDecision:
    asset_id: str
    reason: str                        # 'stop_loss' | 'regime_exit' | 'horizon_exit' | 'universe_exit'
    current_price: Decimal | None
    unrealized_pct: Decimal | None
    holding_days: int


def _unrealized_pct(avg_cost: Decimal, current_price: Decimal) -> Decimal | None:
    if avg_cost <= 0 or current_price is None:
        return None
    return (current_price - avg_cost) / avg_cost


def _holding_days(opened_at: dt.datetime, now: dt.datetime) -> int:
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    return max(0, (now.date() - opened_at.date()).days)


def evaluate_exits(
    *,
    positions: Iterable[PositionView],
    prices_by_asset: Mapping[str, Decimal | None],
    regime: RegimeView | None,
    universe_asset_ids: set[str],
    now: dt.datetime,
    stop_loss_pct: Decimal = STOP_LOSS_PCT,
    max_holding_days: int = MAX_HOLDING_DAYS,
) -> list[ExitDecision]:
    exits: list[ExitDecision] = []
    downtrend = bool(regime is not None and regime.market_trend == "downtrend")

    for pos in positions:
        current_price = prices_by_asset.get(pos.asset_id)
        pct = None
        if current_price is not None:
            pct = _unrealized_pct(pos.avg_cost, current_price)
        days = _holding_days(pos.opened_at, now)

        reason: str | None = None
        if pct is not None and pct <= stop_loss_pct:
            reason = "stop_loss"
        elif downtrend:
            reason = "regime_exit"
        elif days >= max_holding_days:
            reason = "horizon_exit"
        elif pos.asset_id not in universe_asset_ids:
            reason = "universe_exit"

        if reason is not None:
            exits.append(ExitDecision(
                asset_id=pos.asset_id,
                reason=reason,
                current_price=current_price,
                unrealized_pct=pct,
                holding_days=days,
            ))

    return exits
