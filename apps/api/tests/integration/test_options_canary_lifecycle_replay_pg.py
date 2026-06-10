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
from apps.api.src.options.canary import lifecycle
from apps.api.src.options.canary import positions as pos
from apps.api.src.options.canary import quotes_refresh
from apps.api.src.options.canary import selection
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
            "options_chain_snapshot, options_candidate_leg, "
            "options_strategy_candidate, options_shadow_decision_log "
            "RESTART IDENTITY CASCADE"
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

def _release_reason(s: Session, trade_id: int):
    return s.execute(text(
        "SELECT release_reason FROM options_paper_position WHERE trade_id = :t"
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
        # P6D.33A — a CLOSED_TAKE_PROFIT must book POSITIVE realized P&L:
        # entry $35 − exit_debit $11 − fees_rt $2.80 = +$21.20.
        assert _release_reason(s, r.trade_id) == "CLOSED_TAKE_PROFIT"
        realized = _realized(s, r.trade_id)
        assert realized is not None
        assert Decimal(str(realized)) > 0
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
        # P6D.33A — DTE management close may book NEGATIVE realized P&L
        # (risk management, correctly labeled): 35 − 45 − 2.80 = −$12.80.
        assert _release_reason(s, r.trade_id) == "CLOSED_DTE_MANAGEMENT"
        realized = _realized(s, r.trade_id)
        assert realized is not None
        assert Decimal(str(realized)) < 0
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


# ===========================================================================
# 7) P6D.33A — selector economic viability gate (REAL selector + seeded rows)
# ===========================================================================

CAND_EXPIRY = TODAY + dt.timedelta(days=30)   # DTE 30 ∈ [21, 45]


@pytest.fixture
def canary_universe_qqq(monkeypatch):
    """Point the canary universe at the harness underlying (QQQ) so the
    REAL selector evaluates the seeded candidates. Strategy/DTE/confidence
    gates keep their real defaults."""
    monkeypatch.setattr(settings, "OPTIONS_CANARY_UNIVERSE", "QQQ")


def test_selector_rejects_uneconomic_low_credit(
    session_factory, fresh_portfolio, canary_universe_qqq,
):
    """Trade-3-like spread: conservative-fill credit $10 with 0.09-wide
    quotes (drag $9 + fees $2.80 → min_viable $23.60) → the selector's
    economics gate rejects it; nothing is promotable."""
    pid, _ = fresh_portfolio
    with session_factory() as s:
        rh.seed_candidate(s, run_date=TODAY, expiry=CAND_EXPIRY)
        # Fillable (spread 0.09 <= $0.10, OI 2000, fresh) but uneconomic:
        # SELL fill 0.395−0.045=0.35, BUY fill 0.205+0.045=0.25 → credit $10.
        rh.seed_chain(s, expiry=CAND_EXPIRY, snapshot_at=NOW,
                      short_bid=Decimal("0.35"), short_ask=Decimal("0.44"),
                      long_bid=Decimal("0.16"), long_ask=Decimal("0.25"))

    out = selection._load_promotable_requests(
        portfolio_id=pid, run_date=TODAY, session_factory=session_factory,
        now=NOW)
    assert out == []


def test_selector_accepts_economic_credit(
    session_factory, fresh_portfolio, canary_universe_qqq,
):
    """Healthy spread: conservative-fill credit $35 (0.60−0.25) with tight
    quotes → min_viable $15.60, tp_net +$9.70, net_rr 0.495 → promotable."""
    pid, _ = fresh_portfolio
    with session_factory() as s:
        rh.seed_candidate(s, run_date=TODAY, expiry=CAND_EXPIRY)
        rh.seed_chain(s, expiry=CAND_EXPIRY, snapshot_at=NOW,
                      short_bid=Decimal("0.60"), short_ask=Decimal("0.65"),
                      long_bid=Decimal("0.20"), long_ask=Decimal("0.25"))

    out = selection._load_promotable_requests(
        portfolio_id=pid, run_date=TODAY, session_factory=session_factory,
        now=NOW)
    assert len(out) == 1
    req, phash = out[0]
    assert req.underlying == "QQQ"
    assert phash


# ===========================================================================
# 8) P6D.33A — TP gross-crossed but NET-negative → HOLD_TP_UNECONOMIC
# ===========================================================================

def test_tp_gross_crossed_net_negative_holds(session_factory, fresh_portfolio):
    """Promote a low-credit trade DIRECTLY via promote_one (bypassing the
    selector gate in-test): entry fills 0.35/0.25 → credit $10.00, max_loss
    $90 (trade-3 economics). Seed exit quotes so GROSS pct = 0.60 >= 0.50 but
    NET = 10 − 4 − 9 − 2.80 = −$5.80 <= 0 → lifecycle HOLDs (no negative
    'take profit'), position stays OPEN, reconcile clean."""
    pid, _ = fresh_portfolio
    req = rh.make_spcs_request(
        expiry=FAR_EXPIRY, snapshot_at=NOW,
        short_bid=Decimal("0.35"), short_ask=Decimal("0.44"),
        long_bid=Decimal("0.16"), long_ask=Decimal("0.25"),
    )
    r = rh.promote(session_factory, portfolio_id=pid, request=req,
                   proposal_hash="tp-unecon-1", now=NOW)
    assert r.status == "promoted", r
    assert r.reserved == Decimal("92.80")          # max_loss 90 + fees_rt 2.80
    with session_factory() as s:
        # Gross cost = (0.115 − 0.075) × 100 = $4 → pct (10−4)/10 = 0.60 ≥ TP,
        # but 0.09-wide quotes → close drag $9 → net −$5.80.
        rh.seed_chain(s, expiry=FAR_EXPIRY, snapshot_at=NOW,
                      short_bid=Decimal("0.07"), short_ask=Decimal("0.16"),
                      long_bid=Decimal("0.03"), long_ask=Decimal("0.12"))

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "OPEN"     # NOT closed at a loss
        assert _released_at(s, r.trade_id) is None
        assert _release_reason(s, r.trade_id) is None
        assert pos.count_open_positions(s, pid) == 1
        assert _realized(s, r.trade_id) is None
        assert _mtm_event_count(s, r.trade_id) >= 1       # still observed
    assert report.clean
    assert report.cash_drift == []


# ===========================================================================
# 9) P6D.34C — decision freshness gate + targeted intraday quote refresh
# ===========================================================================

STALE_SNAPSHOT_AT = NOW - dt.timedelta(hours=2)   # eff age ≈ 7202s > 900s
MAX_AGE = 900                                      # settings default


def _decision(session_factory, *, pid: str, trade_id: int) -> dict:
    """Observe manage_one's decision dict WITHOUT mutating state (rollback)."""
    with session_factory() as s:
        res = lifecycle.manage_one(
            s, portfolio_id=pid, trade_id=trade_id, now=NOW,
            tp_pct=float(settings.OPTIONS_CANARY_TP_PCT),
            dte_close=int(settings.OPTIONS_CANARY_DTE_CLOSE),
        )
        s.rollback()
    return res


def test_stale_tp_eligible_holds(session_factory, fresh_portfolio):
    """TP-level mids but the chain is 2h old (eff age 7202 > 900) → the
    freshness gate HOLDs with HOLD_STALE_QUOTES; nothing is closed."""
    pid, _ = fresh_portfolio
    r = _promote_far(session_factory, pid, phash="34c-stale-tp")
    with session_factory() as s:
        # Same TP-worthy mids as scenario 2, but seeded 2 hours ago.
        rh.seed_chain(s, expiry=FAR_EXPIRY, snapshot_at=STALE_SNAPSHOT_AT,
                      short_bid=Decimal("0.08"), short_ask=Decimal("0.12"),
                      long_bid=Decimal("0.01"), long_ask=Decimal("0.05"))

    res = _decision(session_factory, pid=pid, trade_id=r.trade_id)
    assert res["action"] is None
    assert res["reason"] == "HOLD_STALE_QUOTES"
    assert res["decision_fresh"] is False
    assert res["max_effective_age_seconds"] > MAX_AGE

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "OPEN"
        assert _released_at(s, r.trade_id) is None
        assert pos.count_open_positions(s, pid) == 1
    assert report.clean
    assert report.cash_drift == []


def test_fresh_tp_decision_fresh_and_closes(session_factory, fresh_portfolio):
    """Fresh chain (age ~2s < 900) at TP level → decision_fresh True and the
    cycle closes CLOSED_TAKE_PROFIT (scenario-2 behavior preserved)."""
    pid, _ = fresh_portfolio
    r = _promote_far(session_factory, pid, phash="34c-fresh-tp")
    with session_factory() as s:
        rh.seed_chain(s, expiry=FAR_EXPIRY, snapshot_at=NOW,
                      short_bid=Decimal("0.08"), short_ask=Decimal("0.12"),
                      long_bid=Decimal("0.01"), long_ask=Decimal("0.05"))

    res = _decision(session_factory, pid=pid, trade_id=r.trade_id)
    assert res["decision_fresh"] is True
    assert res["max_effective_age_seconds"] <= MAX_AGE
    assert (res["action"], res["reason"]) == ("close", "CLOSED_TAKE_PROFIT")

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "CLOSED"
        assert _release_reason(s, r.trade_id) == "CLOSED_TAKE_PROFIT"
        assert pos.count_open_positions(s, pid) == 0
    assert report.clean
    assert report.cash_drift == []


def test_dte_stale_holds(session_factory, fresh_portfolio):
    """Near-expiry (DTE 5 <= 7) but the chain is 2h old → DTE-management
    branch is gated too: HOLD_STALE_QUOTES, position stays OPEN."""
    pid, _ = fresh_portfolio
    near_expiry = TODAY + dt.timedelta(days=5)
    req = rh.make_spcs_request(expiry=near_expiry, snapshot_at=NOW)
    r = rh.promote(session_factory, portfolio_id=pid, request=req,
                   proposal_hash="34c-dte-stale", now=NOW)
    assert r.status == "promoted", r
    with session_factory() as s:
        rh.seed_chain(s, expiry=near_expiry, snapshot_at=STALE_SNAPSHOT_AT,
                      short_bid=Decimal("0.60"), short_ask=Decimal("0.65"),
                      long_bid=Decimal("0.20"), long_ask=Decimal("0.25"))

    res = _decision(session_factory, pid=pid, trade_id=r.trade_id)
    assert res["action"] is None
    assert res["reason"] == "HOLD_STALE_QUOTES"
    assert res["decision_fresh"] is False

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "OPEN"
        assert _released_at(s, r.trade_id) is None
        assert pos.count_open_positions(s, pid) == 1
    assert report.clean
    assert report.cash_drift == []


def test_refresh_success_allows_decision(session_factory, fresh_portfolio):
    """Chain is 2h stale at TP level; the cycle runs with refresh enabled and
    a FAKE ingest_fn that seeds a FRESH chain row → the decision evaluates
    fresh quotes and the trade closes CLOSED_TAKE_PROFIT."""
    pid, _ = fresh_portfolio
    r = _promote_far(session_factory, pid, phash="34c-refresh-ok")
    with session_factory() as s:
        rh.seed_chain(s, expiry=FAR_EXPIRY, snapshot_at=STALE_SNAPSHOT_AT,
                      short_bid=Decimal("0.08"), short_ask=Decimal("0.12"),
                      long_bid=Decimal("0.01"), long_ask=Decimal("0.05"))

    calls: list[str] = []

    def fake_ingest(*, underlying, snapshot_at_utc, session_factory):
        calls.append(underlying)
        with session_factory() as s:
            rh.seed_chain(s, expiry=FAR_EXPIRY, snapshot_at=snapshot_at_utc,
                          short_bid=Decimal("0.08"), short_ask=Decimal("0.12"),
                          long_bid=Decimal("0.01"), long_ask=Decimal("0.05"))

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW,
                          refresh_quotes=True, ingest_fn=fake_ingest)

    assert calls == [rh.UNDERLYING]            # once per distinct underlying
    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "CLOSED"
        assert _release_reason(s, r.trade_id) == "CLOSED_TAKE_PROFIT"
        assert pos.count_open_positions(s, pid) == 0
        realized = _realized(s, r.trade_id)
        assert realized is not None and Decimal(str(realized)) > 0
    assert report.clean
    assert report.cash_drift == []


def test_refresh_failure_tolerated(session_factory, fresh_portfolio):
    """Refresh enabled but ingest raises → no exception escapes the cycle;
    decisions see the stale chain and HOLD; reconcile clean."""
    pid, _ = fresh_portfolio
    r = _promote_far(session_factory, pid, phash="34c-refresh-fail")
    with session_factory() as s:
        rh.seed_chain(s, expiry=FAR_EXPIRY, snapshot_at=STALE_SNAPSHOT_AT,
                      short_bid=Decimal("0.08"), short_ask=Decimal("0.12"),
                      long_bid=Decimal("0.01"), long_ask=Decimal("0.05"))

    def boom(**_kw):
        raise RuntimeError("provider down")

    report = rh.run_cycle(session_factory, portfolio_id=pid, now=NOW,
                          refresh_quotes=True, ingest_fn=boom)

    with session_factory() as s:
        assert _trade_status(s, r.trade_id) == "OPEN"     # held on stale
        assert _released_at(s, r.trade_id) is None
        assert pos.count_open_positions(s, pid) == 1
    assert report.clean
    assert report.cash_drift == []


def test_refresh_helper_success_and_failure(session_factory, fresh_portfolio):
    """Direct refresh_open_position_quotes contract: success path returns the
    refreshed underlyings (fake called once per distinct underlying); a
    raising ingest_fn lands in `failed` and never raises out."""
    pid, _ = fresh_portfolio
    _promote_far(session_factory, pid, phash="34c-helper")

    calls: list[str] = []
    out = quotes_refresh.refresh_open_position_quotes(
        portfolio_id=pid, session_factory=session_factory,
        ingest_fn=lambda **kw: calls.append(kw["underlying"]), now=NOW)
    assert out == {"refreshed": [rh.UNDERLYING], "failed": [], "skipped": None}
    assert calls == [rh.UNDERLYING]

    def boom(**_kw):
        raise RuntimeError("provider down")

    out2 = quotes_refresh.refresh_open_position_quotes(
        portfolio_id=pid, session_factory=session_factory,
        ingest_fn=boom, now=NOW)
    assert out2["refreshed"] == [] and out2["skipped"] is None
    assert out2["failed"] == [
        {"underlying": rh.UNDERLYING, "error": "provider down"}]


def test_refresh_no_open_positions_skips(session_factory, fresh_portfolio):
    """No open positions → skipped='no_open_positions' and ingest_fn is
    never called."""
    pid, _ = fresh_portfolio
    calls: list[str] = []
    out = quotes_refresh.refresh_open_position_quotes(
        portfolio_id=pid, session_factory=session_factory,
        ingest_fn=lambda **kw: calls.append(kw["underlying"]), now=NOW)
    assert out == {"refreshed": [], "failed": [],
                   "skipped": "no_open_positions"}
    assert calls == []
