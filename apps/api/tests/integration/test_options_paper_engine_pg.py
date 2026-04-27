"""Phase 11E integration test — paper engine end-to-end against Postgres.

Verifies:
  * open_trade persists trade + legs + FILLED lifecycle event
  * record_mtm appends MTM event without changing fills/status
  * close_trade fills exits, records realized PnL, flips status to CLOSED
  * expire_trade settles per-leg, writes expiration_event rows,
    records ASSIGNED events for short ITM legs, flips status
  * paper_only=TRUE invariant remains intact
  * Engine inert when OPTIONS_ENABLED=False (kill switch)
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.config import settings
from apps.api.src.db.options_models import (  # noqa: F401 — register on Base
    OptionsAssignmentEvent,
    OptionsExpirationEvent,
    OptionsPaperTrade,
    OptionsPaperTradeLeg,
    OptionsTradeLifecycleEvent,
)
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.engine import (
    STATUS_ASSIGNED,
    STATUS_CLOSED,
    STATUS_OPEN,
    TradeRequest,
    close_trade,
    expire_trade,
    open_trade,
    record_mtm,
)
from apps.api.src.options.paper.strategies import (
    LegSpec,
    STRATEGY_IRON_CONDOR,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)


@pytest.fixture
def options_enabled(monkeypatch):
    """Flip the kill-switch on for this test only."""
    monkeypatch.setattr(settings, "OPTIONS_ENABLED", True)
    monkeypatch.setattr(settings, "OPTIONS_PAPER_ONLY", True)


def _quote(
    *, option_type, strike, expiry,
    bid=1.50, ask=1.55, oi=1000, vol=100,
    delta=-0.20, gamma=0.02, iv=0.20, age=2,
) -> OptionChainQuote:
    snap = dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc)
    mid = (bid + ask) / 2
    return OptionChainQuote(
        snapshot_at_utc=snap, underlying="SPY",
        expiry=expiry, strike=Decimal(str(strike)),
        option_type=option_type,
        option_symbol=f"SPY{expiry.strftime('%y%m%d')}{option_type[0]}{int(strike*1000):08d}",
        bid=Decimal(str(bid)), ask=Decimal(str(ask)),
        mid=Decimal(str(mid)), last=Decimal(str(bid)),
        volume=vol, open_interest=oi,
        delta=Decimal(str(delta)), gamma=Decimal(str(gamma)),
        theta=Decimal("-0.05"), vega=Decimal("0.10"),
        iv=Decimal(str(iv)), quote_age_seconds=age,
        provider="thetadata",
    )


def _spread_request() -> TradeRequest:
    expiry = dt.date(2026, 6, 18)
    short_put = _quote(option_type="PUT", strike=440, expiry=expiry,
                       bid=1.20, ask=1.25, delta=-0.30)
    long_put  = _quote(option_type="PUT", strike=435, expiry=expiry,
                       bid=0.50, ask=0.55, delta=-0.18)
    legs = (
        LegSpec(side="SELL", option_type="PUT",
                strike=Decimal("440"), expiry=expiry, qty=1,
                option_symbol=short_put.option_symbol),
        LegSpec(side="BUY",  option_type="PUT",
                strike=Decimal("435"), expiry=expiry, qty=1,
                option_symbol=long_put.option_symbol),
    )
    return TradeRequest(
        underlying="SPY",
        strategy_name=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        strategy_version="v1.0",
        legs=legs,
        quotes_by_symbol={
            short_put.option_symbol: short_put,
            long_put.option_symbol:  long_put,
        },
        rationale_note="test fixture",
    )


def _iron_condor_request() -> TradeRequest:
    expiry = dt.date(2026, 6, 18)
    long_put   = _quote(option_type="PUT",  strike=425, expiry=expiry,
                        bid=0.30, ask=0.35, delta=-0.10)
    short_put  = _quote(option_type="PUT",  strike=440, expiry=expiry,
                        bid=1.20, ask=1.25, delta=-0.30)
    short_call = _quote(option_type="CALL", strike=460, expiry=expiry,
                        bid=1.10, ask=1.15, delta=0.30)
    long_call  = _quote(option_type="CALL", strike=465, expiry=expiry,
                        bid=0.40, ask=0.45, delta=0.18)
    legs = (
        LegSpec(side="BUY",  option_type="PUT",
                strike=Decimal("425"), expiry=expiry, qty=1,
                option_symbol=long_put.option_symbol),
        LegSpec(side="SELL", option_type="PUT",
                strike=Decimal("440"), expiry=expiry, qty=1,
                option_symbol=short_put.option_symbol),
        LegSpec(side="SELL", option_type="CALL",
                strike=Decimal("460"), expiry=expiry, qty=1,
                option_symbol=short_call.option_symbol),
        LegSpec(side="BUY",  option_type="CALL",
                strike=Decimal("465"), expiry=expiry, qty=1,
                option_symbol=long_call.option_symbol),
    )
    return TradeRequest(
        underlying="SPY",
        strategy_name=STRATEGY_IRON_CONDOR,
        strategy_version="v1.0",
        legs=legs,
        quotes_by_symbol={
            long_put.option_symbol:   long_put,
            short_put.option_symbol:  short_put,
            short_call.option_symbol: short_call,
            long_call.option_symbol:  long_call,
        },
    )


# ===========================================================================
# OPEN
# ===========================================================================

def test_open_credit_spread_persists_trade_and_legs(
    pg_session, session_factory, options_enabled,
):
    req = _spread_request()
    res = open_trade(req, session_factory=session_factory)
    assert res.accepted is True
    assert res.trade_id is not None

    trade = pg_session.execute(text(
        "SELECT id, status, strategy_name, paper_only, "
        "       max_loss_dollars, max_profit_dollars, "
        "       breakeven_lower, fill_model_version "
        "FROM options_paper_trade WHERE id = :id"
    ), {"id": res.trade_id}).one()
    assert trade.status == STATUS_OPEN
    assert trade.strategy_name == STRATEGY_SHORT_PUT_CREDIT_SPREAD
    assert trade.paper_only is True
    assert trade.max_loss_dollars > 0
    assert trade.max_profit_dollars > 0
    assert trade.fill_model_version == "v1.conservative"

    legs = pg_session.execute(text(
        "SELECT leg_index, side, option_type, qty, entry_fill_price "
        "FROM options_paper_trade_leg WHERE trade_id = :id ORDER BY leg_index"
    ), {"id": res.trade_id}).all()
    assert len(legs) == 2
    assert legs[0].side == "SELL" and legs[1].side == "BUY"

    events = pg_session.execute(text(
        "SELECT event_type FROM options_trade_lifecycle_event "
        "WHERE trade_id = :id"
    ), {"id": res.trade_id}).all()
    assert any(e.event_type == "FILLED" for e in events)


def test_open_iron_condor_uses_widest_wing_for_max_loss(
    pg_session, session_factory, options_enabled,
):
    req = _iron_condor_request()
    res = open_trade(req, session_factory=session_factory)
    assert res.accepted is True
    # put width = 15, call width = 5 → widest = 15
    # net credit roughly 1.10 + 1.05 - 0.325 - 0.425 ≈ 1.40 → max_loss = (15-1.40)*100
    trade = pg_session.execute(text(
        "SELECT max_loss_dollars FROM options_paper_trade WHERE id=:id"
    ), {"id": res.trade_id}).one()
    assert trade.max_loss_dollars > Decimal("1300")
    assert trade.max_loss_dollars < Decimal("1400")


def test_open_rejects_naked_short(pg_session, session_factory, options_enabled):
    expiry = dt.date(2026, 6, 18)
    naked = _quote(option_type="PUT", strike=440, expiry=expiry,
                   bid=1.20, ask=1.25)
    req = TradeRequest(
        underlying="SPY",
        strategy_name=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        strategy_version="v1.0",
        legs=(LegSpec(side="SELL", option_type="PUT",
                      strike=Decimal("440"), expiry=expiry, qty=1,
                      option_symbol=naked.option_symbol),),
        quotes_by_symbol={naked.option_symbol: naked},
    )
    res = open_trade(req, session_factory=session_factory)
    assert res.accepted is False
    assert any("NOT_DEFINED_RISK" in r for r in res.rejected_reasons)
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_paper_trade"
    )).scalar_one()
    assert n == 0


def test_open_inert_when_kill_switch_disabled(
    pg_session, session_factory, monkeypatch,
):
    monkeypatch.setattr(settings, "OPTIONS_ENABLED", False)
    res = open_trade(_spread_request(), session_factory=session_factory)
    assert res.accepted is False
    assert "OPTIONS_PAPER_ONLY_DISABLED" in res.rejected_reasons


# ===========================================================================
# MTM
# ===========================================================================

def test_record_mtm_appends_event(pg_session, session_factory, options_enabled):
    req = _spread_request()
    open_res = open_trade(req, session_factory=session_factory)

    # Movement: prices halved → spread is profitable to close
    expiry = dt.date(2026, 6, 18)
    new_short = _quote(option_type="PUT", strike=440, expiry=expiry,
                       bid=0.60, ask=0.65)
    new_long  = _quote(option_type="PUT", strike=435, expiry=expiry,
                       bid=0.25, ask=0.30)
    quotes = {new_short.option_symbol: new_short,
              new_long.option_symbol:  new_long}

    out = record_mtm(
        open_res.trade_id, quotes_by_symbol=quotes,
        session_factory=session_factory,
    )
    assert out["accepted"] is True
    n_mtm = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_trade_lifecycle_event "
        "WHERE trade_id = :id AND event_type = 'MTM'"
    ), {"id": open_res.trade_id}).scalar_one()
    assert n_mtm == 1
    # Status unchanged
    status = pg_session.execute(text(
        "SELECT status FROM options_paper_trade WHERE id = :id"
    ), {"id": open_res.trade_id}).scalar_one()
    assert status == STATUS_OPEN


# ===========================================================================
# CLOSE pre-expiry
# ===========================================================================

def test_close_credit_spread_records_realized_pnl(
    pg_session, session_factory, options_enabled,
):
    req = _spread_request()
    open_res = open_trade(req, session_factory=session_factory)

    expiry = dt.date(2026, 6, 18)
    close_short = _quote(option_type="PUT", strike=440, expiry=expiry,
                         bid=0.60, ask=0.65)
    close_long  = _quote(option_type="PUT", strike=435, expiry=expiry,
                         bid=0.25, ask=0.30)
    out = close_trade(
        open_res.trade_id,
        quotes_by_symbol={
            close_short.option_symbol: close_short,
            close_long.option_symbol:  close_long,
        },
        reason="TAKE_PROFIT_50PCT",
        session_factory=session_factory,
    )
    assert out["accepted"] is True

    trade = pg_session.execute(text(
        "SELECT status, realized_pnl_dollars, exit_debit_dollars "
        "FROM options_paper_trade WHERE id = :id"
    ), {"id": open_res.trade_id}).one()
    assert trade.status == STATUS_CLOSED
    assert trade.realized_pnl_dollars > 0     # profit at half-credit
    assert trade.exit_debit_dollars > 0
    # Both legs have exit_fill_price populated
    legs = pg_session.execute(text(
        "SELECT exit_fill_price FROM options_paper_trade_leg "
        "WHERE trade_id = :id"
    ), {"id": open_res.trade_id}).all()
    assert all(l.exit_fill_price is not None for l in legs)


# ===========================================================================
# EXPIRE — credit spread settles past long strike → max loss
# ===========================================================================

def test_expire_credit_spread_at_max_loss_with_assignment(
    pg_session, session_factory, options_enabled,
):
    req = _spread_request()
    open_res = open_trade(req, session_factory=session_factory)
    out = expire_trade(
        open_res.trade_id,
        settlement_price=Decimal("420"),    # both legs ITM
        session_factory=session_factory,
    )
    assert out["accepted"] is True
    assert out["status"] == STATUS_ASSIGNED      # short put ITM → assignment
    assert out["has_assignment"] is True
    assert "ASSIGNMENT_SIMPLIFIED_EXIT" in out["flags"]

    trade = pg_session.execute(text(
        "SELECT status, realized_pnl_dollars, fees_total_dollars "
        "FROM options_paper_trade WHERE id = :id"
    ), {"id": open_res.trade_id}).one()
    assert trade.status == STATUS_ASSIGNED
    assert trade.realized_pnl_dollars < 0     # max loss territory
    # Round-trip fees on expiry → fees_total > 2 × per-leg open fees alone
    assert trade.fees_total_dollars >= Decimal("2.80")     # 4 fills × $0.70

    n_exp = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_expiration_event WHERE trade_id = :id"
    ), {"id": open_res.trade_id}).scalar_one()
    assert n_exp == 2

    assign = pg_session.execute(text(
        "SELECT event_type, notes FROM options_assignment_event "
        "WHERE trade_id = :id"
    ), {"id": open_res.trade_id}).one()
    assert assign.event_type == "ASSIGNED"
    assert "ASSIGNMENT_SIMPLIFIED_EXIT" in assign.notes
    assert "no synthetic equity position" in assign.notes


# ===========================================================================
# EXPIRE — iron condor in profit zone → all OTM, full credit kept
# ===========================================================================

def test_expire_iron_condor_in_profit_zone_all_otm(
    pg_session, session_factory, options_enabled,
):
    req = _iron_condor_request()
    open_res = open_trade(req, session_factory=session_factory)
    out = expire_trade(
        open_res.trade_id,
        settlement_price=Decimal("450"),    # between short strikes
        session_factory=session_factory,
    )
    assert out["accepted"] is True
    assert out["status"] == "EXPIRED"           # no assignment
    assert out["has_assignment"] is False

    rows = pg_session.execute(text(
        "SELECT classification FROM options_expiration_event "
        "WHERE trade_id = :id ORDER BY leg_index"
    ), {"id": open_res.trade_id}).all()
    assert {r.classification for r in rows} == {"OTM"}

    trade = pg_session.execute(text(
        "SELECT realized_pnl_dollars FROM options_paper_trade "
        "WHERE id = :id"
    ), {"id": open_res.trade_id}).one()
    # Credit minus open-side fees → strictly positive but small
    assert trade.realized_pnl_dollars > 0


# ===========================================================================
# Re-close / re-expire is a safe no-op
# ===========================================================================

def test_expire_pin_risk_settlement_surfaces_uncertainty_flag(
    pg_session, session_factory, options_enabled,
):
    """Settlement within $0.05 of a strike → PIN_RISK_UNCERTAIN_OUTCOME
    flag in the lifecycle event payload + on the result dict."""
    req = _spread_request()
    open_res = open_trade(req, session_factory=session_factory)
    out = expire_trade(
        open_res.trade_id,
        settlement_price=Decimal("440.02"),    # within pin band of short strike
        session_factory=session_factory,
    )
    assert out["accepted"] is True
    assert out["has_pin_risk"] is True
    assert "PIN_RISK_UNCERTAIN_OUTCOME" in out["flags"]

    payload = pg_session.execute(text(
        "SELECT payload_json FROM options_trade_lifecycle_event "
        "WHERE trade_id = :id AND event_type IN ('EXPIRED', 'ASSIGNED') "
        "ORDER BY id DESC LIMIT 1"
    ), {"id": open_res.trade_id}).scalar_one()
    assert "PIN_RISK_UNCERTAIN_OUTCOME" in payload["flags"]
    assert payload["has_pin_risk"] is True


def test_expire_iron_condor_records_round_trip_fees_in_lifecycle(
    pg_session, session_factory, options_enabled,
):
    """Held-to-expiry charges close-side fees (no zero-cost exit advantage)."""
    req = _iron_condor_request()
    open_res = open_trade(req, session_factory=session_factory)
    out = expire_trade(
        open_res.trade_id, settlement_price=Decimal("450"),
        session_factory=session_factory,
    )
    assert out["accepted"] is True
    open_only_fees = Decimal("4") * Decimal("0.70")
    rt_fees = Decimal(out["fees_total_dollars"])
    assert rt_fees > open_only_fees
    assert rt_fees == Decimal("2") * open_only_fees       # exact round-trip parity


def test_close_after_terminal_state_is_rejected(
    pg_session, session_factory, options_enabled,
):
    req = _spread_request()
    open_res = open_trade(req, session_factory=session_factory)
    expire_trade(
        open_res.trade_id, settlement_price=Decimal("450"),
        session_factory=session_factory,
    )
    expiry = dt.date(2026, 6, 18)
    out = close_trade(
        open_res.trade_id,
        quotes_by_symbol={
            req.legs[0].option_symbol:
                _quote(option_type="PUT", strike=440, expiry=expiry,
                       bid=0.10, ask=0.15),
            req.legs[1].option_symbol:
                _quote(option_type="PUT", strike=435, expiry=expiry,
                       bid=0.05, ask=0.10),
        },
        reason="OPERATOR_CLOSE",
        session_factory=session_factory,
    )
    assert out["accepted"] is False
    assert out["reason"] == "TRADE_TERMINAL"
