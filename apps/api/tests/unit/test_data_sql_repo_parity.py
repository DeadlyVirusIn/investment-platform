"""Phase 10 — SQL-backed repo parity with Phase 9 in-memory semantics.

For identical inputs, SqlRepo output must match InMemoryRepo output
exactly — this is the Phase 10 non-negotiable guarantee.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.src.db import Base, models  # noqa: F401
from apps.api.src.domain.data.consensus.models import (
    ConsensusRecord,
    EstimateType,
    Metric,
)
from apps.api.src.domain.data.consensus.repo import InMemoryConsensusRepo
from apps.api.src.domain.data.consensus.sql_repo import SqlConsensusRepo
from apps.api.src.domain.data.earnings.models import EarningsEvent
from apps.api.src.domain.data.earnings.repo import InMemoryEarningsRepo
from apps.api.src.domain.data.earnings.sql_repo import SqlEarningsRepo
from apps.api.src.domain.data.pit_lookup import PITDataContext, PointInTimeDataError
from apps.api.src.domain.data.shares.models import SharesOutstandingRecord
from apps.api.src.domain.data.shares.repo import InMemorySharesRepo
from apps.api.src.domain.data.shares.sql_repo import SqlSharesRepo
from apps.api.src.domain.data.time import EventTime


@pytest.fixture
def sql_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(bind=engine, autoflush=False, future=True)
    yield session
    session.close()
    engine.dispose()


# Shared fixture data
EVENTS = [
    EarningsEvent(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        event_time=EventTime.AFTER_CLOSE,
        fiscal_period="Q2 2026", source="zacks",
    ),
    EarningsEvent(
        symbol="MSFT", asset_id="msft",
        event_date=dt.date(2026, 4, 24),
        event_time=EventTime.BEFORE_OPEN,
        fiscal_period="Q3 2026", source="zacks",
    ),
]

SHARES = [
    SharesOutstandingRecord(
        symbol="AAPL", asset_id="aapl",
        effective_date=dt.date(2025, 12, 31),
        filing_date=dt.date(2026, 2, 1),
        shares_outstanding=16_000_000_000, source="edgar",
    ),
    SharesOutstandingRecord(
        symbol="AAPL", asset_id="aapl",
        effective_date=dt.date(2026, 3, 31),
        filing_date=dt.date(2026, 5, 8),     # post-event -> MUST NOT leak
        shares_outstanding=15_900_000_000, source="edgar",
    ),
]

CONSENSUS = [
    ConsensusRecord(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        metric=Metric.EPS, estimate_type=EstimateType.CONSENSUS,
        value=1.45, as_of_date=dt.date(2026, 3, 1), source="refinitiv",
    ),
    ConsensusRecord(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        metric=Metric.EPS, estimate_type=EstimateType.CONSENSUS,
        value=1.50, as_of_date=dt.date(2026, 4, 10), source="refinitiv",
    ),
    # Post-event "revision" — must be ignored by PIT lookup
    ConsensusRecord(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        metric=Metric.EPS, estimate_type=EstimateType.CONSENSUS,
        value=1.70, as_of_date=dt.date(2026, 4, 25),
        source="refinitiv_late",
    ),
    ConsensusRecord(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        metric=Metric.REVENUE, estimate_type=EstimateType.CONSENSUS,
        value=95_000_000_000, as_of_date=dt.date(2026, 4, 15),
        source="refinitiv",
    ),
    ConsensusRecord(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        metric=Metric.EPS, estimate_type=EstimateType.ACTUAL,
        value=1.62, as_of_date=dt.date(2026, 4, 21), source="company",
    ),
    ConsensusRecord(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        metric=Metric.REVENUE, estimate_type=EstimateType.ACTUAL,
        value=93_000_000_000, as_of_date=dt.date(2026, 4, 21), source="company",
    ),
]


def _populate_inmem():
    e = InMemoryEarningsRepo()
    s = InMemorySharesRepo()
    c = InMemoryConsensusRepo()
    e.bulk_upsert(EVENTS); s.bulk_upsert(SHARES); c.bulk_upsert(CONSENSUS)
    return e, s, c


def _populate_sql(session):
    e = SqlEarningsRepo(session)
    s = SqlSharesRepo(session)
    c = SqlConsensusRepo(session)
    e.bulk_upsert(EVENTS); s.bulk_upsert(SHARES); c.bulk_upsert(CONSENSUS)
    session.commit()
    return e, s, c


class TestEarningsParity:
    def test_get_event_match(self, sql_session):
        mem_e, _, _ = _populate_inmem()
        sql_e, _, _ = _populate_sql(sql_session)
        mem = mem_e.get_event("AAPL", dt.date(2026, 4, 21))
        sql = sql_e.get_event("AAPL", dt.date(2026, 4, 21))
        assert mem == sql

    def test_get_events_on_match(self, sql_session):
        mem_e, _, _ = _populate_inmem()
        sql_e, _, _ = _populate_sql(sql_session)
        mem = sorted(mem_e.get_events_on(dt.date(2026, 4, 21)), key=lambda e: e.symbol)
        sql = sorted(sql_e.get_events_on(dt.date(2026, 4, 21)), key=lambda e: e.symbol)
        assert mem == sql


class TestSharesParity:
    def test_get_as_of_pit_match(self, sql_session):
        _, mem_s, _ = _populate_inmem()
        _, sql_s, _ = _populate_sql(sql_session)
        for as_of in [
            dt.date(2026, 1, 15),  # pre-first-filing
            dt.date(2026, 2, 1),   # boundary
            dt.date(2026, 4, 21),  # event day
            dt.date(2026, 5, 8),   # post-event filing boundary
            dt.date(2026, 6, 1),   # after second filing
        ]:
            assert mem_s.get_as_of("AAPL", as_of) == sql_s.get_as_of("AAPL", as_of)


class TestConsensusParity:
    def test_get_consensus_strict_less_than_match(self, sql_session):
        _, _, mem_c = _populate_inmem()
        _, _, sql_c = _populate_sql(sql_session)
        mem = mem_c.get_consensus(
            "AAPL", dt.date(2026, 4, 21), Metric.EPS, dt.date(2026, 4, 21),
        )
        sql = sql_c.get_consensus(
            "AAPL", dt.date(2026, 4, 21), Metric.EPS, dt.date(2026, 4, 21),
        )
        assert mem == sql
        assert mem.value == 1.50  # pre-event 4/10 wins; NOT 1.45 nor 1.70

    def test_get_actual_match(self, sql_session):
        _, _, mem_c = _populate_inmem()
        _, _, sql_c = _populate_sql(sql_session)
        for metric in (Metric.EPS, Metric.REVENUE):
            mem = mem_c.get_actual("AAPL", dt.date(2026, 4, 21), metric)
            sql = sql_c.get_actual("AAPL", dt.date(2026, 4, 21), metric)
            assert mem == sql


class TestPITContextParity:
    def test_build_event_record_match(self, sql_session):
        mem_e, mem_s, mem_c = _populate_inmem()
        sql_e, sql_s, sql_c = _populate_sql(sql_session)
        mem_ctx = PITDataContext(earnings=mem_e, shares=mem_s, consensus=mem_c)
        sql_ctx = PITDataContext(earnings=sql_e, shares=sql_s, consensus=sql_c)
        mem_rec = mem_ctx.build_event_record("AAPL", dt.date(2026, 4, 21))
        sql_rec = sql_ctx.build_event_record("AAPL", dt.date(2026, 4, 21))
        # Compare key fields
        assert mem_rec.eps_consensus == sql_rec.eps_consensus == 1.50
        assert mem_rec.eps_actual == sql_rec.eps_actual == 1.62
        assert (
            mem_rec.shares_outstanding_as_of_event
            == sql_rec.shares_outstanding_as_of_event
            == 16_000_000_000
        )
        # Lookahead invariants: post-event 1.70 NOT used; 5/8 filing NOT used
        assert mem_rec.eps_consensus != 1.70
        assert mem_rec.shares_outstanding_as_of_event != 15_900_000_000
        assert sql_rec.eps_consensus != 1.70
        assert sql_rec.shares_outstanding_as_of_event != 15_900_000_000
        # Completeness + quality should match
        assert mem_rec.completeness.count == sql_rec.completeness.count
        assert mem_rec.quality == sql_rec.quality

    def test_require_consensus_raises_on_both(self, sql_session):
        mem_e, mem_s, mem_c = _populate_inmem()
        sql_e, sql_s, sql_c = _populate_sql(sql_session)
        mem_ctx = PITDataContext(earnings=mem_e, shares=mem_s, consensus=mem_c)
        sql_ctx = PITDataContext(earnings=sql_e, shares=sql_s, consensus=sql_c)
        # MSFT has no consensus at all
        with pytest.raises(PointInTimeDataError):
            mem_ctx.build_event_record(
                "MSFT", dt.date(2026, 4, 24), require_consensus=True,
            )
        with pytest.raises(PointInTimeDataError):
            sql_ctx.build_event_record(
                "MSFT", dt.date(2026, 4, 24), require_consensus=True,
            )
