"""Phase 9 — consensus / actual PIT tests."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.data.consensus.models import (
    ConsensusRecord,
    EstimateType,
    Metric,
)
from apps.api.src.domain.data.consensus.repo import InMemoryConsensusRepo


def _cons(
    symbol: str = "AAPL",
    event_date: dt.date | None = None,
    metric: Metric = Metric.EPS,
    estimate_type: EstimateType = EstimateType.CONSENSUS,
    value: float = 1.50,
    as_of: dt.date | None = None,
    source: str = "refinitiv",
) -> ConsensusRecord:
    return ConsensusRecord(
        symbol=symbol, asset_id=symbol.lower(),
        event_date=event_date or dt.date(2026, 4, 21),
        metric=metric, estimate_type=estimate_type,
        value=value,
        as_of_date=as_of or dt.date(2026, 4, 1),
        source=source,
    )


class TestModelInvariants:
    def test_metric_must_be_enum(self):
        with pytest.raises(TypeError):
            ConsensusRecord(
                symbol="X", asset_id="x",
                event_date=dt.date(2026, 4, 21),
                metric="eps",   # type: ignore
                estimate_type=EstimateType.CONSENSUS,
                value=1.0, as_of_date=dt.date(2026, 4, 1),
            )

    def test_estimate_type_must_be_enum(self):
        with pytest.raises(TypeError):
            ConsensusRecord(
                symbol="X", asset_id="x",
                event_date=dt.date(2026, 4, 21),
                metric=Metric.EPS,
                estimate_type="consensus",   # type: ignore
                value=1.0, as_of_date=dt.date(2026, 4, 1),
            )


class TestConsensusPIT:
    def test_strict_less_than_pre_event(self):
        """Consensus must be PUBLISHED strictly before as_of."""
        repo = InMemoryConsensusRepo()
        repo.upsert(_cons(as_of=dt.date(2026, 4, 1), value=1.50))
        # Lookup as_of=2026-04-21 -> 4/1 < 4/21 -> included
        got = repo.get_consensus(
            "AAPL", dt.date(2026, 4, 21), Metric.EPS, dt.date(2026, 4, 21),
        )
        assert got is not None
        assert got.value == 1.50

    def test_as_of_equal_to_event_excluded(self):
        """Consensus published ON the event day is excluded (could be
        post-announcement revision)."""
        repo = InMemoryConsensusRepo()
        repo.upsert(_cons(as_of=dt.date(2026, 4, 21), value=1.50))
        got = repo.get_consensus(
            "AAPL", dt.date(2026, 4, 21), Metric.EPS, dt.date(2026, 4, 21),
        )
        assert got is None

    def test_latest_pre_event_revision_wins(self):
        """Among multiple consensus revisions, pick the most recent
        that is still < as_of."""
        repo = InMemoryConsensusRepo()
        repo.upsert(_cons(as_of=dt.date(2026, 3, 20), value=1.40))
        repo.upsert(_cons(as_of=dt.date(2026, 4, 10), value=1.50))
        repo.upsert(_cons(as_of=dt.date(2026, 4, 22), value=1.55))  # post-event
        got = repo.get_consensus(
            "AAPL", dt.date(2026, 4, 21), Metric.EPS, dt.date(2026, 4, 21),
        )
        assert got.value == 1.50   # NOT the post-event 1.55

    def test_no_record_returns_none(self):
        repo = InMemoryConsensusRepo()
        got = repo.get_consensus(
            "AAPL", dt.date(2026, 4, 21), Metric.EPS, dt.date(2026, 4, 21),
        )
        assert got is None

    def test_metric_isolation(self):
        repo = InMemoryConsensusRepo()
        repo.upsert(_cons(metric=Metric.EPS, value=1.50))
        repo.upsert(_cons(metric=Metric.REVENUE, value=50_000_000))
        eps = repo.get_consensus(
            "AAPL", dt.date(2026, 4, 21), Metric.EPS, dt.date(2026, 4, 21),
        )
        rev = repo.get_consensus(
            "AAPL", dt.date(2026, 4, 21), Metric.REVENUE, dt.date(2026, 4, 21),
        )
        assert eps.value == 1.50
        assert rev.value == 50_000_000


class TestActualVsConsensus:
    def test_actual_and_consensus_are_separate(self):
        repo = InMemoryConsensusRepo()
        repo.upsert(_cons(
            estimate_type=EstimateType.CONSENSUS,
            value=1.50, as_of=dt.date(2026, 4, 10),
        ))
        repo.upsert(_cons(
            estimate_type=EstimateType.ACTUAL,
            value=1.60, as_of=dt.date(2026, 4, 21),
        ))
        cons = repo.get_consensus(
            "AAPL", dt.date(2026, 4, 21), Metric.EPS, dt.date(2026, 4, 21),
        )
        actual = repo.get_actual("AAPL", dt.date(2026, 4, 21), Metric.EPS)
        assert cons.value == 1.50
        assert actual.value == 1.60

    def test_actual_latest_revision_wins(self):
        repo = InMemoryConsensusRepo()
        repo.upsert(_cons(
            estimate_type=EstimateType.ACTUAL, value=1.60,
            as_of=dt.date(2026, 4, 21),
        ))
        # Restatement next quarter
        repo.upsert(_cons(
            estimate_type=EstimateType.ACTUAL, value=1.58,
            as_of=dt.date(2026, 7, 22),
        ))
        got = repo.get_actual("AAPL", dt.date(2026, 4, 21), Metric.EPS)
        assert got.value == 1.58   # latest restatement

    def test_actual_as_of_respects_cutoff(self):
        """Strict PIT: actual with as_of=T does not see T+N revisions."""
        repo = InMemoryConsensusRepo()
        repo.upsert(_cons(
            estimate_type=EstimateType.ACTUAL, value=1.60,
            as_of=dt.date(2026, 4, 21),
        ))
        repo.upsert(_cons(
            estimate_type=EstimateType.ACTUAL, value=1.58,
            as_of=dt.date(2026, 7, 22),
        ))
        got = repo.get_actual_as_of(
            "AAPL", dt.date(2026, 4, 21), Metric.EPS, dt.date(2026, 5, 1),
        )
        assert got.value == 1.60   # pre-restatement
