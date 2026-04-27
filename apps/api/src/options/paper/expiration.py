"""Per-leg expiration payoff + classification (Phase 11E).

Computes settlement intrinsic value, classifies each leg as
OTM / ITM / PIN_RISK, and surfaces assignment risk for short ITM legs.

Pure-fn module. No DB. No I/O.

Pin-risk: |S − K| < PIN_RISK_BAND (frozen $0.05). Cash-settled and
European-style options never trigger pin-risk; v1 universe is American
ETF options where pin-risk is real.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from apps.api.src.options.paper.strategies import (
    CONTRACT_MULTIPLIER,
    LegSpec,
)


PIN_RISK_BAND_DOLLARS = Decimal("0.05")

CLASSIFICATION_OTM        = "OTM"
CLASSIFICATION_ITM        = "ITM"
CLASSIFICATION_PIN_RISK   = "PIN_RISK"
CLASSIFICATION_MISSING    = "MISSING_DATA"

# Flag tokens — surfaced into lifecycle payloads for downstream readers
FLAG_PIN_RISK_UNCERTAIN_OUTCOME = "PIN_RISK_UNCERTAIN_OUTCOME"
FLAG_ASSIGNMENT_SIMPLIFIED_EXIT = "ASSIGNMENT_SIMPLIFIED_EXIT"
FLAG_MISSING_SETTLEMENT          = "MISSING_SETTLEMENT"


@dataclass(frozen=True)
class LegExpirationOutcome:
    leg_index: int
    classification: str
    intrinsic_value_per_contract: Decimal | None
    payoff_dollars: Decimal | None
    assigned: bool                      # short leg ITM at settlement
    uncertain_outcome: bool = False     # set when classification == PIN_RISK


@dataclass(frozen=True)
class ExpirationOutcome:
    settlement_price: Decimal | None
    legs: tuple[LegExpirationOutcome, ...]
    total_payoff_dollars: Decimal       # sum of leg payoffs (settlement only)
    has_pin_risk: bool
    has_assignment: bool
    has_missing_data: bool
    flags: tuple[str, ...] = ()         # surfaced flag tokens (see FLAG_*)


def _intrinsic_per_contract(
    *,
    option_type: str,
    strike: Decimal,
    settlement: Decimal,
) -> Decimal:
    if option_type == "CALL":
        diff = settlement - strike
    else:
        diff = strike - settlement
    return diff if diff > 0 else Decimal("0")


def classify_leg(
    *,
    option_type: str,
    side: str,
    strike: Decimal,
    settlement: Decimal | None,
    pin_band: Decimal = PIN_RISK_BAND_DOLLARS,
) -> str:
    if settlement is None:
        return CLASSIFICATION_MISSING
    if abs(settlement - strike) < pin_band:
        return CLASSIFICATION_PIN_RISK
    intrinsic = _intrinsic_per_contract(
        option_type=option_type, strike=strike, settlement=settlement,
    )
    return CLASSIFICATION_ITM if intrinsic > 0 else CLASSIFICATION_OTM


def expire_legs(
    legs: Sequence[LegSpec],
    *,
    settlement_price: Decimal | None,
) -> ExpirationOutcome:
    """Apply expiration settlement to all legs in `legs` at the same expiry.

    Long ITM payoff  = +intrinsic × 100 × qty (you exercise, receive value).
    Short ITM payoff = −intrinsic × 100 × qty (you are assigned, owe value).
    OTM legs expire worthless on both sides.

    PIN_RISK: payoff is computed at intrinsic (deterministic), but the
    leg is also marked `uncertain_outcome=True` and a top-level
    `PIN_RISK_UNCERTAIN_OUTCOME` flag is added to surface the fact that
    the actual exercise/assignment decision is settlement-time-dependent
    and the recorded payoff is a model approximation only.

    ASSIGNMENT (any short ITM leg): the v1 paper engine does NOT create a
    synthetic equity position. Final PnL is taken at intrinsic and the
    `ASSIGNMENT_SIMPLIFIED_EXIT` flag is added to make this v1
    simplification explicit in the audit trail.
    """
    out: list[LegExpirationOutcome] = []
    total = Decimal("0")
    has_pin = False
    has_assign = False
    has_missing = False
    flags: list[str] = []
    for idx, leg in enumerate(legs):
        cls = classify_leg(
            option_type=leg.option_type, side=leg.side,
            strike=leg.strike, settlement=settlement_price,
        )
        if cls == CLASSIFICATION_PIN_RISK:
            has_pin = True
        if cls == CLASSIFICATION_MISSING:
            has_missing = True
            out.append(LegExpirationOutcome(
                leg_index=idx, classification=cls,
                intrinsic_value_per_contract=None,
                payoff_dollars=None, assigned=False,
                uncertain_outcome=False,
            ))
            continue
        intrinsic = _intrinsic_per_contract(
            option_type=leg.option_type,
            strike=leg.strike, settlement=settlement_price,
        )
        sign = Decimal("1") if leg.side == "BUY" else Decimal("-1")
        payoff = sign * intrinsic * CONTRACT_MULTIPLIER * Decimal(leg.qty)
        assigned = (leg.side == "SELL" and intrinsic > 0)
        if assigned:
            has_assign = True
        out.append(LegExpirationOutcome(
            leg_index=idx, classification=cls,
            intrinsic_value_per_contract=intrinsic,
            payoff_dollars=payoff, assigned=assigned,
            uncertain_outcome=(cls == CLASSIFICATION_PIN_RISK),
        ))
        total += payoff
    if has_pin:
        flags.append(FLAG_PIN_RISK_UNCERTAIN_OUTCOME)
    if has_assign:
        flags.append(FLAG_ASSIGNMENT_SIMPLIFIED_EXIT)
    if has_missing:
        flags.append(FLAG_MISSING_SETTLEMENT)
    return ExpirationOutcome(
        settlement_price=settlement_price,
        legs=tuple(out),
        total_payoff_dollars=total,
        has_pin_risk=has_pin,
        has_assignment=has_assign,
        has_missing_data=has_missing,
        flags=tuple(flags),
    )
