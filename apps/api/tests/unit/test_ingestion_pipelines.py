"""Phase 10 — ingestion pipelines + validation report."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.src.db import Base, models  # noqa: F401
from apps.api.src.db.models import (
    ConsensusEstimateRow,
    EarningsEventRow,
    EventQuarantine,
    RawEarningsIngestion,
    SharesOutstandingRow,
)
from apps.api.src.ingestion.consensus import ingest_consensus
from apps.api.src.ingestion.earnings import ingest_earnings
from apps.api.src.ingestion.shares import ingest_shares
from apps.api.src.ingestion.validation import run_validation


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    s = Session(bind=engine, autoflush=False, future=True)
    yield s
    s.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Earnings ingestion
# ---------------------------------------------------------------------------


class TestEarningsIngest:
    def test_happy_path(self, session):
        result = ingest_earnings(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "event_time": "after_close",
            "announcement_timestamp": "2026-04-21T20:30:00Z",
            "announcement_timestamp_raw": "04/21/2026 4:30 PM ET",
            "fiscal_period": "Q2 2026", "source": "zacks",
            "external_id": "zacks-aapl-2026q2",
        }])
        assert result.inserted == 1
        assert result.quarantined == 0
        row = session.execute(select(EarningsEventRow)).scalar_one()
        assert row.symbol == "AAPL"
        assert row.event_time == "after_close"
        assert row.announcement_timestamp_raw == "04/21/2026 4:30 PM ET"

    def test_before_open_preserved(self, session):
        ingest_earnings(session, [{
            "asset_id": "msft", "symbol": "MSFT",
            "event_date": "2026-04-24", "event_time": "before_open",
            "source": "zacks",
        }])
        row = session.execute(select(EarningsEventRow)).scalar_one()
        assert row.event_time == "before_open"

    def test_unknown_preserved(self, session):
        ingest_earnings(session, [{
            "asset_id": "x", "symbol": "X",
            "event_date": "2026-04-21", "event_time": "unknown",
            "source": "feed",
        }])
        row = session.execute(select(EarningsEventRow)).scalar_one()
        assert row.event_time == "unknown"

    def test_malformed_timestamp_quarantined(self, session):
        result = ingest_earnings(session, [{
            "asset_id": "x", "symbol": "X",
            "event_date": "2026-04-21", "event_time": "after_close",
            "announcement_timestamp": "not-a-timestamp",
            "source": "feed",
        }])
        assert result.quarantined == 1
        assert "bad_announcement_timestamp" in result.quarantine_reasons
        assert session.execute(
            select(func.count(EarningsEventRow.id))
        ).scalar_one() == 0
        q = session.execute(select(EventQuarantine)).scalar_one()
        assert q.reason == "bad_announcement_timestamp"
        # Raw row still recorded
        raw = session.execute(select(RawEarningsIngestion)).scalar_one()
        assert raw.status == "rejected"

    def test_missing_required_field_quarantined(self, session):
        result = ingest_earnings(session, [{
            "asset_id": "x", "symbol": "X",
            # missing event_date + event_time
            "source": "feed",
        }])
        assert result.quarantined == 1
        assert "missing_required_field" in result.quarantine_reasons

    def test_bad_event_time_quarantined(self, session):
        result = ingest_earnings(session, [{
            "asset_id": "x", "symbol": "X",
            "event_date": "2026-04-21", "event_time": "midday",
            "source": "feed",
        }])
        assert result.quarantined == 1
        assert "bad_event_time" in result.quarantine_reasons

    def test_idempotent_rerun(self, session):
        rec = {
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "event_time": "after_close",
            "source": "zacks",
        }
        r1 = ingest_earnings(session, [rec])
        r2 = ingest_earnings(session, [rec])
        assert r1.inserted == 1
        assert r2.inserted == 0
        assert r2.updated == 1
        assert session.execute(
            select(func.count(EarningsEventRow.id))
        ).scalar_one() == 1

    def test_dry_run_no_writes(self, session):
        ingest_earnings(session, [{
            "asset_id": "x", "symbol": "X",
            "event_date": "2026-04-21", "event_time": "after_close",
            "source": "feed",
        }], dry_run=True)
        assert session.execute(
            select(func.count(EarningsEventRow.id))
        ).scalar_one() == 0


# ---------------------------------------------------------------------------
# Shares ingestion
# ---------------------------------------------------------------------------


class TestSharesIngest:
    def test_happy_path(self, session):
        result = ingest_shares(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "effective_date": "2025-12-31", "filing_date": "2026-02-01",
            "shares_outstanding": 16_000_000_000, "source": "edgar",
        }])
        assert result.inserted == 1
        assert result.quarantined == 0

    def test_filing_before_effective_rejected(self, session):
        result = ingest_shares(session, [{
            "asset_id": "x", "symbol": "X",
            "effective_date": "2026-05-15", "filing_date": "2026-03-31",
            "shares_outstanding": 1000, "source": "edgar",
        }])
        assert result.quarantined == 1
        assert "filing_before_effective" in result.quarantine_reasons

    def test_negative_shares_rejected(self, session):
        result = ingest_shares(session, [{
            "asset_id": "x", "symbol": "X",
            "effective_date": "2026-03-31", "filing_date": "2026-05-01",
            "shares_outstanding": -1, "source": "edgar",
        }])
        assert result.quarantined == 1
        assert "negative_shares" in result.quarantine_reasons

    def test_comma_formatted_shares_accepted(self, session):
        ingest_shares(session, [{
            "asset_id": "x", "symbol": "X",
            "effective_date": "2026-03-31", "filing_date": "2026-05-01",
            "shares_outstanding": "16,000,000,000", "source": "edgar",
        }])
        row = session.execute(select(SharesOutstandingRow)).scalar_one()
        assert row.shares_outstanding == 16_000_000_000


# ---------------------------------------------------------------------------
# Consensus ingestion
# ---------------------------------------------------------------------------


class TestConsensusIngest:
    def test_happy_path(self, session):
        result = ingest_consensus(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21",
            "metric": "eps", "estimate_type": "consensus",
            "value": 1.50, "value_unit": "usd_per_share",
            "as_of_date": "2026-04-10",
            "source": "refinitiv",
        }])
        assert result.inserted == 1
        assert result.quarantined == 0

    def test_revisions_preserved_historically(self, session):
        """Two revisions with different as_of_date are TWO rows, not one."""
        ingest_consensus(session, [
            {
                "asset_id": "aapl", "symbol": "AAPL",
                "event_date": "2026-04-21",
                "metric": "eps", "estimate_type": "consensus",
                "value": 1.45, "value_unit": "usd_per_share",
                "as_of_date": "2026-03-01",
                "source": "refinitiv",
            },
            {
                "asset_id": "aapl", "symbol": "AAPL",
                "event_date": "2026-04-21",
                "metric": "eps", "estimate_type": "consensus",
                "value": 1.50, "value_unit": "usd_per_share",
                "as_of_date": "2026-04-10",
                "source": "refinitiv",
            },
        ])
        count = session.execute(
            select(func.count(ConsensusEstimateRow.id))
        ).scalar_one()
        assert count == 2

    def test_consensus_and_actual_separate(self, session):
        ingest_consensus(session, [
            {
                "asset_id": "aapl", "symbol": "AAPL",
                "event_date": "2026-04-21", "metric": "eps",
                "estimate_type": "consensus", "value": 1.50,
                "value_unit": "usd_per_share",
                "as_of_date": "2026-04-10", "source": "refinitiv",
            },
            {
                "asset_id": "aapl", "symbol": "AAPL",
                "event_date": "2026-04-21", "metric": "eps",
                "estimate_type": "actual", "value": 1.62,
                "value_unit": "usd_per_share",
                "as_of_date": "2026-04-21", "source": "company",
            },
        ])
        count = session.execute(
            select(func.count(ConsensusEstimateRow.id))
        ).scalar_one()
        assert count == 2

    def test_bad_metric_rejected(self, session):
        result = ingest_consensus(session, [{
            "asset_id": "x", "symbol": "X",
            "event_date": "2026-04-21", "metric": "ebitda",
            "estimate_type": "consensus", "value": 1.0,
            "value_unit": "usd_per_share",
            "as_of_date": "2026-04-10", "source": "feed",
        }])
        assert result.quarantined == 1
        assert "bad_metric" in result.quarantine_reasons

    def test_bad_estimate_type_rejected(self, session):
        result = ingest_consensus(session, [{
            "asset_id": "x", "symbol": "X",
            "event_date": "2026-04-21", "metric": "eps",
            "estimate_type": "forecast", "value": 1.0,
            "value_unit": "usd_per_share",
            "as_of_date": "2026-04-10", "source": "feed",
        }])
        assert result.quarantined == 1
        assert "bad_estimate_type" in result.quarantine_reasons

    def test_nan_value_rejected(self, session):
        result = ingest_consensus(session, [{
            "asset_id": "x", "symbol": "X",
            "event_date": "2026-04-21", "metric": "eps",
            "estimate_type": "consensus", "value": float("nan"),
            "value_unit": "usd_per_share",
            "as_of_date": "2026-04-10", "source": "feed",
        }])
        assert result.quarantined == 1
        assert "bad_value" in result.quarantine_reasons


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------


class TestValidationReport:
    def test_empty_db(self, session):
        report = run_validation(session)
        assert report.earnings_events == 0
        assert report.pct_with_eps_actual == 0.0

    def test_completeness_calculation(self, session):
        # 1 earnings, 1 shares, 1 eps consensus, 1 eps actual
        ingest_earnings(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "event_time": "after_close",
            "source": "zacks",
        }])
        ingest_shares(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "effective_date": "2025-12-31", "filing_date": "2026-02-01",
            "shares_outstanding": 16_000_000_000, "source": "edgar",
        }])
        ingest_consensus(session, [
            {
                "asset_id": "aapl", "symbol": "AAPL",
                "event_date": "2026-04-21", "metric": "eps",
                "estimate_type": "consensus", "value": 1.50,
                "value_unit": "usd_per_share",
                "as_of_date": "2026-04-10", "source": "refinitiv",
            },
            {
                "asset_id": "aapl", "symbol": "AAPL",
                "event_date": "2026-04-21", "metric": "eps",
                "estimate_type": "actual", "value": 1.62,
                "value_unit": "usd_per_share",
                "as_of_date": "2026-04-21", "source": "company",
            },
        ])
        # Completeness test doesn't involve report for consensus+actual;
        # recall previous assertion set uses run_validation. Keep reuse.
        report = run_validation(session)
        assert report.earnings_events == 1
        assert report.shares_records == 1
        assert report.consensus_records == 2
        # One event with EPS actual, EPS consensus, and shares present
        assert report.pct_with_eps_actual == 1.0
        assert report.pct_with_eps_consensus == 1.0
        # No revenue records in this test
        assert report.pct_with_revenue_actual == 0.0
        assert report.pct_with_revenue_consensus == 0.0
        assert report.pct_with_shares == 1.0
        # No orphans
        assert report.orphan_events_without_actual == 0
        assert report.invalid_chronology_count == 0

    def test_quarantine_breakdown(self, session):
        ingest_earnings(session, [
            {"asset_id": "x", "symbol": "X",
             "event_date": "bad", "event_time": "after_close",
             "source": "feed"},
            {"asset_id": "y", "symbol": "Y",
             "event_date": "2026-04-21", "event_time": "midday",
             "source": "feed"},
        ])
        report = run_validation(session)
        assert report.quarantine_by_reason["bad_event_date"] == 1
        assert report.quarantine_by_reason["bad_event_time"] == 1
        assert report.quarantine_by_source_type["earnings"] == 2
