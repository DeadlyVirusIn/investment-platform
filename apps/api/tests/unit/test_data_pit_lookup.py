"""Phase 9 — unified PITDataContext integration tests."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.data.consensus.models import (
    ConsensusRecord,
    EstimateType,
    Metric,
)
from apps.api.src.domain.data.consensus.repo import InMemoryConsensusRepo
from apps.api.src.domain.data.earnings.models import EarningsEvent
from apps.api.src.domain.data.earnings.repo import InMemoryEarningsRepo
from apps.api.src.domain.data.pit_lookup import (
    PITDataContext,
    PointInTimeDataError,
)
from apps.api.src.domain.data.shares.models import SharesOutstandingRecord
from apps.api.src.domain.data.shares.repo import InMemorySharesRepo
from apps.api.src.domain.data.time import EventTime


def _fixture_ctx():
    e = InMemoryEarningsRepo()
    s = InMemorySharesRepo()
    c = InMemoryConsensusRepo()
    # Earnings event for AAPL 2026-04-21 after close -> tradable 2026-04-22
    e.upsert(EarningsEvent(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        event_time=EventTime.AFTER_CLOSE,
        fiscal_period="Q2 2026", source="zacks",
    ))
    # Shares filed 2026-02-01 effective 2025-12-31 = 16B
    s.upsert(SharesOutstandingRecord(
        symbol="AAPL", asset_id="aapl",
        effective_date=dt.date(2025, 12, 31),
        filing_date=dt.date(2026, 2, 1),
        shares_outstanding=16_000_000_000,
        source="edgar",
    ))
    # Consensus EPS 1.50 pre-event (as_of 2026-04-10)
    c.upsert(ConsensusRecord(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        metric=Metric.EPS, estimate_type=EstimateType.CONSENSUS,
        value=1.50, as_of_date=dt.date(2026, 4, 10),
        source="refinitiv",
    ))
    # Consensus Revenue 95B
    c.upsert(ConsensusRecord(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        metric=Metric.REVENUE, estimate_type=EstimateType.CONSENSUS,
        value=95_000_000_000, as_of_date=dt.date(2026, 4, 15),
        source="refinitiv",
    ))
    # Actual EPS reported 2026-04-21 at 1.62
    c.upsert(ConsensusRecord(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        metric=Metric.EPS, estimate_type=EstimateType.ACTUAL,
        value=1.62, as_of_date=dt.date(2026, 4, 21),
        source="company",
    ))
    # Actual Revenue 93B (miss)
    c.upsert(ConsensusRecord(
        symbol="AAPL", asset_id="aapl",
        event_date=dt.date(2026, 4, 21),
        metric=Metric.REVENUE, estimate_type=EstimateType.ACTUAL,
        value=93_000_000_000, as_of_date=dt.date(2026, 4, 21),
        source="company",
    ))
    return PITDataContext(earnings=e, shares=s, consensus=c)


class TestPITContext:
    def test_get_events_on(self):
        ctx = _fixture_ctx()
        got = ctx.get_events_on(dt.date(2026, 4, 21))
        assert len(got) == 1
        assert got[0].symbol == "AAPL"

    def test_get_event_missing_returns_none(self):
        ctx = _fixture_ctx()
        assert ctx.get_event("NONE", dt.date(2026, 4, 21)) is None

    def test_get_shares_pit(self):
        ctx = _fixture_ctx()
        s = ctx.get_shares_outstanding("AAPL", dt.date(2026, 4, 21))
        assert s.shares_outstanding == 16_000_000_000

    def test_build_event_record_happy_path(self):
        ctx = _fixture_ctx()
        rec = ctx.build_event_record("AAPL", dt.date(2026, 4, 21))
        assert rec.symbol == "AAPL"
        assert rec.event_time == EventTime.AFTER_CLOSE
        assert rec.tradable_date == dt.date(2026, 4, 22)
        assert rec.eps_consensus == 1.50
        assert rec.eps_actual == 1.62
        assert rec.revenue_consensus == 95_000_000_000
        assert rec.revenue_actual == 93_000_000_000
        assert rec.shares_outstanding_as_of_event == 16_000_000_000
        assert rec.consensus_as_of == dt.date(2026, 4, 21)
        assert rec.shares_as_of == dt.date(2026, 4, 21)
        # Provenance
        assert rec.source_earnings == "zacks"
        assert rec.source_shares == "edgar"
        assert rec.source_consensus_eps == "refinitiv"

    def test_build_event_record_missing_event_raises(self):
        ctx = _fixture_ctx()
        with pytest.raises(PointInTimeDataError):
            ctx.build_event_record("NONE", dt.date(2026, 4, 21))

    def test_missing_consensus_allowed_by_default(self):
        """By default, missing consensus -> None field (not raise)."""
        ctx = _fixture_ctx()
        # Add a second event with NO consensus records
        ctx.earnings.upsert(EarningsEvent(
            symbol="MSFT", asset_id="msft",
            event_date=dt.date(2026, 4, 22),
            event_time=EventTime.AFTER_CLOSE, source="zacks",
        ))
        rec = ctx.build_event_record("MSFT", dt.date(2026, 4, 22))
        assert rec.eps_consensus is None
        assert rec.revenue_consensus is None

    def test_require_consensus_raises_when_missing(self):
        ctx = _fixture_ctx()
        ctx.earnings.upsert(EarningsEvent(
            symbol="MSFT", asset_id="msft",
            event_date=dt.date(2026, 4, 22),
            event_time=EventTime.AFTER_CLOSE, source="zacks",
        ))
        with pytest.raises(PointInTimeDataError):
            ctx.build_event_record(
                "MSFT", dt.date(2026, 4, 22), require_consensus=True,
            )

    def test_require_shares_raises_when_missing(self):
        ctx = _fixture_ctx()
        ctx.earnings.upsert(EarningsEvent(
            symbol="NVDA", asset_id="nvda",
            event_date=dt.date(2026, 4, 21),
            event_time=EventTime.AFTER_CLOSE, source="zacks",
        ))
        with pytest.raises(PointInTimeDataError):
            ctx.build_event_record(
                "NVDA", dt.date(2026, 4, 21), require_shares=True,
            )


class TestLookaheadBiasInvariants:
    """These are the most important tests — directly enforce PIT."""

    def test_consensus_revised_after_event_not_used(self):
        """If a consensus is published on the event day it must NOT be
        used in the EventRecord assembly for that date."""
        ctx = _fixture_ctx()
        # Add a same-day "revision" — should be ignored by build_event_record
        ctx.consensus.upsert(ConsensusRecord(
            symbol="AAPL", asset_id="aapl",
            event_date=dt.date(2026, 4, 21),
            metric=Metric.EPS, estimate_type=EstimateType.CONSENSUS,
            value=1.70, as_of_date=dt.date(2026, 4, 21),
            source="refinitiv_revision",
        ))
        rec = ctx.build_event_record("AAPL", dt.date(2026, 4, 21))
        assert rec.eps_consensus == 1.50   # pre-event 4/10 wins

    def test_shares_filed_after_event_not_used(self):
        """Shares filed after event_date must NOT be used in the
        EventRecord whose shares_as_of=event_date."""
        ctx = _fixture_ctx()
        # New filing after event
        ctx.shares.upsert(SharesOutstandingRecord(
            symbol="AAPL", asset_id="aapl",
            effective_date=dt.date(2026, 3, 31),
            filing_date=dt.date(2026, 5, 10),   # > event_date
            shares_outstanding=15_900_000_000,
            source="edgar",
        ))
        rec = ctx.build_event_record("AAPL", dt.date(2026, 4, 21))
        # Must still be the 2026-02-01-filed 16B, not the 5/10 15.9B
        assert rec.shares_outstanding_as_of_event == 16_000_000_000


class TestUnknownEventTimeConservative:
    def test_unknown_event_time_forces_next_bd(self):
        """UNKNOWN must NOT allow same-day trading in the unified record."""
        e = InMemoryEarningsRepo()
        s = InMemorySharesRepo()
        c = InMemoryConsensusRepo()
        e.upsert(EarningsEvent(
            symbol="X", asset_id="x",
            event_date=dt.date(2026, 4, 21),
            event_time=EventTime.UNKNOWN, source="feed",
        ))
        ctx = PITDataContext(earnings=e, shares=s, consensus=c)
        rec = ctx.build_event_record("X", dt.date(2026, 4, 21))
        assert rec.tradable_date == dt.date(2026, 4, 22)
