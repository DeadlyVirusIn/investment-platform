"""Unit tests for `_build_legs_payload` in
`scripts.run_options_paper_exec`.

Pure-function coverage. No DB. Validates that the dict produced
matches `OptionsPaperTradeLeg`'s column kwargs exactly so the
spread can be inserted without TypeError or NOT-NULL violations.

Background: the previous implementation emitted
`fill_price_dollars` (no such column) and never populated
`entry_quote_at_utc` (NOT NULL). Both issues blocked every
options paper INSERT — Phase A fixes that.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from apps.api.src.db.options_models import OptionsPaperTradeLeg
from scripts.run_options_paper_exec import _build_legs_payload


_QUOTE_TS = dt.datetime(2026, 5, 4, 21, 0, tzinfo=dt.timezone.utc)


def _suggestion_leg(
    *, action: str = "buy", option_type: str = "call",
    strike: float = 200.0, bid: float | None = 4.5,
    ask: float | None = 5.0, mid: float | None = 4.75,
    iv: float | None = 0.32, expiry: str = "2026-06-18",
    option_symbol: str = "TEST260618C00200000",
) -> dict:
    """Mirrors the shape returned by `_leg_dict` in
    `apps/api/src/api/performance_paper.py`."""
    return {
        "type": option_type,
        "strike": strike,
        "action": action,
        "option_symbol": option_symbol,
        "expiry": expiry,
        "bid": bid, "ask": ask, "mid": mid,
        "open_interest": 100,
        "iv": iv,
        "liquidity_score": 0.85,
    }


def test_bull_call_spread_builds_two_legs_with_required_fields():
    legs = [
        _suggestion_leg(action="buy",  strike=200, bid=4.5, ask=5.0,
                        option_symbol="X260618C00200000"),
        _suggestion_leg(action="sell", strike=210, bid=2.0, ask=2.3,
                        option_symbol="X260618C00210000"),
    ]
    payload = _build_legs_payload(
        "bull_call_spread", legs, qty=1,
        entry_quote_at_utc=_QUOTE_TS,
    )
    assert len(payload) == 2
    buy, sell = payload
    # Indices preserved in input order.
    assert buy["leg_index"] == 0 and sell["leg_index"] == 1
    # Side normalised to upper-case enum.
    assert buy["side"] == "BUY"
    assert sell["side"] == "SELL"
    # Option type upper-case.
    assert buy["option_type"] == "CALL"
    # Required NOT-NULL fields populated.
    assert buy["entry_quote_at_utc"] == _QUOTE_TS
    assert sell["entry_quote_at_utc"] == _QUOTE_TS
    assert buy["entry_fill_price"] == Decimal("5.0")   # ask for buy
    assert sell["entry_fill_price"] == Decimal("2.0")  # bid for sell
    # Optional snapshot fields propagated.
    assert buy["entry_bid"] == Decimal("4.5")
    assert buy["entry_ask"] == Decimal("5.0")
    assert buy["entry_mid"] == Decimal("4.75")
    assert buy["entry_iv"] == Decimal("0.32")


def test_long_call_builds_single_buy_leg():
    legs = [_suggestion_leg(action="buy", bid=4.0, ask=4.2)]
    payload = _build_legs_payload(
        "long_call", legs, qty=1, entry_quote_at_utc=_QUOTE_TS,
    )
    assert len(payload) == 1
    leg = payload[0]
    assert leg["side"] == "BUY"
    assert leg["entry_fill_price"] == Decimal("4.2")  # ask


def test_qty_propagates_to_each_leg():
    legs = [
        _suggestion_leg(action="buy"),
        _suggestion_leg(action="sell"),
    ]
    payload = _build_legs_payload(
        "bull_call_spread", legs, qty=3,
        entry_quote_at_utc=_QUOTE_TS,
    )
    assert all(p["qty"] == 3 for p in payload)


@pytest.mark.parametrize("missing_key", [
    "option_symbol", "expiry", "strike", "type", "action",
])
def test_missing_required_field_raises_clear_value_error(missing_key):
    legs = [_suggestion_leg(action="buy")]
    legs[0][missing_key] = None
    with pytest.raises(ValueError) as exc:
        _build_legs_payload(
            "long_call", legs, qty=1, entry_quote_at_utc=_QUOTE_TS,
        )
    # Error message names the missing field — operator-friendly.
    assert missing_key in str(exc.value)


def test_buy_with_null_ask_rejected_no_fabrication():
    legs = [_suggestion_leg(action="buy", ask=None)]
    with pytest.raises(ValueError, match="ask"):
        _build_legs_payload(
            "long_call", legs, qty=1, entry_quote_at_utc=_QUOTE_TS,
        )


def test_sell_with_null_bid_rejected_no_fabrication():
    legs = [_suggestion_leg(action="sell", bid=None)]
    with pytest.raises(ValueError, match="bid"):
        _build_legs_payload(
            "bull_call_spread", legs, qty=1,
            entry_quote_at_utc=_QUOTE_TS,
        )


def test_bad_action_rejected():
    legs = [_suggestion_leg(action="hold")]
    with pytest.raises(ValueError, match="action"):
        _build_legs_payload(
            "long_call", legs, qty=1, entry_quote_at_utc=_QUOTE_TS,
        )


def test_bad_option_type_rejected():
    legs = [_suggestion_leg(action="buy")]
    legs[0]["type"] = "future"
    with pytest.raises(ValueError, match="CALL/PUT"):
        _build_legs_payload(
            "long_call", legs, qty=1, entry_quote_at_utc=_QUOTE_TS,
        )


def test_payload_kwargs_match_orm_columns_no_typeerror():
    """Regression: previously the dict carried `fill_price_dollars`
    (not a column), so `OptionsPaperTradeLeg(trade_id=…, **lp)`
    raised TypeError before ever reaching the DB. Instantiating
    the ORM object without committing must succeed now."""
    legs = [_suggestion_leg(action="buy")]
    payload = _build_legs_payload(
        "long_call", legs, qty=1, entry_quote_at_utc=_QUOTE_TS,
    )
    lp = {**payload[0], "underlying": "TEST"}
    # Should NOT raise — every key is a real column.
    obj = OptionsPaperTradeLeg(trade_id=1, **lp)
    assert obj.option_symbol == "TEST260618C00200000"
    assert obj.entry_quote_at_utc == _QUOTE_TS
    assert obj.entry_fill_price == Decimal("5.0")


def test_no_greek_columns_set_when_chain_lacks_them():
    """Suggestion legs do NOT carry delta/gamma/theta/vega today.
    The payload should leave those columns absent (NULL on
    insert) — never invented."""
    legs = [_suggestion_leg(action="buy")]
    payload = _build_legs_payload(
        "long_call", legs, qty=1, entry_quote_at_utc=_QUOTE_TS,
    )
    for greek in ("entry_delta", "entry_gamma",
                  "entry_theta", "entry_vega"):
        assert greek not in payload[0], (
            f"{greek} must not be set when chain lacks greeks; "
            f"insertion-time default keeps the column NULL"
        )
