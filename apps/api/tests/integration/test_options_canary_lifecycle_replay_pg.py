"""TESTS-ONLY options-canary lifecycle replay (alembic-migrated PG container).

Proves the REAL canary lifecycle (promote_one + run_lifecycle_cycle →
manage_one → decide_exit → release_one + reconcile) transitions
deterministically for the QQQ SHORT_PUT_CREDIT_SPREAD shape, in an ISOLATED
ephemeral Postgres testcontainer built via `alembic upgrade head`.

No production source is touched; no production/compose DB is used. Six
scenarios, each driven purely by (a) the promoted trade's leg strikes/expiry
and (b) the seeded latest options_chain_snapshot mids / age / expiry.

Run:
    uv run pytest apps/api/tests/integration/test_options_canary_lifecycle_replay_pg.py -v -m integration
"""

from __future__ import annotations

import datetime as dt
import os
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.config import settings
from apps.api.src.options.canary import positions as pos
from apps.api.tests.integration import _canary_replay as rh

pytestmark = pytest.mark.integration

# Deterministic clock. NOW is the lifecycle "as_of"; expiries are derived from
# it so DTE is exact and reproducible.
NOW = dt.datetime(2026, 6, 9, 22, 0, tzinfo=dt.timezone.utc)
TODAY = NOW.date()
FAR_EXPIRY = TODAY + dt.timedelta(days=101)   # DTE = 101  (> dte_close 7)


# ---------------------------------------------------------------------------
# Container engine — alembic-migrated, isolation-asserted (SAFETY GUARDS 1+2)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def alembic_engine(pg_url: str) -> Engine:
    """Ephemeral testcontainer URL (from the existing session-scoped pg_url
    fixture) → assert isolation → `alembic upgrade head` → Engine. Never reads
    DATABASE_URL to build the engine."""
    engine = rh.make_alembic_engine(pg_url, os.environ)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(alembic_engine: Engine):
    return sessionmaker(bind=alembic_engine, class_=Session,
                        expire_on_commit=False)


@pytest.fixture(autouse=True)
def _engine_kill_switch_on(monkeypatch):
    """The paper engine is inert unless OPTIONS_ENABLED + OPTIONS_PAPER_ONLY.
    Lifecycle MTM/close/expire need these True to write. Promotion gate
    (OPTIONS_CANARY_ENABLED) is intentionally OFF — manage_one must run
    regardless (gate split)."""
    monkeypatch.setattr(settings, "OPTIONS_ENABLED", True)
    monkeypatch.setattr(settings, "OPTIONS_PAPER_ONLY", True)
    monkeypatch.setattr(settings, "OPTIONS_CANARY_ENABLED", False)


@pytest.fixture
def fresh_portfolio(session_factory):
    """A clean isolated replay-sim- portfolio per test (truncate canary state
    first so module-scoped schema is reused without cross-test bleed)."""
    with session_factory() as s:
        s.execute(text(
            "TRUNCATE options_paper_position, options_paper_trade_leg, "
            "options_trade_lifecycle_event, options_expiration_event, "
            "options_assignment_event, options_paper_trade, "
            "options_chain_snapshot RESTART IDENTITY CASCADE"
        ))
        s.execute(text(
            "DELETE FROM options_paper_portfolio WHERE name LIKE :p"
        ), {"p": f"{rh.REPLAY_PREFIX}%"})
        s.commit()
        pid, name = rh.make_portfolio(s)
    return pid, name


# ---------------------------------------------------------------------------
# Small assertion helpers
# ---------------------------------------------------------------------------

def _trade_status(s: Session, trade_id: int) -> str:
    return s.execute(text(
        "SELECT status FROM options_paper_trade WHERE id = :t"
    ), {"t": trade_id}).scalar()

def _released_at(s: Session, trade_id: int):
    return s.execute(text(
        "SELECT released_at FROM options_paper_position WHERE trade_id = :t"
    ), {"t": trade_id}).scalar()

def _realized(s: Session, trade_id: int):
    return s.execute(text(
        "SELECT realized_pnl_dollars FROM options_paper_trade WHERE id = :t"
    ), {"t": trade_id}).scalar()

def _cash(s: Session, pid: str) -> Decimal:
    return Decimal(str(s.execute(text(
        "SELECT cash_current FROM options_paper_portfolio WHERE id = :p"
    ), {"p": pid}).scalar()))

def _mtm_event_count(s: Session, trade_id: int) -> int:
    return int(s.execute(text(
        "SELECT COUNT(*) FROM options_trade_lifecycle_event "
        "WHERE trade_id = :t AND event_type = 'MTM'"
    ), {"t": trade_id}).scalar() or 0)


def _promote_far(session_factory, pid: str, *, phash: str):
    """Promote the default fillable SPCS at FAR_EXPIRY (entry credit ~$35,
    max_loss ~$65)."""
    req = rh.make_spcs_request(expiry=FAR_EXPIRY, snapshot_at=NOW)
    r = rh.promote(session_factory, portfolio_id=pid, request=req,
                   proposal_hash=phash, now=NOW)
    assert r.status == "promoted", r
    return r


# ===========================================================================
# SAFETY GUARDS — assert the four guards directly (independent of scenarios)
# ===========================================================================

def test_safety_guards(alembic_engine, fresh_portfolio):
    url = str(alembic_engine.url)
    # GUARD 1: ephemeral localhost + container-assigned (non-5432) port.
    rh.assert_ephemeral_url(url)
    # GUARD 2: engine URL is not DATABASE_URL.
    rh.assert_not_database_url(url, os.environ)
    pid, name = fresh_portfolio
    # GUARD 3: replay-sim- prefix.
    rh.assert_replay_portfolio_name(name)
    # GUARD 4: not the canary-spy-v1 seed.
    rh.assert_not_canary_seed(portfolio_id=pid, name=name)
    assert name.startswith("replay-sim-") and name != "canary-spy-v1"


# ===========================================================================
# 1) HOLD — DTE>7, captured<50% → stays open, MTM recorded, reconcile clean
# ===========================================================================

def test_hold_far_dte_low_capture(session_factory, fresh_portfolio):
    pid, _ = fresh_portfolio
    r = _promote_far(session_factory, pid, phash="hold-1")
    # Latest chain ≈ entry (cost≈$40 vs max_profit $35 → pct<0 → HOLD).
    with session_factory() as s:
        rh.seed_chain(s, expiry=FAR_EXPIRY, snapshot_at=NOW,
                      short_bid=Decimal("0.60"), short_ask=Decimal("0.65"),
                      long_bid=Decimal("0.20"), long_ask=Decimal("0.25"))

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "OPEN"
        assert _released_at(s, r.trade_id) is None
        assert pos.count_open_positions(s, pid) == 1
        assert _mtm_event_count(s, r.trade_id) >= 1   # MTM observation recorded
    assert report.clean
    assert report.cash_drift == []


# ===========================================================================
# 2) TP_CLOSE — captured>=50% → closes, reserve released, realized recorded
# ===========================================================================

def test_take_profit_close(session_factory, fresh_portfolio):
    pid, _ = fresh_portfolio
    r = _promote_far(session_factory, pid, phash="tp-1")
    with session_factory() as s:
        cash_after_open = _cash(s, pid)
        # Cheap to close: short mid 0.10 / long 0.03 → cost $7 → pct≈0.80 ≥ 0.50.
        rh.seed_chain(s, expiry=FAR_EXPIRY, snapshot_at=NOW,
                      short_bid=Decimal("0.08"), short_ask=Decimal("0.12"),
                      long_bid=Decimal("0.01"), long_ask=Decimal("0.05"))

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "CLOSED"
        assert _released_at(s, r.trade_id) is not None
        assert pos.count_open_positions(s, pid) == 0
        assert _realized(s, r.trade_id) is not None
        # Reserve (≈max_loss+fees) + realized credited back → cash strictly up.
        assert _cash(s, pid) > cash_after_open
    assert report.clean
    assert report.cash_drift == []


# ===========================================================================
# 3) DTE_CLOSE — expiry = today+5 (DTE<=7), not TP → closes, released, realized
# ===========================================================================

def test_dte_management_close(session_factory, fresh_portfolio):
    pid, _ = fresh_portfolio
    near_expiry = TODAY + dt.timedelta(days=5)   # DTE = 5  (<= dte_close 7)
    req = rh.make_spcs_request(expiry=near_expiry, snapshot_at=NOW)
    r = rh.promote(session_factory, portfolio_id=pid, request=req,
                   proposal_hash="dte-1", now=NOW)
    assert r.status == "promoted", r
    with session_factory() as s:
        cash_after_open = _cash(s, pid)
        # Priced & fillable, but NOT take-profit (cost≈$40, pct<0).
        rh.seed_chain(s, expiry=near_expiry, snapshot_at=NOW,
                      short_bid=Decimal("0.60"), short_ask=Decimal("0.65"),
                      long_bid=Decimal("0.20"), long_ask=Decimal("0.25"))

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "CLOSED"
        assert _released_at(s, r.trade_id) is not None
        assert pos.count_open_positions(s, pid) == 0
        assert _realized(s, r.trade_id) is not None
        assert _cash(s, pid) > cash_after_open
    assert report.clean
    assert report.cash_drift == []


# ===========================================================================
# 4) EXPIRY_SETTLEMENT — expiry <= today (DTE<=0) → settle/close, released
# ===========================================================================

def test_expiry_settlement(session_factory, fresh_portfolio):
    pid, _ = fresh_portfolio
    exp_expiry = TODAY            # DTE = 0 → decide_exit → 'expire'
    req = rh.make_spcs_request(expiry=exp_expiry, snapshot_at=NOW)
    r = rh.promote(session_factory, portfolio_id=pid, request=req,
                   proposal_hash="exp-1", now=NOW)
    assert r.status == "promoted", r
    with session_factory() as s:
        cash_after_open = _cash(s, pid)
        # priced (mid present) so decide_exit reaches the expiry branch.
        rh.seed_chain(s, expiry=exp_expiry, snapshot_at=NOW,
                      short_bid=Decimal("0.10"), short_ask=Decimal("0.14"),
                      long_bid=Decimal("0.02"), long_ask=Decimal("0.06"))
        # settlement source for selection.settlement_price (QQQ well above the
        # short strike → puts expire worthless / OTM).
        rh.seed_settlement(s, close_price=Decimal("420"))

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) in ("EXPIRED", "ASSIGNED")
        assert _released_at(s, r.trade_id) is not None
        assert pos.count_open_positions(s, pid) == 0
        assert _realized(s, r.trade_id) is not None
        assert _cash(s, pid) > cash_after_open
    assert report.clean
    assert report.cash_drift == []


# ===========================================================================
# 5) STALE_OR_UNPRICED_HOLD — no/stale quote → HOLD, NOT closed, reconcile clean
# ===========================================================================

def test_stale_unpriced_hold(session_factory, fresh_portfolio):
    pid, _ = fresh_portfolio
    r = _promote_far(session_factory, pid, phash="stale-1")
    # Seed a STALE snapshot (quote_age_seconds way over 60) for each leg.
    # latest_chain_quotes still returns it (it's the latest), but manage_one's
    # MTM path treats it as priced ONLY by mid — staleness is enforced at the
    # FILL gate on close. To force the HOLD_STALE branch we instead seed NO
    # mid (unpriced): omit the chain entirely so quotes are missing.
    # (Two real ways to be 'unpriced': symbol absent, or mid NULL.)
    # Here: leave the chain EMPTY → priced=False → decide_exit → HOLD_STALE.

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "OPEN"
        assert _released_at(s, r.trade_id) is None
        assert pos.count_open_positions(s, pid) == 1
    assert report.clean
    assert report.cash_drift == []


def test_stale_quote_null_mid_hold(session_factory, fresh_portfolio):
    """Second unpriced form: a snapshot row exists but mid IS NULL → unpriced
    → HOLD_STALE (never force-close on missing data)."""
    pid, _ = fresh_portfolio
    r = _promote_far(session_factory, pid, phash="stale-2")
    with session_factory() as s:
        for sym, strike in [(rh.SHORT_SYM, rh.SHORT_STRIKE),
                            (rh.LONG_SYM, rh.LONG_STRIKE)]:
            s.execute(text(
                "INSERT INTO options_chain_snapshot "
                "(snapshot_at_utc, underlying, expiry, strike, option_type, "
                " option_symbol, bid, ask, mid, last, volume, open_interest, "
                " quote_age_seconds, provider) "
                "VALUES (:t, :u, :e, :k, 'PUT', :sym, NULL, NULL, NULL, NULL, "
                " 500, 2000, 5, 'thetadata')"
            ), {"t": NOW, "u": rh.UNDERLYING, "e": FAR_EXPIRY, "k": strike,
                "sym": sym})
        s.commit()

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "OPEN"
        assert _released_at(s, r.trade_id) is None
        assert pos.count_open_positions(s, pid) == 1
    assert report.clean


# ===========================================================================
# 6) ADVERSE_NEAR_MAX_LOSS — spread ~ full width → HOLD (defined risk, no stop)
# ===========================================================================

def test_adverse_near_max_loss_holds(session_factory, fresh_portfolio):
    pid, _ = fresh_portfolio
    r = _promote_far(session_factory, pid, phash="adverse-1")
    with session_factory() as s:
        # Spread expensive to close ≈ full width: short mid ~0.92, long ~0.10
        # → cost ≈ $82, profit ≈ -$47 → pct strongly negative. DTE far.
        # decide_exit has NO hard stop for defined-risk → HOLD.
        rh.seed_chain(s, expiry=FAR_EXPIRY, snapshot_at=NOW,
                      short_bid=Decimal("0.90"), short_ask=Decimal("0.94"),
                      long_bid=Decimal("0.08"), long_ask=Decimal("0.12"))

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "OPEN"      # NOT prematurely closed
        assert _released_at(s, r.trade_id) is None
        assert pos.count_open_positions(s, pid) == 1
        assert _mtm_event_count(s, r.trade_id) >= 1
    assert report.clean
    assert report.cash_drift == []
