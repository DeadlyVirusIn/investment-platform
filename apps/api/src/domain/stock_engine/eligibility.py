"""Eligibility gates for stock-swing candidate generation.

Ordered rejection table — first matching gate wins, and the resulting
``rejection_reason`` is stored on the candidate_idea row. Every row passes
through ``first_rejection_reason``; accepted rows get ``None``.

Rejection reasons are enumerated below and are the ONLY values allowed in
``candidate_idea.rejection_reason`` aside from ``topn_overflow`` (produced
downstream by the decision engine, not a gate).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from apps.api.src.db.models import FactorSnapshot, RegimeSnapshot

# ---------------------------------------------------------------------------
# Rejection reason vocabulary
# ---------------------------------------------------------------------------

# Gate-produced
REJ_REGIME_OFF           = "regime_off"
REJ_NOT_IN_UNIVERSE      = "not_in_universe"
REJ_INSUFFICIENT_HISTORY = "insufficient_history"
REJ_STALE_DATA           = "stale_data"
REJ_LIQUIDITY_FAIL       = "liquidity_fail"
REJ_EARNINGS_TOO_CLOSE   = "earnings_too_close"
REJ_BELOW_LONG_TREND     = "below_long_trend"
REJ_EXTENDED_FROM_SMA200 = "extended_from_sma200"
REJ_IDIOSYNCRATIC_VOL    = "idiosyncratic_vol_high"
REJ_ALREADY_AT_CAP       = "already_at_cap"
# Downstream (emitted by decision engine, not gates)
REJ_TOPN_OVERFLOW         = "topn_overflow"
REJ_HIGH_VOL_TOPN_OVERFLOW = "high_vol_topn_overflow"
REJ_JOB_ERROR             = "job_error"

ALL_REJECTION_REASONS: tuple[str, ...] = (
    REJ_REGIME_OFF,
    REJ_NOT_IN_UNIVERSE,
    REJ_INSUFFICIENT_HISTORY,
    REJ_STALE_DATA,
    REJ_LIQUIDITY_FAIL,
    REJ_EARNINGS_TOO_CLOSE,
    REJ_BELOW_LONG_TREND,
    REJ_EXTENDED_FROM_SMA200,
    REJ_IDIOSYNCRATIC_VOL,
    REJ_ALREADY_AT_CAP,
    REJ_TOPN_OVERFLOW,
    REJ_HIGH_VOL_TOPN_OVERFLOW,
    REJ_JOB_ERROR,
)

# ---------------------------------------------------------------------------
# Threshold defaults (stated; tune via EngineConfig in later batches)
# ---------------------------------------------------------------------------

MIN_AVG_DOLLAR_VOLUME   = Decimal("50000000")   # $50M / day
EARNINGS_WINDOW_DAYS    = 5
PRICE_VS_200SMA_FLOOR   = Decimal("-0.05")
PRICE_VS_200SMA_CEILING = Decimal("0.30")       # reject >30% extended above SMA200
MAX_POSITION_PCT        = 0.07                  # mirrors portfolio sizer spec


# ---------------------------------------------------------------------------
# Context types
# ---------------------------------------------------------------------------


@dataclass
class PortfolioView:
    """Minimal view over the paper portfolio used by the ``already_at_cap``
    gate. Empty by default; wired in Batch 5 when portfolio sizer lands."""
    weights_by_asset: dict[str, float] = field(default_factory=dict)

    def weight(self, asset_id: str) -> float:
        return self.weights_by_asset.get(asset_id, 0.0)


@dataclass
class DecisionContext:
    regime: RegimeSnapshot | None
    universe_asset_ids: set[str]
    atr_p90: Decimal | None                    # computed across today's universe
    portfolio: PortfolioView = field(default_factory=PortfolioView)
    max_position_pct: float = MAX_POSITION_PCT

    def in_universe(self, asset_id: str) -> bool:
        return asset_id in self.universe_asset_ids


# ---------------------------------------------------------------------------
# Individual gate predicates — True means REJECT
# ---------------------------------------------------------------------------


def _regime_off(ctx: DecisionContext, _row: FactorSnapshot) -> bool:
    """Hard regime block. Only missing regime or explicit downtrend fail here.

    High volatility is handled as a SOFT constraint downstream in the
    decision engine (daily Buy cap shrinks to 3) — NOT as a blanket
    rejection at the gate layer.
    """
    if ctx.regime is None:
        return True
    return ctx.regime.market_trend == "downtrend"


def _not_in_universe(ctx: DecisionContext, row: FactorSnapshot) -> bool:
    return not ctx.in_universe(row.asset_id)


def _insufficient_history(_ctx: DecisionContext, row: FactorSnapshot) -> bool:
    return not row.enough_data


def _stale_data(_ctx: DecisionContext, row: FactorSnapshot) -> bool:
    return bool(row.stale_data)


def _liquidity_fail(_ctx: DecisionContext, row: FactorSnapshot) -> bool:
    adv = row.avg_dollar_volume_20d
    if adv is None:
        return True
    if not isinstance(adv, Decimal):
        adv = Decimal(str(adv))
    return adv < MIN_AVG_DOLLAR_VOLUME


def _earnings_too_close(_ctx: DecisionContext, row: FactorSnapshot) -> bool:
    ep = row.earnings_proximity_days
    return ep is not None and ep <= EARNINGS_WINDOW_DAYS


def _below_long_trend(_ctx: DecisionContext, row: FactorSnapshot) -> bool:
    p200 = row.price_vs_200sma
    if p200 is None:
        return True
    if not isinstance(p200, Decimal):
        p200 = Decimal(str(p200))
    return p200 < PRICE_VS_200SMA_FLOOR


def _extended_from_sma200(_ctx: DecisionContext, row: FactorSnapshot) -> bool:
    """Reject names extended >30% above their 200-day SMA — mean-reversion
    risk dominates forward-return expectation for such names in practice.
    """
    p200 = row.price_vs_200sma
    if p200 is None:
        return False  # handled upstream by _below_long_trend
    if not isinstance(p200, Decimal):
        p200 = Decimal(str(p200))
    return p200 > PRICE_VS_200SMA_CEILING


def _idiosyncratic_vol_high(ctx: DecisionContext, row: FactorSnapshot) -> bool:
    atr_pct = row.atr_percent_14
    if atr_pct is None or ctx.atr_p90 is None:
        return False      # unknown → do not reject here
    if not isinstance(atr_pct, Decimal):
        atr_pct = Decimal(str(atr_pct))
    return atr_pct > ctx.atr_p90


def _already_at_cap(ctx: DecisionContext, row: FactorSnapshot) -> bool:
    return ctx.portfolio.weight(row.asset_id) >= ctx.max_position_pct


# ---------------------------------------------------------------------------
# Ordered evaluation table
# ---------------------------------------------------------------------------

GateFn = Callable[[DecisionContext, FactorSnapshot], bool]

ORDERED_GATES: list[tuple[str, GateFn]] = [
    (REJ_REGIME_OFF,           _regime_off),
    (REJ_NOT_IN_UNIVERSE,      _not_in_universe),
    (REJ_INSUFFICIENT_HISTORY, _insufficient_history),
    (REJ_STALE_DATA,           _stale_data),
    (REJ_LIQUIDITY_FAIL,       _liquidity_fail),
    (REJ_EARNINGS_TOO_CLOSE,   _earnings_too_close),
    (REJ_BELOW_LONG_TREND,     _below_long_trend),
    (REJ_EXTENDED_FROM_SMA200, _extended_from_sma200),
    (REJ_IDIOSYNCRATIC_VOL,    _idiosyncratic_vol_high),
    (REJ_ALREADY_AT_CAP,       _already_at_cap),
]


def first_rejection_reason(
    ctx: DecisionContext, row: FactorSnapshot,
) -> str | None:
    """Return the first rejection reason that fires, or None when eligible."""
    for reason, fn in ORDERED_GATES:
        if fn(ctx, row):
            return reason
    return None
