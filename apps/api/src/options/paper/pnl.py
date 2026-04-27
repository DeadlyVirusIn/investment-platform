"""PnL calculations for paper trades (Phase 11E).

Pure-fn module. No DB.

Conventions
-----------
* Per-leg open: SELL receives `entry_fill_price × 100 × qty` (credit);
  BUY pays the same amount as a debit (negative cash).
* Per-leg close: SELL leg closed by BUYING back at exit_fill_price;
  BUY leg closed by SELLING at exit_fill_price.
* Closed-pre-expiry PnL = entry_credit − exit_debit − fees
* Held-to-expiry  PnL  = entry_credit + Σ leg_payoff_at_expiry − fees
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from apps.api.src.options.paper.strategies import CONTRACT_MULTIPLIER, LegSpec


@dataclass(frozen=True)
class LegPnL:
    leg_index: int
    open_cash_flow_dollars: Decimal       # +credit / −debit
    close_cash_flow_dollars: Decimal | None
    realized_pnl_dollars: Decimal | None  # close + open − leg_fees, only when closed/expired


@dataclass(frozen=True)
class TradePnL:
    entry_credit_dollars: Decimal         # +credit / −debit (sum of opens)
    exit_debit_dollars: Decimal | None    # +cost-to-close (sum of closes; None if open)
    expiration_payoff_dollars: Decimal | None  # used when held-to-expiry
    fees_total_dollars: Decimal
    realized_pnl_dollars: Decimal | None
    legs: tuple[LegPnL, ...]


def open_cash_flow_for_leg(
    leg: LegSpec,
    entry_fill_price: Decimal,
) -> Decimal:
    """Cash received (positive) or paid (negative) at open of one leg."""
    sign = Decimal("1") if leg.side == "SELL" else Decimal("-1")
    return sign * entry_fill_price * CONTRACT_MULTIPLIER * Decimal(leg.qty)


def close_cash_flow_for_leg(
    leg: LegSpec,
    exit_fill_price: Decimal,
) -> Decimal:
    """Cash received (+) or paid (−) when closing the leg pre-expiry.
    Closing a SELL means BUYING back (cash out, negative).
    Closing a BUY  means SELLING (cash in, positive).
    """
    sign = Decimal("-1") if leg.side == "SELL" else Decimal("1")
    return sign * exit_fill_price * CONTRACT_MULTIPLIER * Decimal(leg.qty)


def trade_pnl_closed(
    legs: Sequence[LegSpec],
    entry_fills: Sequence[Decimal],
    exit_fills: Sequence[Decimal],
    fees_total_dollars: Decimal,
) -> TradePnL:
    """Closed-pre-expiry PnL.  realized = entry_credit + close_cf − fees."""
    if len(entry_fills) != len(legs) or len(exit_fills) != len(legs):
        raise ValueError("entry_fills + exit_fills must match legs length")
    leg_results: list[LegPnL] = []
    entry_credit = Decimal("0")
    exit_debit = Decimal("0")
    for i, leg in enumerate(legs):
        opn = open_cash_flow_for_leg(leg, entry_fills[i])
        cls = close_cash_flow_for_leg(leg, exit_fills[i])
        entry_credit += opn
        # exit_debit positive when we paid cash to close
        exit_debit += -cls
        leg_results.append(LegPnL(
            leg_index=i,
            open_cash_flow_dollars=opn,
            close_cash_flow_dollars=cls,
            realized_pnl_dollars=opn + cls,    # fees aggregated at trade level
        ))
    realized = entry_credit - exit_debit - fees_total_dollars
    return TradePnL(
        entry_credit_dollars=entry_credit,
        exit_debit_dollars=exit_debit,
        expiration_payoff_dollars=None,
        fees_total_dollars=fees_total_dollars,
        realized_pnl_dollars=realized,
        legs=tuple(leg_results),
    )


def trade_pnl_expired(
    legs: Sequence[LegSpec],
    entry_fills: Sequence[Decimal],
    *,
    settlement_payoffs_per_leg: Sequence[Decimal],
    fees_total_dollars: Decimal,
) -> TradePnL:
    """Held-to-expiry PnL.

    realized = entry_credit + Σ leg_payoff_at_expiry − fees

    `fees_total_dollars` must reflect the orchestrator's fee model. The
    Phase 11E engine charges round-trip fees on expiry (open + close
    commissions parity with `trade_pnl_closed`) so held-to-expiry trades
    do NOT receive an optimistic zero-cost-exit advantage.
    """
    if len(entry_fills) != len(legs):
        raise ValueError("entry_fills must match legs length")
    if len(settlement_payoffs_per_leg) != len(legs):
        raise ValueError("settlement_payoffs_per_leg must match legs length")
    leg_results: list[LegPnL] = []
    entry_credit = Decimal("0")
    payoff_total = Decimal("0")
    for i, leg in enumerate(legs):
        opn = open_cash_flow_for_leg(leg, entry_fills[i])
        entry_credit += opn
        payoff = Decimal(settlement_payoffs_per_leg[i])
        payoff_total += payoff
        leg_results.append(LegPnL(
            leg_index=i,
            open_cash_flow_dollars=opn,
            close_cash_flow_dollars=payoff,    # treat settlement as the close
            realized_pnl_dollars=opn + payoff,
        ))
    realized = entry_credit + payoff_total - fees_total_dollars
    return TradePnL(
        entry_credit_dollars=entry_credit,
        exit_debit_dollars=None,
        expiration_payoff_dollars=payoff_total,
        fees_total_dollars=fees_total_dollars,
        realized_pnl_dollars=realized,
        legs=tuple(leg_results),
    )


@dataclass(frozen=True)
class GreeksSnapshot:
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None


def aggregate_greeks(
    legs: Sequence[LegSpec],
    leg_greeks: Sequence[GreeksSnapshot],
) -> GreeksSnapshot:
    """Aggregate Greeks across legs, signed by side.
    SELL legs contribute with negative sign (short delta/gamma/theta/vega).
    """
    if len(leg_greeks) != len(legs):
        raise ValueError("leg_greeks length must match legs")

    def _sum(getter):
        total = Decimal("0")
        any_present = False
        for leg, g in zip(legs, leg_greeks):
            v = getter(g)
            if v is None:
                continue
            sign = Decimal("1") if leg.side == "BUY" else Decimal("-1")
            total += sign * v * Decimal(leg.qty)
            any_present = True
        return total if any_present else None

    return GreeksSnapshot(
        delta=_sum(lambda g: g.delta),
        gamma=_sum(lambda g: g.gamma),
        theta=_sum(lambda g: g.theta),
        vega=_sum(lambda g: g.vega),
    )
