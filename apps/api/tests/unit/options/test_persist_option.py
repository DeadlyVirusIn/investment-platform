"""Phase Opt-B1 — persist_option() pure-function tests.

Hash + dataclass coverage. The DB UPSERT path is verified by
integration tests separately.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from apps.api.src.options.persist_option import (
    OptionLegSpec,
    OptionTradeProposal,
    proposal_hash,
)


def _make_leg(**overrides) -> OptionLegSpec:
    base = dict(
        leg_index=1,
        option_symbol="SPY260618C00440000",
        underlying="SPY",
        expiry=datetime.date(2026, 6, 18),
        strike=Decimal("440"),
        option_type="CALL",
        side="BUY",
        qty=1,
        multiplier=100,
        entry_fill_price=Decimal("1.25"),
    )
    base.update(overrides)
    return OptionLegSpec(**base)


def _make_proposal(**overrides) -> OptionTradeProposal:
    base = dict(
        underlying="SPY",
        strategy_name="LONG_CALL",
        strategy_version="v1.0",
        opened_at=datetime.datetime(2026, 5, 12, 21, 0,
                                    tzinfo=datetime.timezone.utc),
        legs=[_make_leg()],
        fill_model_version="mid_plus_25_pct_spread",
        entry_credit_dollars=Decimal("125.00"),
        max_loss_dollars=Decimal("125.00"),
        max_profit_dollars=Decimal("1000.00"),
        breakeven_lower=Decimal("441.25"),
        breakeven_upper=Decimal("441.25"),
        fees_total_dollars=Decimal("0"),
    )
    base.update(overrides)
    return OptionTradeProposal(**base)


# ---------------------------------------------------------------------------
# Hash stability
# ---------------------------------------------------------------------------


def test_hash_is_32_hex_chars():
    h = proposal_hash(_make_proposal())
    assert len(h) == 32
    int(h, 16)  # raises if non-hex


def test_hash_stable_for_identical_proposals():
    h1 = proposal_hash(_make_proposal())
    h2 = proposal_hash(_make_proposal())
    assert h1 == h2


def test_hash_stable_across_leg_order():
    """Caller may build legs in any order; hash MUST be identical."""
    a = _make_proposal(legs=[
        _make_leg(leg_index=1, option_symbol="SPY260618C00440000"),
        _make_leg(leg_index=2, option_symbol="SPY260618C00450000",
                  strike=Decimal("450"), side="SELL"),
    ])
    b = _make_proposal(legs=[
        # same legs, reversed list order
        _make_leg(leg_index=2, option_symbol="SPY260618C00450000",
                  strike=Decimal("450"), side="SELL"),
        _make_leg(leg_index=1, option_symbol="SPY260618C00440000"),
    ])
    assert proposal_hash(a) == proposal_hash(b)


# ---------------------------------------------------------------------------
# Hash invariance to quote-time fields (the core idempotency contract)
# ---------------------------------------------------------------------------


def test_hash_invariant_to_entry_credit_dollars():
    a = _make_proposal(entry_credit_dollars=Decimal("125.00"))
    b = _make_proposal(entry_credit_dollars=Decimal("130.00"))
    assert proposal_hash(a) == proposal_hash(b)


def test_hash_invariant_to_max_loss():
    a = _make_proposal(max_loss_dollars=Decimal("125"))
    b = _make_proposal(max_loss_dollars=Decimal("999"))
    assert proposal_hash(a) == proposal_hash(b)


def test_hash_invariant_to_leg_fill_price():
    a = _make_proposal(legs=[_make_leg(entry_fill_price=Decimal("1.25"))])
    b = _make_proposal(legs=[_make_leg(entry_fill_price=Decimal("9.99"))])
    assert proposal_hash(a) == proposal_hash(b)


def test_hash_invariant_to_leg_greeks_and_iv():
    a = _make_proposal(legs=[_make_leg(
        entry_iv=Decimal("0.20"), entry_delta=Decimal("0.30"),
        entry_gamma=Decimal("0.02"), entry_theta=Decimal("-0.05"),
        entry_vega=Decimal("0.10"),
    )])
    b = _make_proposal(legs=[_make_leg(
        entry_iv=Decimal("0.99"), entry_delta=Decimal("0.99"),
        entry_gamma=Decimal("0.99"), entry_theta=Decimal("-0.99"),
        entry_vega=Decimal("0.99"),
    )])
    assert proposal_hash(a) == proposal_hash(b)


def test_hash_invariant_to_fees():
    a = _make_proposal(fees_total_dollars=Decimal("0"))
    b = _make_proposal(fees_total_dollars=Decimal("5"))
    assert proposal_hash(a) == proposal_hash(b)


# ---------------------------------------------------------------------------
# Hash sensitivity to identity fields (the core dedup contract)
# ---------------------------------------------------------------------------


def test_hash_changes_on_underlying():
    a = _make_proposal(underlying="SPY")
    b = _make_proposal(underlying="QQQ")
    assert proposal_hash(a) != proposal_hash(b)


def test_hash_changes_on_strategy_name():
    a = _make_proposal(strategy_name="LONG_CALL")
    b = _make_proposal(strategy_name="BULL_CALL_SPREAD")
    assert proposal_hash(a) != proposal_hash(b)


def test_hash_changes_on_strategy_version():
    a = _make_proposal(strategy_version="v1.0")
    b = _make_proposal(strategy_version="v1.1")
    assert proposal_hash(a) != proposal_hash(b)


def test_hash_changes_on_opened_at_date():
    a = _make_proposal(opened_at=datetime.datetime(
        2026, 5, 12, 21, 0, tzinfo=datetime.timezone.utc,
    ))
    b = _make_proposal(opened_at=datetime.datetime(
        2026, 5, 13, 21, 0, tzinfo=datetime.timezone.utc,
    ))
    assert proposal_hash(a) != proposal_hash(b)


def test_hash_INVARIANT_to_opened_at_within_same_date():
    """Same calendar date but different HH:MM — hash MUST match (so two
    runs in the same trading session dedup)."""
    a = _make_proposal(opened_at=datetime.datetime(
        2026, 5, 12, 9, 0, tzinfo=datetime.timezone.utc,
    ))
    b = _make_proposal(opened_at=datetime.datetime(
        2026, 5, 12, 21, 30, tzinfo=datetime.timezone.utc,
    ))
    assert proposal_hash(a) == proposal_hash(b)


def test_hash_changes_on_leg_strike():
    a = _make_proposal(legs=[_make_leg(strike=Decimal("440"))])
    b = _make_proposal(legs=[_make_leg(strike=Decimal("441"))])
    assert proposal_hash(a) != proposal_hash(b)


def test_hash_changes_on_leg_expiry():
    a = _make_proposal(legs=[_make_leg(expiry=datetime.date(2026, 6, 18))])
    b = _make_proposal(legs=[_make_leg(expiry=datetime.date(2026, 7, 18))])
    assert proposal_hash(a) != proposal_hash(b)


def test_hash_changes_on_leg_option_type():
    a = _make_proposal(legs=[_make_leg(option_type="CALL")])
    b = _make_proposal(legs=[_make_leg(option_type="PUT")])
    assert proposal_hash(a) != proposal_hash(b)


def test_hash_changes_on_leg_side():
    a = _make_proposal(legs=[_make_leg(side="BUY")])
    b = _make_proposal(legs=[_make_leg(side="SELL")])
    assert proposal_hash(a) != proposal_hash(b)


def test_hash_changes_on_leg_qty():
    a = _make_proposal(legs=[_make_leg(qty=1)])
    b = _make_proposal(legs=[_make_leg(qty=2)])
    assert proposal_hash(a) != proposal_hash(b)


def test_hash_changes_on_fill_model_version():
    a = _make_proposal(fill_model_version="mid_plus_25_pct_spread")
    b = _make_proposal(fill_model_version="mid")
    assert proposal_hash(a) != proposal_hash(b)


# ---------------------------------------------------------------------------
# Case + canonicalization
# ---------------------------------------------------------------------------


def test_hash_invariant_to_underlying_case():
    a = _make_proposal(underlying="spy")
    b = _make_proposal(underlying="SPY")
    assert proposal_hash(a) == proposal_hash(b)


def test_hash_invariant_to_option_type_case():
    a = _make_proposal(legs=[_make_leg(option_type="call")])
    b = _make_proposal(legs=[_make_leg(option_type="CALL")])
    assert proposal_hash(a) == proposal_hash(b)


def test_hash_invariant_to_side_case():
    a = _make_proposal(legs=[_make_leg(side="buy")])
    b = _make_proposal(legs=[_make_leg(side="BUY")])
    assert proposal_hash(a) == proposal_hash(b)
