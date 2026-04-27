"""Strategy shape declarations + risk metric calculators (Phase 11E).

The paper-trading engine accepts a `TradeRequest` describing legs;
`strategies` validates that the legs match one of the v1 defined-risk
shapes and computes max_loss / max_profit / breakeven(s).

NEVER recommends a strategy. NEVER decides whether to open. Pure-fn
classification + risk math only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence


STRATEGY_SHORT_PUT_CREDIT_SPREAD  = "SHORT_PUT_CREDIT_SPREAD"
STRATEGY_SHORT_CALL_CREDIT_SPREAD = "SHORT_CALL_CREDIT_SPREAD"
STRATEGY_IRON_CONDOR              = "IRON_CONDOR"

DEFINED_RISK_STRATEGIES = (
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
    STRATEGY_SHORT_CALL_CREDIT_SPREAD,
    STRATEGY_IRON_CONDOR,
)

# Multiplier per equity option contract
CONTRACT_MULTIPLIER = Decimal("100")


@dataclass(frozen=True)
class LegSpec:
    """A single leg of a trade — entry/exit fills are computed elsewhere."""
    side: str             # "BUY" | "SELL"
    option_type: str      # "CALL" | "PUT"
    strike: Decimal
    expiry: object        # datetime.date — kept Object-typed to avoid import cycle
    qty: int              # contracts; > 0
    option_symbol: str


@dataclass(frozen=True)
class RiskMetrics:
    max_loss_dollars: Decimal       # always >= 0
    max_profit_dollars: Decimal     # always >= 0
    breakeven_lower: Decimal | None
    breakeven_upper: Decimal | None


def validate_defined_risk(
    strategy_name: str,
    legs: Sequence[LegSpec],
) -> None:
    """Raise ValueError if (strategy_name, legs) does not match a v1
    defined-risk shape. NEVER allows naked short legs.
    """
    if strategy_name not in DEFINED_RISK_STRATEGIES:
        raise ValueError(
            f"strategy {strategy_name!r} is not in v1 defined-risk universe; "
            f"allowed: {DEFINED_RISK_STRATEGIES}"
        )
    if any(leg.qty <= 0 for leg in legs):
        raise ValueError("all legs must have qty > 0")
    if any(leg.side not in ("BUY", "SELL") for leg in legs):
        raise ValueError("each leg side must be BUY or SELL")
    if any(leg.option_type not in ("CALL", "PUT") for leg in legs):
        raise ValueError("each leg option_type must be CALL or PUT")
    qtys = {leg.qty for leg in legs}
    if len(qtys) != 1:
        raise ValueError(
            "all legs must be the same qty for v1 defined-risk shapes"
        )
    expiries = {leg.expiry for leg in legs}
    if len(expiries) != 1:
        raise ValueError("all legs must share one expiry for v1")

    if strategy_name == STRATEGY_SHORT_PUT_CREDIT_SPREAD:
        _validate_credit_spread(legs, "PUT")
    elif strategy_name == STRATEGY_SHORT_CALL_CREDIT_SPREAD:
        _validate_credit_spread(legs, "CALL")
    elif strategy_name == STRATEGY_IRON_CONDOR:
        _validate_iron_condor(legs)


def _validate_credit_spread(legs: Sequence[LegSpec], opt: str) -> None:
    if len(legs) != 2:
        raise ValueError("credit spread requires exactly 2 legs")
    if any(leg.option_type != opt for leg in legs):
        raise ValueError(f"all legs must be {opt}")
    sells = [leg for leg in legs if leg.side == "SELL"]
    buys  = [leg for leg in legs if leg.side == "BUY"]
    if len(sells) != 1 or len(buys) != 1:
        raise ValueError("credit spread requires 1 SELL + 1 BUY (defined risk)")
    short, long_ = sells[0], buys[0]
    if opt == "PUT" and not (short.strike > long_.strike):
        raise ValueError("short put must be above long put (defined risk)")
    if opt == "CALL" and not (short.strike < long_.strike):
        raise ValueError("short call must be below long call (defined risk)")


def _validate_iron_condor(legs: Sequence[LegSpec]) -> None:
    if len(legs) != 4:
        raise ValueError("iron condor requires exactly 4 legs")
    puts  = sorted([leg for leg in legs if leg.option_type == "PUT"],
                   key=lambda l: l.strike)
    calls = sorted([leg for leg in legs if leg.option_type == "CALL"],
                   key=lambda l: l.strike)
    if len(puts) != 2 or len(calls) != 2:
        raise ValueError("iron condor needs 2 puts + 2 calls")
    long_put, short_put = puts[0], puts[1]
    short_call, long_call = calls[0], calls[1]
    if not (short_put.strike < short_call.strike):
        raise ValueError("iron condor short put must be below short call")
    if long_put.side != "BUY" or short_put.side != "SELL":
        raise ValueError("iron condor put wing: low-strike BUY, high-strike SELL")
    if short_call.side != "SELL" or long_call.side != "BUY":
        raise ValueError("iron condor call wing: low-strike SELL, high-strike BUY")


# ---------------------------------------------------------------------------
# Risk metrics
# ---------------------------------------------------------------------------

def compute_risk(
    strategy_name: str,
    legs: Sequence[LegSpec],
    entry_fill_prices: Sequence[Decimal],
) -> RiskMetrics:
    """Compute max_loss / max_profit / breakevens for a defined-risk
    strategy at the given entry fills (per-contract dollar prices).

    `entry_fill_prices[i]` corresponds to `legs[i]`.
    Net credit (positive) = SELL fills − BUY fills.
    """
    if len(entry_fill_prices) != len(legs):
        raise ValueError("entry_fill_prices length must match legs")
    if any(leg.qty <= 0 for leg in legs):
        raise ValueError("legs must have qty > 0")
    qty = legs[0].qty
    mult = CONTRACT_MULTIPLIER * Decimal(qty)
    net_credit_per_contract = sum(
        (
            (price if leg.side == "SELL" else -price)
            for leg, price in zip(legs, entry_fill_prices)
        ),
        start=Decimal("0"),
    )

    if strategy_name == STRATEGY_SHORT_PUT_CREDIT_SPREAD:
        short = next(l for l in legs if l.side == "SELL")
        long_ = next(l for l in legs if l.side == "BUY")
        width = short.strike - long_.strike
        max_loss = (width - net_credit_per_contract) * mult
        max_profit = net_credit_per_contract * mult
        breakeven_lower = short.strike - net_credit_per_contract
        breakeven_upper = None
    elif strategy_name == STRATEGY_SHORT_CALL_CREDIT_SPREAD:
        short = next(l for l in legs if l.side == "SELL")
        long_ = next(l for l in legs if l.side == "BUY")
        width = long_.strike - short.strike
        max_loss = (width - net_credit_per_contract) * mult
        max_profit = net_credit_per_contract * mult
        breakeven_upper = short.strike + net_credit_per_contract
        breakeven_lower = None
    elif strategy_name == STRATEGY_IRON_CONDOR:
        puts  = sorted([l for l in legs if l.option_type == "PUT"],  key=lambda l: l.strike)
        calls = sorted([l for l in legs if l.option_type == "CALL"], key=lambda l: l.strike)
        long_put, short_put = puts
        short_call, long_call = calls
        put_width  = short_put.strike  - long_put.strike
        call_width = long_call.strike  - short_call.strike
        # Both sides cannot lose simultaneously → max risk = max wing width − credit
        worst_width = put_width if put_width > call_width else call_width
        max_loss = (worst_width - net_credit_per_contract) * mult
        max_profit = net_credit_per_contract * mult
        breakeven_lower = short_put.strike  - net_credit_per_contract
        breakeven_upper = short_call.strike + net_credit_per_contract
    else:
        raise ValueError(f"unknown strategy {strategy_name!r}")

    if max_loss < 0:
        # Net credit exceeds width — degenerate input. Floor at 0.
        max_loss = Decimal("0")
    if max_profit < 0:
        max_profit = Decimal("0")
    return RiskMetrics(
        max_loss_dollars=max_loss,
        max_profit_dollars=max_profit,
        breakeven_lower=breakeven_lower,
        breakeven_upper=breakeven_upper,
    )


def net_credit_dollars(
    legs: Sequence[LegSpec],
    fills: Sequence[Decimal],
) -> Decimal:
    """Net credit RECEIVED at open (positive) or DEBIT paid (negative)."""
    if len(fills) != len(legs):
        raise ValueError("fills length must match legs")
    qty = legs[0].qty
    per_contract = sum(
        (
            (p if leg.side == "SELL" else -p)
            for leg, p in zip(legs, fills)
        ),
        start=Decimal("0"),
    )
    return per_contract * CONTRACT_MULTIPLIER * Decimal(qty)
