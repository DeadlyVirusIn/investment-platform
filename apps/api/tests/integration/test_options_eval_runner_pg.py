"""Phase 11O - Postgres integration tests for the manual options paper
evaluation runner.

End-to-end happy/sad paths against the real schema. Uses the existing
pg_engine + pg_session fixtures and the OPTIONS_ENABLED kill-switch
override pattern from the Phase 11E tests.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from pathlib import Path

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
from apps.api.src.options.paper.eval_runner import (
    EvalRunnerCommitError,
    EvalRunnerSafetyError,
    run,
    step_commit_trades,
)
from apps.api.src.options.paper.eval_runner_models import (
    PlannedTrade,
    RunnerConfig,
)
from apps.api.src.options.paper.strategies import (
    LegSpec,
    RiskMetrics,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
)


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )


@pytest.fixture
def options_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OPTIONS_ENABLED", True)
    monkeypatch.setattr(settings, "OPTIONS_PAPER_ONLY", True)
    monkeypatch.setattr(settings, "OPTIONS_ML_CAN_AFFECT_TRADES", False)


def _today() -> datetime.date:
    return datetime.date(2026, 4, 27)


def _expiry() -> datetime.date:
    return _today() + datetime.timedelta(days=30)


def _snap() -> datetime.datetime:
    d = _today()
    return datetime.datetime(d.year, d.month, d.day, 14, 0,
                             tzinfo=datetime.timezone.utc)


def _seed_put_chain(
    pg_session: Session,
    *,
    underlying: str = "SPY",
) -> None:
    """Insert a tight 4-strike put chain that yields one qualified
    SHORT_PUT_CREDIT_SPREAD evaluation."""
    expiry = _expiry()
    snap = _snap()
    rows = [
        # short candidate (delta -0.30, in band)
        dict(strike=Decimal("440"), bid=Decimal("1.20"),
             ask=Decimal("1.25"), delta=Decimal("-0.30")),
        # long protective (delta outside band but used as long leg)
        dict(strike=Decimal("435"), bid=Decimal("0.55"),
             ask=Decimal("0.60"), delta=Decimal("-0.18")),
        # extra unrelated (out-of-band) just to widen the chain
        dict(strike=Decimal("430"), bid=Decimal("0.30"),
             ask=Decimal("0.35"), delta=Decimal("-0.12")),
        dict(strike=Decimal("450"), bid=Decimal("4.10"),
             ask=Decimal("4.15"), delta=Decimal("-0.55")),
    ]
    for r in rows:
        sym = (
            f"{underlying}{expiry.strftime('%y%m%d')}"
            f"P{int(r['strike'] * 1000):08d}"
        )
        pg_session.execute(text(
            """
            INSERT INTO options_chain_snapshot
              (snapshot_at_utc, underlying, expiry, strike, option_type,
               option_symbol, bid, ask, mid, last,
               volume, open_interest,
               delta, gamma, theta, vega, iv,
               quote_age_seconds, provider, provider_version)
            VALUES
              (:snap, :u, :exp, :strike, 'PUT',
               :sym, :bid, :ask, :mid, :last,
               100, 1000,
               :delta, 0.02, -0.05, 0.10, 0.20,
               2, 'thetadata', 'v1')
            """
        ), {
            "snap": snap, "u": underlying, "exp": expiry,
            "strike": r["strike"], "sym": sym,
            "bid": r["bid"], "ask": r["ask"],
            "mid": (r["bid"] + r["ask"]) / 2, "last": r["bid"],
            "delta": r["delta"],
        })
    pg_session.commit()


def _config(
    *,
    commit: bool = False,
    max_open: int = 5,
    underlyings: tuple[str, ...] = ("SPY",),
) -> RunnerConfig:
    return RunnerConfig(
        date=_today(),
        underlyings=underlyings,
        strategy_filter=None,
        dry_run=not commit,
        commit=commit,
        max_open=max_open,
        explain=False,
        skip_ingest=True,  # NEVER hit ThetaData in tests
    )


# ---------------------------------------------------------------------------
# 1. Dry-run with seeded chain produces planned trades but zero DB writes
# ---------------------------------------------------------------------------

def test_runner_dry_run_against_seeded_chain_zero_trades(
    pg_session, session_factory, options_enabled,
):
    _seed_put_chain(pg_session)
    summary = run(
        _config(commit=False),
        session_factory=session_factory,
        now_utc=_snap(),
    )
    assert summary.config.dry_run is True
    assert summary.n_qualified >= 1
    assert summary.n_planned >= 1
    assert summary.n_committed == 0
    assert summary.committed_trade_ids == ()

    n_trades = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_paper_trade"
    )).scalar_one()
    assert n_trades == 0


# ---------------------------------------------------------------------------
# 2. Commit opens one trade per qualified observation (cap-respected)
# ---------------------------------------------------------------------------

def test_runner_commit_opens_one_trade_per_qualified_observation(
    pg_session, session_factory, options_enabled, tmp_path,
):
    _seed_put_chain(pg_session)
    summary = run(
        _config(commit=True),
        session_factory=session_factory,
        now_utc=_snap(),
        audit_log_dir=tmp_path,
    )
    assert summary.config.commit is True
    assert summary.n_planned >= 1
    assert summary.n_committed == summary.n_planned
    assert len(summary.committed_trade_ids) == summary.n_committed

    n_trades = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_paper_trade WHERE paper_only = TRUE"
    )).scalar_one()
    assert n_trades == summary.n_committed

    legs = pg_session.execute(text(
        "SELECT trade_id, side, option_type "
        "FROM options_paper_trade_leg ORDER BY trade_id, leg_index"
    )).all()
    assert len(legs) == 2 * summary.n_committed
    sides = sorted(l.side for l in legs)
    assert "SELL" in sides and "BUY" in sides


# ---------------------------------------------------------------------------
# 3. Commit twice on same date is dedup-idempotent
# ---------------------------------------------------------------------------

def test_runner_commit_idempotent_across_two_invocations(
    pg_session, session_factory, options_enabled, tmp_path,
):
    _seed_put_chain(pg_session)

    s1 = run(
        _config(commit=True),
        session_factory=session_factory,
        now_utc=_snap(),
        audit_log_dir=tmp_path,
    )
    assert s1.n_committed >= 1
    n_after_first = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_paper_trade"
    )).scalar_one()

    s2 = run(
        _config(commit=True),
        session_factory=session_factory,
        now_utc=_snap(),
        audit_log_dir=tmp_path,
    )
    # Second run should dedupe — every committable plan already has an
    # OPEN trade for the (underlying, rule_id, date) tuple.
    assert s2.n_existing_open_trade_dedup >= s1.n_committed
    assert s2.n_committed == 0
    n_after_second = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_paper_trade"
    )).scalar_one()
    assert n_after_second == n_after_first


# ---------------------------------------------------------------------------
# 4. max_open cap is honored
# ---------------------------------------------------------------------------

def test_runner_commit_respects_max_open_cap(
    pg_session, session_factory, options_enabled, tmp_path,
):
    # Seed two underlyings — gives at least 2 qualifiable observations
    _seed_put_chain(pg_session, underlying="SPY")
    _seed_put_chain(pg_session, underlying="QQQ")

    summary = run(
        _config(commit=True, max_open=1, underlyings=("SPY", "QQQ")),
        session_factory=session_factory,
        now_utc=_snap(),
        audit_log_dir=tmp_path,
    )
    assert summary.n_qualified >= 2
    assert summary.n_planned == 1
    assert summary.n_committed == 1


# ---------------------------------------------------------------------------
# 5. Commit aborts on missing quote
# ---------------------------------------------------------------------------

def test_runner_commit_aborts_on_quote_missing(
    pg_session, session_factory, options_enabled,
):
    """If we hand step_commit_trades a planned trade whose accepted-quote
    map is empty, open_trade rejects with QUOTE_MISSING and the runner
    must surface EvalRunnerCommitError."""
    expiry = _expiry()
    legs = (
        LegSpec(
            side="SELL", option_type="PUT", strike=Decimal("440"),
            expiry=expiry, qty=1, option_symbol="SPY_FAKE_SHORT",
        ),
        LegSpec(
            side="BUY", option_type="PUT", strike=Decimal("435"),
            expiry=expiry, qty=1, option_symbol="SPY_FAKE_LONG",
        ),
    )
    p = PlannedTrade(
        observation_id="SPY:2026-04-27:SHORT_PUT_CREDIT_SPREAD",
        underlying="SPY",
        rule_id=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        legs=legs,
        risk=RiskMetrics(
            max_loss_dollars=Decimal("388"),
            max_profit_dollars=Decimal("112"),
            breakeven_lower=Decimal("438.88"), breakeven_upper=None,
        ),
        entry_credit_dollars=Decimal("112"),
        quote_age_max_seconds=2,
        rejection_reasons=(), qualified=True,
    )
    with pytest.raises(EvalRunnerCommitError):
        step_commit_trades(
            [p], accepted_quotes_by_obs={}, session_factory=session_factory,
        )


# ---------------------------------------------------------------------------
# 6. Commit aborts on defined-risk failure (engineered via legs alone)
# ---------------------------------------------------------------------------

def test_runner_commit_aborts_on_defined_risk_fail(
    pg_session, session_factory, options_enabled,
):
    """Engineer a single-leg PlannedTrade — open_trade's
    validate_defined_risk catches this and the runner surfaces the
    rejection."""
    expiry = _expiry()
    snap = _snap()
    naked_sym = "SPY_NAKED_SHORT"
    quote = OptionChainQuote(
        snapshot_at_utc=snap, underlying="SPY",
        expiry=expiry, strike=Decimal("440"),
        option_type="PUT", option_symbol=naked_sym,
        bid=Decimal("1.20"), ask=Decimal("1.25"),
        mid=Decimal("1.225"), last=Decimal("1.20"),
        volume=100, open_interest=1000,
        delta=Decimal("-0.30"), gamma=Decimal("0.02"),
        theta=Decimal("-0.05"), vega=Decimal("0.10"),
        iv=Decimal("0.20"), quote_age_seconds=2,
        provider="thetadata",
    )
    p = PlannedTrade(
        observation_id="SPY:2026-04-27:SHORT_PUT_CREDIT_SPREAD",
        underlying="SPY",
        rule_id=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        legs=(LegSpec(
            side="SELL", option_type="PUT", strike=Decimal("440"),
            expiry=expiry, qty=1, option_symbol=naked_sym,
        ),),  # 1 leg = naked short = NOT defined risk
        risk=RiskMetrics(
            max_loss_dollars=Decimal("100"),
            max_profit_dollars=Decimal("100"),
            breakeven_lower=None, breakeven_upper=None,
        ),
        entry_credit_dollars=Decimal("100"),
        quote_age_max_seconds=2,
        rejection_reasons=(), qualified=True,
    )
    with pytest.raises(EvalRunnerCommitError):
        step_commit_trades(
            [p], accepted_quotes_by_obs={
                p.observation_id: [quote],
            },
            session_factory=session_factory,
        )


# ---------------------------------------------------------------------------
# 7. Commit writes JSONL audit log
# ---------------------------------------------------------------------------

def test_runner_commit_writes_jsonl_audit_log(
    pg_session, session_factory, options_enabled, tmp_path,
):
    _seed_put_chain(pg_session)
    summary = run(
        _config(commit=True),
        session_factory=session_factory,
        now_utc=_snap(),
        audit_log_dir=tmp_path,
    )
    assert summary.n_committed >= 1
    expected = tmp_path / f"options_paper_eval_{_today().isoformat()}.jsonl"
    assert expected.exists(), f"audit log {expected} missing"

    lines = [
        json.loads(line)
        for line in expected.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    kinds = [r["kind"] for r in lines]
    assert "summary" in kinds
    assert "filled_paper_trade" in kinds
    filled = [r for r in lines if r["kind"] == "filled_paper_trade"]
    assert len(filled) == summary.n_committed
    for row in filled:
        assert row["trade_id"] is not None
        assert row["underlying"] == "SPY"
        assert row["rule_id"] == STRATEGY_SHORT_PUT_CREDIT_SPREAD
        assert row["qualified"] is True
        assert row["rejection_reasons"] == []


def test_runner_dry_run_does_not_write_audit_log(
    pg_session, session_factory, options_enabled, tmp_path,
):
    _seed_put_chain(pg_session)
    summary = run(
        _config(commit=False),
        session_factory=session_factory,
        now_utc=_snap(),
        audit_log_dir=tmp_path,
    )
    assert summary.config.dry_run is True
    expected = tmp_path / f"options_paper_eval_{_today().isoformat()}.jsonl"
    assert not expected.exists()


# ---------------------------------------------------------------------------
# 8. Kill-switch blocks commit
# ---------------------------------------------------------------------------

def test_runner_kill_switch_blocks_commit(
    pg_session, session_factory, monkeypatch,
):
    monkeypatch.setattr(settings, "OPTIONS_ENABLED", False)
    monkeypatch.setattr(settings, "OPTIONS_PAPER_ONLY", True)
    monkeypatch.setattr(settings, "OPTIONS_ML_CAN_AFFECT_TRADES", False)
    _seed_put_chain(pg_session)

    with pytest.raises(EvalRunnerSafetyError, match="OPTIONS_ENABLED"):
        run(
            _config(commit=True),
            session_factory=session_factory,
            now_utc=_snap(),
        )

    n_trades = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_paper_trade"
    )).scalar_one()
    assert n_trades == 0
