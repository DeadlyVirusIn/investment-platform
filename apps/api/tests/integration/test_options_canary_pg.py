"""Phase P6A integration tests — canary promotion/lifecycle vs Postgres.

Covers the red-team must-fix matrix end-to-end:
  * TXN-OPEN: promote_one reserves capital + debits cash atomically
  * slot-cap enforcement (advisory-locked COUNT)
  * over-capital-cap rejection (no position, cash untouched)
  * proposal_hash duplicate via begin_nested SAVEPOINT (outer txn survives)
  * TXN-RELEASE: release_one credits cash; rowcount-guarded idempotency
  * reconcile ordering: orphan-position heal before drift; no false drift
  * injected-session: no commit until the caller commits (commit discipline)

Marked `integration` — needs Docker/testcontainers (or TEST_DATABASE_URL to a
NON-prod db). Paper-only; touches only options_* tables.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.config import settings
from apps.api.src.options.canary import engine as canary_engine
from apps.api.src.options.canary import positions as pos
from apps.api.src.options.canary import reconcile
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.engine import TradeRequest, open_trade
from apps.api.src.options.paper.strategies import (
    LegSpec,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
)

pytestmark = pytest.mark.integration

EXPIRY = dt.date(2026, 7, 18)
NOW = dt.datetime(2026, 6, 4, 22, 0, tzinfo=dt.timezone.utc)
RUN_DATE = dt.date(2026, 6, 4)


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)


@pytest.fixture
def options_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OPTIONS_ENABLED", True)
    monkeypatch.setattr(settings, "OPTIONS_PAPER_ONLY", True)


def _quote(*, option_type, strike, bid, ask, delta):
    mid = (bid + ask) / 2
    return OptionChainQuote(
        snapshot_at_utc=NOW, underlying="SPY", expiry=EXPIRY,
        strike=Decimal(str(strike)), option_type=option_type,
        option_symbol=f"SPY260718{option_type[0]}{int(strike*1000):08d}",
        bid=Decimal(str(bid)), ask=Decimal(str(ask)), mid=Decimal(str(mid)),
        last=Decimal(str(bid)), volume=500, open_interest=2000,
        delta=Decimal(str(delta)), gamma=Decimal("0.02"),
        theta=Decimal("-0.05"), vega=Decimal("0.10"), iv=Decimal("0.20"),
        quote_age_seconds=2, provider="thetadata",
    )


def _spread_request():
    short = _quote(option_type="PUT", strike=440, bid=1.20, ask=1.25, delta=-0.30)
    long_ = _quote(option_type="PUT", strike=435, bid=0.50, ask=0.55, delta=-0.18)
    legs = (
        LegSpec(side="SELL", option_type="PUT", strike=Decimal("440"),
                expiry=EXPIRY, qty=1, option_symbol=short.option_symbol),
        LegSpec(side="BUY", option_type="PUT", strike=Decimal("435"),
                expiry=EXPIRY, qty=1, option_symbol=long_.option_symbol),
    )
    quotes = {short.option_symbol: short, long_.option_symbol: long_}
    return TradeRequest(
        underlying="SPY", strategy_name=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        strategy_version="v1", legs=legs, quotes_by_symbol=quotes,
    ), quotes


def _seed_portfolio(s, *, cash="2000", max_open=1, cap="500"):
    pid = str(uuid.uuid4())
    s.execute(text(
        "INSERT INTO options_paper_portfolio (id,name,cash_initial,cash_current,"
        "max_open_trades,max_capital_per_trade,active,universe,strategy_family) "
        "VALUES (:id,:n,:c,:c,:mo,:cap,TRUE,'SPY','SHORT_PUT_CREDIT_SPREAD')"
    ), {"id": pid, "n": f"sandbox-{pid[:8]}", "c": Decimal(cash),
        "mo": max_open, "cap": Decimal(cap)})
    s.commit()
    return pid


def _hash(pid, req):
    return pos.proposal_hash(
        portfolio_id=pid, run_date=RUN_DATE, underlying=req.underlying,
        strategy_name=req.strategy_name, strategy_version=req.strategy_version,
        legs=list(req.legs),
    )


def _cash(s, pid):
    return Decimal(str(s.execute(text(
        "SELECT cash_current FROM options_paper_portfolio WHERE id=:p"
    ), {"p": pid}).scalar()))


def test_promote_one_reserves_and_debits(session_factory, options_enabled):
    with session_factory() as s:
        pid = _seed_portfolio(s)
        req, _ = _spread_request()
        before = _cash(s, pid)
        r = canary_engine.promote_one(
            s, portfolio_id=pid, request=req, proposal_hash=_hash(pid, req), now=NOW)
        s.commit()
        assert r.status == "promoted" and r.reserved is not None
        assert pos.count_open_positions(s, pid) == 1
        assert _cash(s, pid) == before - r.reserved


def test_slot_full(session_factory, options_enabled):
    with session_factory() as s:
        pid = _seed_portfolio(s)
        req, _ = _spread_request()
        canary_engine.promote_one(s, portfolio_id=pid, request=req,
                                  proposal_hash=_hash(pid, req), now=NOW)
        s.commit()
        req2, _ = _spread_request()
        r = canary_engine.promote_one(s, portfolio_id=pid, request=req2,
                                      proposal_hash="different", now=NOW)
        s.commit()
        assert r.status == "slot_full"
        assert pos.count_open_positions(s, pid) == 1


def test_over_capital_cap(session_factory, options_enabled):
    with session_factory() as s:
        pid = _seed_portfolio(s, cap="100")   # reserve ~437 > cap
        req, _ = _spread_request()
        before = _cash(s, pid)
        r = canary_engine.promote_one(s, portfolio_id=pid, request=req,
                                      proposal_hash=_hash(pid, req), now=NOW)
        s.commit()
        assert r.status == "over_capital_cap"
        assert pos.count_open_positions(s, pid) == 0
        assert _cash(s, pid) == before        # cash untouched (savepoint rollback)


def test_proposal_duplicate_savepoint_survives(session_factory, options_enabled):
    with session_factory() as s:
        pid = _seed_portfolio(s, max_open=5)
        req, _ = _spread_request()
        h = _hash(pid, req)
        r1 = canary_engine.promote_one(s, portfolio_id=pid, request=req,
                                       proposal_hash=h, now=NOW)
        s.commit()
        req2, _ = _spread_request()
        r2 = canary_engine.promote_one(s, portfolio_id=pid, request=req2,
                                       proposal_hash=h, now=NOW)
        # Outer txn still usable after the SAVEPOINT rollback:
        still_ok = s.execute(text("SELECT 1")).scalar()
        s.commit()
        assert r1.status == "promoted" and r2.status == "proposal_duplicate"
        assert still_ok == 1
        assert pos.count_open_positions(s, pid) == 1


def test_release_one_credits_and_idempotent(session_factory, options_enabled):
    with session_factory() as s:
        pid = _seed_portfolio(s)
        req, quotes = _spread_request()
        r = canary_engine.promote_one(s, portfolio_id=pid, request=req,
                                      proposal_hash=_hash(pid, req), now=NOW)
        s.commit()
        after_open = _cash(s, pid)
        rel = canary_engine.release_one(
            s, portfolio_id=pid, trade_id=r.trade_id, terminal="close",
            now=NOW, quotes=quotes, reason="CLOSED_TAKE_PROFIT")
        s.commit()
        assert rel.status == "released" and rel.credited is not None
        credited_cash = _cash(s, pid)
        assert credited_cash == after_open + rel.credited
        # idempotent: second release does nothing, no double credit
        rel2 = canary_engine.release_one(
            s, portfolio_id=pid, trade_id=r.trade_id, terminal="close",
            now=NOW, quotes=quotes)
        s.commit()
        assert rel2.status in ("already_released", "engine_rejected")
        assert _cash(s, pid) == credited_cash


def test_reconcile_heals_before_drift(session_factory, options_enabled):
    with session_factory() as s:
        pid = _seed_portfolio(s)
        req, quotes = _spread_request()
        r = canary_engine.promote_one(s, portfolio_id=pid, request=req,
                                      proposal_hash=_hash(pid, req), now=NOW)
        s.commit()
        # Simulate an orphan: close the trade WITHOUT releasing the position.
        from apps.api.src.options.paper.engine import close_trade
        close_trade(r.trade_id, quotes_by_symbol=quotes, reason="X", session=s)
        s.commit()
        assert pos.count_open_positions(s, pid) == 1   # still unreleased = orphan
        report = reconcile.run(s, now=NOW, heal=True)
        s.commit()
        assert r.trade_id in report.orphan_positions_healed
        assert report.cash_drift == []                 # heal-before-drift → clean
        assert pos.count_open_positions(s, pid) == 0


def test_injected_session_no_commit(session_factory, options_enabled):
    with session_factory() as s:
        pid = _seed_portfolio(s)
        req, _ = _spread_request()
        res = open_trade(req, proposal_hash=_hash(pid, req), session=s)
        assert res.accepted
        # Not committed yet → invisible to a separate connection.
        with session_factory() as other:
            seen = other.execute(text(
                "SELECT COUNT(*) FROM options_paper_trade WHERE id=:i"
            ), {"i": res.trade_id}).scalar()
        assert seen == 0
        s.rollback()
        with session_factory() as other:
            gone = other.execute(text(
                "SELECT COUNT(*) FROM options_paper_trade WHERE id=:i"
            ), {"i": res.trade_id}).scalar()
        assert gone == 0
