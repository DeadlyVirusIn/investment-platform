"""Phase P6B.0 integration tests — selector SQL + lifecycle cycle vs Postgres.

  * selection._load_promotable_requests executes against the real
    options_strategy_candidate / candidate_leg / chain schema (column
    correctness; returns [] on empty data — no auto-open)
  * run_lifecycle_cycle manages an open position to a take-profit close +
    cash credit, REGARDLESS of OPTIONS_CANARY_ENABLED (gate split)

Marked `integration` — needs Docker/testcontainers. Paper-only.
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
from apps.api.src.options.canary import selection
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.engine import TradeRequest
from apps.api.src.options.paper.strategies import (
    LegSpec, STRATEGY_SHORT_PUT_CREDIT_SPREAD,
)

pytestmark = pytest.mark.integration

EXPIRY = dt.date(2026, 7, 18)
NOW = dt.datetime(2026, 6, 4, 22, 0, tzinfo=dt.timezone.utc)
RUN_DATE = dt.date(2026, 6, 4)
SHORT_SYM = "SPY260718P00440000"
LONG_SYM = "SPY260718P00435000"


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)


@pytest.fixture
def options_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OPTIONS_ENABLED", True)
    monkeypatch.setattr(settings, "OPTIONS_PAPER_ONLY", True)


def _quote(symbol, option_type, strike, bid, ask, delta):
    mid = (bid + ask) / 2
    return OptionChainQuote(
        snapshot_at_utc=NOW, underlying="SPY", expiry=EXPIRY,
        strike=Decimal(str(strike)), option_type=option_type,
        option_symbol=symbol, bid=Decimal(str(bid)), ask=Decimal(str(ask)),
        mid=Decimal(str(mid)), last=Decimal(str(bid)), volume=500,
        open_interest=2000, delta=Decimal(str(delta)), gamma=Decimal("0.02"),
        theta=Decimal("-0.05"), vega=Decimal("0.10"), iv=Decimal("0.20"),
        quote_age_seconds=2, provider="thetadata",
    )


def _request():
    short = _quote(SHORT_SYM, "PUT", 440, 1.20, 1.25, -0.30)
    long_ = _quote(LONG_SYM, "PUT", 435, 0.50, 0.55, -0.18)
    legs = (
        LegSpec(side="SELL", option_type="PUT", strike=Decimal("440"),
                expiry=EXPIRY, qty=1, option_symbol=SHORT_SYM),
        LegSpec(side="BUY", option_type="PUT", strike=Decimal("435"),
                expiry=EXPIRY, qty=1, option_symbol=LONG_SYM),
    )
    return TradeRequest(
        underlying="SPY", strategy_name=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        strategy_version="canary-v1", legs=legs,
        quotes_by_symbol={SHORT_SYM: short, LONG_SYM: long_},
    )


def _seed_portfolio(s):
    pid = str(uuid.uuid4())
    s.execute(text(
        "INSERT INTO options_paper_portfolio (id,name,cash_initial,cash_current,"
        "max_open_trades,max_capital_per_trade,active,universe,strategy_family) "
        "VALUES (:id,:n,2000,2000,1,500,FALSE,'SPY','SHORT_PUT_CREDIT_SPREAD')"
    ), {"id": pid, "n": f"sbx-{pid[:8]}"})
    s.commit()
    return pid


def _seed_cheap_chain(s):
    """Latest chain: spread cheap to close (high captured profit → TP)."""
    for sym, strike, bid, ask in [(SHORT_SYM, 440, 0.28, 0.32),
                                  (LONG_SYM, 435, 0.08, 0.12)]:
        s.execute(text(
            "INSERT INTO options_chain_snapshot (snapshot_at_utc,underlying,"
            "expiry,strike,option_type,option_symbol,bid,ask,mid,last,volume,"
            "open_interest,delta,quote_age_seconds,provider) VALUES "
            "(:t,'SPY',:e,:k,'PUT',:sym,:b,:a,:m,:b,500,2000,-0.10,2,'thetadata')"
        ), {"t": NOW, "e": EXPIRY, "k": strike, "sym": sym,
            "b": bid, "a": ask, "m": (bid + ask) / 2})
    s.commit()


def test_selector_sql_executes_empty(session_factory):
    # No candidates seeded → selector runs the real query and returns [].
    out = selection._load_promotable_requests(
        portfolio_id="none", run_date=RUN_DATE, session_factory=session_factory)
    assert out == []


def test_lifecycle_cycle_take_profit_gate_independent(
    session_factory, options_enabled, monkeypatch,
):
    # Gate OFF — lifecycle must still manage an existing open position.
    monkeypatch.setattr(settings, "OPTIONS_CANARY_ENABLED", False)
    with session_factory() as s:
        pid = _seed_portfolio(s)
        r = canary_engine.promote_one(
            s, portfolio_id=pid, request=_request(),
            proposal_hash="p6b-tp-test", now=NOW)
        s.commit()
        assert r.status == "promoted"
        cash_after_open = Decimal(str(s.execute(text(
            "SELECT cash_current FROM options_paper_portfolio WHERE id=:p"
        ), {"p": pid}).scalar()))
        _seed_cheap_chain(s)

    # P6D.34C: refresh off — the test container has no provider API access.
    report = canary_engine.run_lifecycle_cycle(
        portfolio_id=pid, now=NOW, heal=True, session_factory=session_factory,
        refresh_quotes=False)

    with session_factory() as s:
        assert pos.count_open_positions(s, pid) == 0          # released
        status = s.execute(text(
            "SELECT status FROM options_paper_trade WHERE id=:t"
        ), {"t": r.trade_id}).scalar()
        assert status == "CLOSED"
        cash_final = Decimal(str(s.execute(text(
            "SELECT cash_current FROM options_paper_portfolio WHERE id=:p"
        ), {"p": pid}).scalar()))
        assert cash_final > cash_after_open                   # reserve+credit returned
    assert report.cash_drift == []                            # identity holds
