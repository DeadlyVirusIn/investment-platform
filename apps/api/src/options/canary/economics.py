"""P6D.33A — options economic viability assessment (pure math, no DB).

Prevents structurally uneconomic credit-spread trades from being promoted
(fees + close-side slippage drag exceed the credit's economics) and feeds
the lifecycle TP guard so a take-profit that would book NEGATIVE realized
P&L is never labeled CLOSED_TAKE_PROFIT.

Model — mirrors the REAL paper engine, no new fee/slippage math:
  * slippage per leg per side = min(half_spread, $0.05) in price terms
    (paper.fills.slippage_per_contract), ×100 per contract in dollars.
  * fee = DEFAULT_FEE_PER_CONTRACT ($0.70) per contract per side;
    fees_round_trip = 2 × Σ qty × fee (paper.fills.total_fees_for_legs).
  * realized (closed) = entry_credit − exit_debit − fees_total
    (paper.pnl.trade_pnl_closed); exit fills at mid ± slip.

Thresholds come from settings — defaults are the source of truth everywhere
(intentionally NOT wired into compose):
  * OPTIONS_CANARY_MIN_CREDIT_MULTIPLE (2.0): entry_credit must be >= this
    multiple of (close_drag + fees_round_trip).
  * OPTIONS_CANARY_MIN_NET_REWARD_RISK (0.10): floor on
    (entry_credit − fees_round_trip) / max_loss.

Derivation of expected_tp_close_net_pnl: for a credit spread, gross
max_profit = entry_credit, so the GROSS TP trigger
(pct_max_profit >= tp_pct on mid-marks) first fires when
mid_cost = (1 − tp_pct) × entry_credit. The NET P&L of closing there is
    entry_credit − (mid_cost + close_drag) − fees_round_trip
  = tp_pct × entry_credit − close_drag − fees_round_trip.

Stdlib + Decimal only. Pure functions. No DB. No I/O. (Mirrors the purity
style of canary.lifecycle.decide_exit / paper.fills.)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from apps.api.src.options.paper.fills import DEFAULT_FEE_PER_CONTRACT

CONTRACT_MULTIPLIER = Decimal("100")
DEFAULT_SLIPPAGE_CAP = Decimal("0.05")

# Terminal (first-failing) viability reasons.
REASON_BELOW_MIN_VIABLE_CREDIT = "below_min_viable_credit"
REASON_TP_CLOSE_NET_NEGATIVE = "tp_close_net_negative"
REASON_NET_REWARD_RISK_BELOW_THRESHOLD = "net_reward_risk_below_threshold"


@dataclass(frozen=True)
class EconomicAssessment:
    entry_credit: Decimal
    fees_round_trip: Decimal
    close_drag: Decimal
    min_viable_credit: Decimal
    expected_tp_close_net_pnl: Decimal
    net_max_profit: Decimal
    net_reward_risk: Decimal | None   # None when max_loss is None/<=0
    viable: bool
    reason: str | None                # first failing check; None when viable


def _fees_round_trip(
    leg_qtys: Sequence[int], fee_per_contract: Decimal,
) -> Decimal:
    """Round-trip (open + close) fees across all legs — same formula as
    paper.fills.total_fees_for_legs."""
    return Decimal(2) * sum(
        (Decimal(q) * fee_per_contract for q in leg_qtys),
        start=Decimal("0"),
    )


def _close_drag(
    leg_half_spreads: Sequence[Decimal],
    leg_qtys: Sequence[int],
    slippage_cap: Decimal,
) -> Decimal:
    """Close-side slippage drag in dollars: Σ min(half_spread, cap)×100×qty.
    Same per-leg slip the fill model applies (mid ± min(half_spread, cap))."""
    if len(leg_half_spreads) != len(leg_qtys):
        raise ValueError("leg_half_spreads length must match leg_qtys")
    drag = Decimal("0")
    for hs, qty in zip(leg_half_spreads, leg_qtys):
        h = Decimal(str(hs))
        if h < 0:
            h = Decimal("0")
        if h > slippage_cap:
            h = slippage_cap
        drag += h * CONTRACT_MULTIPLIER * Decimal(qty)
    return drag


def expected_close_net_pnl(
    *,
    entry_credit: Decimal,
    current_mid_cost: Decimal,
    leg_half_spreads: Sequence[Decimal],
    leg_qtys: Sequence[int],
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
    slippage_cap: Decimal = DEFAULT_SLIPPAGE_CAP,
) -> Decimal:
    """Estimated NET realized P&L of closing NOW at the given gross mid cost:

        entry_credit − (current_mid_cost + close_drag) − fees_round_trip

    fees_round_trip covers the already-incurred OPEN fees plus the CLOSE-side
    fees (the trade's fees_total at close is round-trip — paper engine parity).
    """
    drag = _close_drag(leg_half_spreads, leg_qtys, slippage_cap)
    fees_rt = _fees_round_trip(leg_qtys, fee_per_contract)
    return entry_credit - (current_mid_cost + drag) - fees_rt


def assess_economics(
    *,
    entry_credit: Decimal,
    max_loss: Decimal,
    leg_half_spreads: list[Decimal],
    leg_qtys: list[int],
    tp_pct: float,
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
    slippage_cap: Decimal = Decimal("0.05"),
    min_credit_multiple: float,
    min_net_reward_risk: float,
) -> EconomicAssessment:
    """Structural economic viability of a credit spread at promotion time.

    viable = entry_credit >= min_viable_credit
             AND expected_tp_close_net_pnl > 0
             AND net_reward_risk >= min_net_reward_risk
    reason = first failing check (gate order above), else None.
    A None net_reward_risk (max_loss None/<=0 → no structural risk) passes
    the reward/risk check (0-safe; never divides by zero).
    """
    fees_rt = _fees_round_trip(leg_qtys, fee_per_contract)
    drag = _close_drag(leg_half_spreads, leg_qtys, slippage_cap)
    min_viable = Decimal(str(min_credit_multiple)) * (drag + fees_rt)
    net_max_profit = entry_credit - fees_rt
    tp_net = Decimal(str(tp_pct)) * entry_credit - drag - fees_rt

    net_rr: Decimal | None = None
    if max_loss is not None:
        ml = Decimal(str(max_loss))
        if ml > 0:
            net_rr = net_max_profit / ml

    reason: str | None = None
    if entry_credit < min_viable:
        reason = REASON_BELOW_MIN_VIABLE_CREDIT
    elif tp_net <= 0:
        reason = REASON_TP_CLOSE_NET_NEGATIVE
    elif net_rr is not None and net_rr < Decimal(str(min_net_reward_risk)):
        reason = REASON_NET_REWARD_RISK_BELOW_THRESHOLD

    return EconomicAssessment(
        entry_credit=entry_credit,
        fees_round_trip=fees_rt,
        close_drag=drag,
        min_viable_credit=min_viable,
        expected_tp_close_net_pnl=tp_net,
        net_max_profit=net_max_profit,
        net_reward_risk=net_rr,
        viable=reason is None,
        reason=reason,
    )
