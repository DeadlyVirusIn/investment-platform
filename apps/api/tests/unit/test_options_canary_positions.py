"""Phase P6A — pure unit coverage for canary capital/identity helpers."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.options.canary import positions as pos
from apps.api.src.options.canary.engine import _release_reason
from apps.api.src.options.paper.fills import DEFAULT_FEE_PER_CONTRACT
from apps.api.src.options.paper.strategies import LegSpec

EXPIRY = dt.date(2026, 7, 18)


def _legs(qty=1):
    return [
        LegSpec(side="SELL", option_type="PUT", strike=Decimal("440"),
                expiry=EXPIRY, qty=qty, option_symbol="A"),
        LegSpec(side="BUY", option_type="PUT", strike=Decimal("435"),
                expiry=EXPIRY, qty=qty, option_symbol="B"),
    ]


def _hash(**over):
    base = dict(portfolio_id="pf-1", run_date=dt.date(2026, 6, 4),
                underlying="SPY", strategy_name="SHORT_PUT_CREDIT_SPREAD",
                strategy_version="v1", legs=_legs())
    base.update(over)
    return pos.proposal_hash(**base)


def test_proposal_hash_deterministic_and_order_independent():
    h1 = _hash()
    h2 = _hash(legs=list(reversed(_legs())))  # leg order must not matter
    assert h1 == h2 and len(h1) == 64


def test_proposal_hash_scoping():
    base = _hash()
    assert _hash(run_date=dt.date(2026, 6, 5)) != base   # next day differs
    assert _hash(portfolio_id="pf-2") != base            # portfolio differs
    legs = [LegSpec(side="SELL", option_type="PUT", strike=Decimal("441"),
                    expiry=EXPIRY, qty=1, option_symbol="A"), _legs()[1]]
    assert _hash(legs=legs) != base                       # structure differs


def test_fee_buffer_is_round_trip():
    # 2 legs × qty 1 → 2 × (1×fee + 1×fee) = 4 × fee
    assert pos.fee_buffer(_legs()) == Decimal("4") * DEFAULT_FEE_PER_CONTRACT


def test_reserved_capital_adds_fee_buffer():
    r = pos.reserved_capital(max_loss_dollars=Decimal("165"), legs=_legs())
    assert r == Decimal("165") + Decimal("4") * DEFAULT_FEE_PER_CONTRACT


def test_release_reason_mapping():
    assert _release_reason("close", {"accepted": True}, "CLOSED_TAKE_PROFIT") == "CLOSED_TAKE_PROFIT"
    assert _release_reason("close", {"accepted": True}, None) == "CLOSED_OPERATOR"
    assert _release_reason("expire", {"status": "ASSIGNED"}, None) == "ASSIGNED"
    assert _release_reason("expire", {"status": "EXPIRED", "has_assignment": True}, None) == "EXPIRED_ITM"
    assert _release_reason("expire", {"status": "EXPIRED", "has_assignment": False}, None) == "EXPIRED_OTM"
