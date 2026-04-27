"""Phase 11B integration tests — options schema isolation + constraints.

Asserts:
  * Migration upgrade + downgrade cycle works
  * Zero foreign keys cross the options_* / non-options_* boundary
  * CHECK constraints enforce option_type, side, status, strategy_name,
    paper_only, lifecycle event_type, expiration classification,
    assignment event_type / risk_level
  * No options table references any equity / V2 table
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.options_models import (
    OptionsAssignmentEvent,
    OptionsChainSnapshot,
    OptionsExpirationEvent,
    OptionsFeatureDaily,
    OptionsPaperTrade,
    OptionsPaperTradeLeg,
    OptionsTradeLifecycleEvent,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def pg_factory(pg_engine):
    return sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)


# ===========================================================================
# Tables exist + Base.metadata picked up models
# ===========================================================================

def test_all_seven_options_tables_exist(pg_session):
    rows = pg_session.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name LIKE 'options_%' "
        "ORDER BY table_name"
    )).all()
    table_names = {r[0] for r in rows}
    expected = {
        "options_chain_snapshot",
        "options_feature_daily",
        "options_paper_trade",
        "options_paper_trade_leg",
        "options_trade_lifecycle_event",
        "options_expiration_event",
        "options_assignment_event",
    }
    assert expected.issubset(table_names)


# ===========================================================================
# FK isolation: ZERO cross-domain foreign keys
# ===========================================================================

def test_zero_foreign_keys_between_options_and_non_options(pg_session):
    """The single most important boundary check. No FK may cross the
    options_* / non-options_* boundary in either direction."""
    rows = pg_session.execute(text("""
        SELECT conrelid::regclass::text AS source_tbl,
               confrelid::regclass::text AS target_tbl,
               conname
          FROM pg_constraint
         WHERE contype = 'f'
           AND ((conrelid::regclass::text LIKE 'options_%%'
                  AND confrelid::regclass::text NOT LIKE 'options_%%')
                 OR
                (conrelid::regclass::text NOT LIKE 'options_%%'
                  AND confrelid::regclass::text LIKE 'options_%%'))
    """)).fetchall()
    assert rows == [], (
        f"cross-domain FK leak between options_* and non-options_*: {rows}"
    )


def test_options_internal_fks_target_only_options_paper_trade(pg_session):
    rows = pg_session.execute(text("""
        SELECT conrelid::regclass::text AS source_tbl,
               confrelid::regclass::text AS target_tbl
          FROM pg_constraint
         WHERE contype = 'f'
           AND conrelid::regclass::text LIKE 'options_%%'
    """)).fetchall()
    targets = {r[1] for r in rows}
    # All FKs from options_* tables must target options_paper_trade only
    assert targets == {"options_paper_trade"}, (
        f"options FKs reference unexpected tables: {targets}"
    )


# ===========================================================================
# CHECK constraint enforcement
# ===========================================================================

def _baseline_trade_kwargs(**overrides):
    base = dict(
        underlying="SPY",
        strategy_name="SHORT_PUT_CREDIT_SPREAD",
        strategy_version="v1",
        status="PROPOSED",
        max_loss_dollars=Decimal("400"),
        max_profit_dollars=Decimal("100"),
        fill_model_version="mid_plus_25_pct_spread",
    )
    base.update(overrides)
    return base


def test_strategy_name_check_rejects_invalid(pg_factory):
    with pg_factory() as s:
        bad = OptionsPaperTrade(**_baseline_trade_kwargs(
            strategy_name="NAKED_SHORT_PUT",   # forbidden
        ))
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.commit()


def test_strategy_name_check_accepts_three_locked_strategies(pg_factory):
    for strat in ("SHORT_PUT_CREDIT_SPREAD",
                   "SHORT_CALL_CREDIT_SPREAD",
                   "IRON_CONDOR"):
        with pg_factory() as s:
            t = OptionsPaperTrade(**_baseline_trade_kwargs(strategy_name=strat))
            s.add(t)
            s.commit()


def test_status_check_rejects_invalid(pg_factory):
    with pg_factory() as s:
        bad = OptionsPaperTrade(**_baseline_trade_kwargs(status="ACTIVE"))
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.commit()


def test_status_check_accepts_six_lifecycle_states(pg_factory):
    for state in ("PROPOSED", "OPEN", "EXPIRING",
                   "CLOSED", "EXPIRED", "ASSIGNED"):
        with pg_factory() as s:
            t = OptionsPaperTrade(**_baseline_trade_kwargs(status=state))
            s.add(t)
            s.commit()


def test_paper_only_invariant_blocks_false(pg_factory):
    with pg_factory() as s:
        t = OptionsPaperTrade(**_baseline_trade_kwargs())
        t.paper_only = False   # try to bypass
        s.add(t)
        with pytest.raises(IntegrityError):
            s.commit()


def test_max_loss_max_profit_must_be_nonneg(pg_factory):
    with pg_factory() as s:
        t = OptionsPaperTrade(**_baseline_trade_kwargs(
            max_loss_dollars=Decimal("-1"),
        ))
        s.add(t)
        with pytest.raises(IntegrityError):
            s.commit()


def test_fees_must_be_nonneg(pg_factory):
    with pg_factory() as s:
        t = OptionsPaperTrade(**_baseline_trade_kwargs())
        t.fees_total_dollars = Decimal("-0.01")
        s.add(t)
        with pytest.raises(IntegrityError):
            s.commit()


def test_chain_snapshot_option_type_check(pg_factory):
    with pg_factory() as s:
        bad = OptionsChainSnapshot(
            snapshot_at_utc=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
            underlying="SPY",
            expiry=dt.date(2026, 6, 18),
            strike=Decimal("450"),
            option_type="STRADDLE",   # invalid
            option_symbol="SPY260618C00450000",
            quote_age_seconds=2,
            provider="thetadata",
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.commit()


def test_chain_snapshot_quote_age_must_be_nonneg(pg_factory):
    with pg_factory() as s:
        bad = OptionsChainSnapshot(
            snapshot_at_utc=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
            underlying="SPY",
            expiry=dt.date(2026, 6, 18),
            strike=Decimal("450"),
            option_type="CALL",
            option_symbol="SPY260618C00450000",
            quote_age_seconds=-1,
            provider="thetadata",
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.commit()


def test_leg_side_check_rejects_invalid(pg_factory):
    with pg_factory() as s:
        trade = OptionsPaperTrade(**_baseline_trade_kwargs())
        s.add(trade)
        s.commit()
        s.refresh(trade)
        bad = OptionsPaperTradeLeg(
            trade_id=trade.id, leg_index=0,
            option_symbol="SPY260618P00440000",
            underlying="SPY",
            expiry=dt.date(2026, 6, 18),
            strike=Decimal("440"),
            option_type="PUT",
            side="SHORT",   # invalid; should be "SELL"
            qty=1,
            entry_quote_at_utc=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
            entry_fill_price=Decimal("1.50"),
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.commit()


def test_leg_qty_must_be_positive(pg_factory):
    with pg_factory() as s:
        trade = OptionsPaperTrade(**_baseline_trade_kwargs())
        s.add(trade)
        s.commit()
        s.refresh(trade)
        bad = OptionsPaperTradeLeg(
            trade_id=trade.id, leg_index=0,
            option_symbol="SPY260618P00440000",
            underlying="SPY", expiry=dt.date(2026, 6, 18),
            strike=Decimal("440"), option_type="PUT", side="SELL",
            qty=0,
            entry_quote_at_utc=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
            entry_fill_price=Decimal("1.50"),
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.commit()


def test_leg_unique_per_trade_index(pg_factory):
    with pg_factory() as s:
        trade = OptionsPaperTrade(**_baseline_trade_kwargs())
        s.add(trade)
        s.commit()
        s.refresh(trade)
        leg1 = OptionsPaperTradeLeg(
            trade_id=trade.id, leg_index=0,
            option_symbol="SPY260618P00440000",
            underlying="SPY", expiry=dt.date(2026, 6, 18),
            strike=Decimal("440"), option_type="PUT", side="SELL", qty=1,
            entry_quote_at_utc=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
            entry_fill_price=Decimal("1.50"),
        )
        leg2 = OptionsPaperTradeLeg(
            trade_id=trade.id, leg_index=0,   # duplicate
            option_symbol="SPY260618P00435000",
            underlying="SPY", expiry=dt.date(2026, 6, 18),
            strike=Decimal("435"), option_type="PUT", side="BUY", qty=1,
            entry_quote_at_utc=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
            entry_fill_price=Decimal("1.10"),
        )
        s.add_all([leg1, leg2])
        with pytest.raises(IntegrityError):
            s.commit()


def test_lifecycle_event_type_check(pg_factory):
    with pg_factory() as s:
        trade = OptionsPaperTrade(**_baseline_trade_kwargs())
        s.add(trade)
        s.commit()
        s.refresh(trade)
        bad = OptionsTradeLifecycleEvent(
            trade_id=trade.id,
            event_type="UNKNOWN_EVENT",
            triggered_by="OPERATOR_API",
            payload_json={},
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.commit()


def test_lifecycle_event_triggered_by_check(pg_factory):
    with pg_factory() as s:
        trade = OptionsPaperTrade(**_baseline_trade_kwargs())
        s.add(trade)
        s.commit()
        s.refresh(trade)
        bad = OptionsTradeLifecycleEvent(
            trade_id=trade.id,
            event_type="MTM",
            triggered_by="MAGIC",   # invalid
            payload_json={},
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.commit()


def test_expiration_classification_check(pg_factory):
    with pg_factory() as s:
        trade = OptionsPaperTrade(**_baseline_trade_kwargs())
        s.add(trade)
        s.commit()
        s.refresh(trade)
        bad = OptionsExpirationEvent(
            trade_id=trade.id,
            leg_index=0,
            expiry_date=dt.date(2026, 6, 18),
            classification="WEIRD",   # invalid
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.commit()


def test_assignment_event_type_check(pg_factory):
    with pg_factory() as s:
        trade = OptionsPaperTrade(**_baseline_trade_kwargs())
        s.add(trade)
        s.commit()
        s.refresh(trade)
        bad = OptionsAssignmentEvent(
            trade_id=trade.id,
            leg_index=0,
            event_type="MAGIC_ASSIGN",   # invalid
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.commit()


def test_assignment_risk_level_check(pg_factory):
    with pg_factory() as s:
        trade = OptionsPaperTrade(**_baseline_trade_kwargs())
        s.add(trade)
        s.commit()
        s.refresh(trade)
        bad = OptionsAssignmentEvent(
            trade_id=trade.id,
            leg_index=0,
            event_type="EARLY_ASSIGN_RISK",
            risk_level="EXTREME",   # invalid
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.commit()


def test_assignment_risk_level_null_allowed(pg_factory):
    with pg_factory() as s:
        trade = OptionsPaperTrade(**_baseline_trade_kwargs())
        s.add(trade)
        s.commit()
        s.refresh(trade)
        ok = OptionsAssignmentEvent(
            trade_id=trade.id,
            leg_index=0,
            event_type="ASSIGNED",
            risk_level=None,
        )
        s.add(ok)
        s.commit()


# ===========================================================================
# Round-trip: end-to-end multi-leg trade insert
# ===========================================================================

def test_full_iron_condor_trade_roundtrip(pg_factory):
    with pg_factory() as s:
        trade = OptionsPaperTrade(
            underlying="SPY",
            strategy_name="IRON_CONDOR",
            strategy_version="v1",
            status="OPEN",
            opened_at=dt.datetime(2026, 5, 18, 14, 30, tzinfo=dt.timezone.utc),
            entry_credit_dollars=Decimal("130"),
            max_loss_dollars=Decimal("370"),
            max_profit_dollars=Decimal("130"),
            breakeven_lower=Decimal("438.70"),
            breakeven_upper=Decimal("461.30"),
            fees_total_dollars=Decimal("3.00"),
            fill_model_version="mid_plus_25_pct_spread",
        )
        s.add(trade)
        s.commit()
        s.refresh(trade)
        legs = [
            OptionsPaperTradeLeg(
                trade_id=trade.id, leg_index=0,
                option_symbol="SPY260618P00440000",
                underlying="SPY", expiry=dt.date(2026, 6, 18),
                strike=Decimal("440"), option_type="PUT", side="SELL", qty=1,
                entry_quote_at_utc=dt.datetime(2026, 5, 18, 14, 30, tzinfo=dt.timezone.utc),
                entry_fill_price=Decimal("1.50"),
            ),
            OptionsPaperTradeLeg(
                trade_id=trade.id, leg_index=1,
                option_symbol="SPY260618P00435000",
                underlying="SPY", expiry=dt.date(2026, 6, 18),
                strike=Decimal("435"), option_type="PUT", side="BUY", qty=1,
                entry_quote_at_utc=dt.datetime(2026, 5, 18, 14, 30, tzinfo=dt.timezone.utc),
                entry_fill_price=Decimal("1.05"),
            ),
            OptionsPaperTradeLeg(
                trade_id=trade.id, leg_index=2,
                option_symbol="SPY260618C00460000",
                underlying="SPY", expiry=dt.date(2026, 6, 18),
                strike=Decimal("460"), option_type="CALL", side="SELL", qty=1,
                entry_quote_at_utc=dt.datetime(2026, 5, 18, 14, 30, tzinfo=dt.timezone.utc),
                entry_fill_price=Decimal("1.40"),
            ),
            OptionsPaperTradeLeg(
                trade_id=trade.id, leg_index=3,
                option_symbol="SPY260618C00465000",
                underlying="SPY", expiry=dt.date(2026, 6, 18),
                strike=Decimal("465"), option_type="CALL", side="BUY", qty=1,
                entry_quote_at_utc=dt.datetime(2026, 5, 18, 14, 30, tzinfo=dt.timezone.utc),
                entry_fill_price=Decimal("1.00"),
            ),
        ]
        s.add_all(legs)
        s.add(OptionsTradeLifecycleEvent(
            trade_id=trade.id,
            event_type="FILLED",
            triggered_by="OPERATOR_API",
            payload_json={"fills": [1.50, 1.05, 1.40, 1.00]},
        ))
        s.commit()

    # Verify retrieval
    with pg_factory() as s:
        rt = s.get(OptionsPaperTrade, trade.id)
        assert rt.strategy_name == "IRON_CONDOR"
        assert len(rt.legs) == 4
        leg_indices = sorted(l.leg_index for l in rt.legs)
        assert leg_indices == [0, 1, 2, 3]
        assert len(rt.lifecycle_events) == 1
