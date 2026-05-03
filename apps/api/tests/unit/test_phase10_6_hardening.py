"""Phase 10.6 tests — timezone / units / content_hash / expanded validation.

All tests use SQLite in-memory via create_all(), so they exercise the
ORM models + indexes + constraints exactly as migration 022 defines them.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.src.db import Base
from apps.api.src.db import models  # noqa: F401
from apps.api.src.db.models import (
    ConsensusEstimateRow,
    EarningsEventRow,
    EventQuarantine,
    RawConsensusIngestion,
    RawEarningsIngestion,
    RawSharesIngestion,
)
from apps.api.src.ingestion.adapters.et_earnings import normalize_et_records
from apps.api.src.ingestion.consensus import ingest_consensus
from apps.api.src.ingestion.content_hash import (
    canonical_hash,
    consensus_content_hash,
    earnings_content_hash,
    shares_content_hash,
)
from apps.api.src.ingestion.earnings import ingest_earnings
from apps.api.src.ingestion.shares import ingest_shares
from apps.api.src.ingestion.units import (
    UnitError,
    ValueUnit,
    canonical_unit_for,
    normalize_to_canonical,
    parse_unit,
)
from apps.api.src.ingestion.validation import run_validation

ET = ZoneInfo("America/New_York")


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    s = Session(bind=engine, autoflush=False, future=True)
    yield s
    s.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Timezone — strict rules
# ---------------------------------------------------------------------------


class TestTimezoneStrict:
    def test_naive_rejected_without_source_timezone(self, session):
        res = ingest_earnings(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "event_time": "after_close",
            "announcement_timestamp": "2026-04-21T16:30:00",   # naive
            "source": "zacks",
        }])
        assert res.quarantined == 1
        assert "naive_timestamp" in res.quarantine_reasons
        q = session.execute(select(EventQuarantine)).scalar_one()
        assert q.reason == "naive_timestamp"

    def test_naive_accepted_with_source_timezone(self, session):
        res = ingest_earnings(
            session,
            [{
                "asset_id": "aapl", "symbol": "AAPL",
                "event_date": "2026-04-21", "event_time": "after_close",
                "announcement_timestamp": dt.datetime(2026, 4, 21, 16, 30),
                "source": "zacks",
            }],
            source_timezone=ET,
        )
        assert res.inserted == 1
        row = session.execute(select(EarningsEventRow)).scalar_one()
        # 16:30 ET = 20:30 UTC in April (EDT, UTC-4). SQLite strips tz on
        # readback; coerce to UTC to compare values.
        ts = row.announcement_timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        assert ts == dt.datetime(2026, 4, 21, 20, 30, tzinfo=dt.timezone.utc)

    def test_aware_utc_passthrough(self, session):
        res = ingest_earnings(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "event_time": "after_close",
            "announcement_timestamp": "2026-04-21T20:30:00Z",
            "source": "zacks",
        }])
        assert res.inserted == 1

    def test_et_adapter_normalizes_naive(self):
        recs = [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "event_time": "after_close",
            "announcement_timestamp": "2026-04-21T16:30:00",   # naive ET
            "source": "zacks",
        }]
        out = normalize_et_records(recs)
        ts = out[0]["announcement_timestamp"]
        assert isinstance(ts, dt.datetime)
        assert ts.tzinfo is not None
        # 16:30 ET -> 20:30 UTC (EDT)
        assert ts == dt.datetime(2026, 4, 21, 20, 30, tzinfo=dt.timezone.utc)
        # Raw preserved
        assert "announcement_timestamp_raw" in out[0]

    def test_et_adapter_aware_passthrough(self):
        already_aware = dt.datetime(2026, 4, 21, 20, 30, tzinfo=dt.timezone.utc)
        recs = [{"announcement_timestamp": already_aware, "source": "zacks"}]
        out = normalize_et_records(recs)
        assert out[0]["announcement_timestamp"] == already_aware

    def test_before_open_et_conversion(self):
        """7:00 AM ET = 11:00 UTC (EDT) — still BEFORE_OPEN same day."""
        recs = [{
            "event_date": "2026-04-21", "event_time": "before_open",
            "announcement_timestamp": dt.datetime(2026, 4, 21, 7, 0),
            "source": "zacks",
        }]
        out = normalize_et_records(recs)
        assert out[0]["announcement_timestamp"] == dt.datetime(
            2026, 4, 21, 11, 0, tzinfo=dt.timezone.utc,
        )


# ---------------------------------------------------------------------------
# Units — strict enforcement
# ---------------------------------------------------------------------------


class TestUnitEnforcement:
    def test_missing_unit_rejected(self, session):
        res = ingest_consensus(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "metric": "revenue",
            "estimate_type": "consensus", "value": 95e9,
            # NO value_unit
            "as_of_date": "2026-04-10", "source": "refinitiv",
        }])
        assert res.quarantined == 1
        # missing_required_field fires first since value_unit is in required list
        assert (
            "missing_required_field" in res.quarantine_reasons
            or "ambiguous_unit" in res.quarantine_reasons
        )

    def test_revenue_millions_normalized_to_raw(self, session):
        res = ingest_consensus(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "metric": "revenue",
            "estimate_type": "consensus",
            "value": 95000,           # source reports millions
            "value_unit": "usd_millions",
            "as_of_date": "2026-04-10", "source": "refinitiv",
        }])
        assert res.inserted == 1
        row = session.execute(select(ConsensusEstimateRow)).scalar_one()
        assert float(row.value) == 95_000_000_000.0     # normalized to raw
        assert row.value_unit == "usd_raw"
        assert float(row.original_value) == 95000.0
        assert row.original_unit == "usd_millions"

    def test_revenue_raw_passthrough(self, session):
        res = ingest_consensus(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "metric": "revenue",
            "estimate_type": "consensus",
            "value": 95_000_000_000,
            "value_unit": "usd_raw",
            "as_of_date": "2026-04-10", "source": "refinitiv",
        }])
        assert res.inserted == 1
        row = session.execute(select(ConsensusEstimateRow)).scalar_one()
        assert float(row.value) == 95_000_000_000.0
        assert row.value_unit == "usd_raw"
        assert row.original_unit == "usd_raw"

    def test_eps_must_be_per_share(self, session):
        res = ingest_consensus(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "metric": "eps",
            "estimate_type": "consensus",
            "value": 1.50, "value_unit": "usd_millions",  # WRONG unit
            "as_of_date": "2026-04-10", "source": "refinitiv",
        }])
        assert res.quarantined == 1
        assert "unit_metric_mismatch" in res.quarantine_reasons

    def test_bad_unit_string_rejected(self, session):
        res = ingest_consensus(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "metric": "revenue",
            "estimate_type": "consensus",
            "value": 95e9, "value_unit": "usd_gajillion",
            "as_of_date": "2026-04-10", "source": "refinitiv",
        }])
        assert res.quarantined == 1
        assert "ambiguous_unit" in res.quarantine_reasons

    def test_actual_path_also_normalizes(self, session):
        res = ingest_consensus(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "metric": "revenue",
            "estimate_type": "actual",
            "value": 93_000, "value_unit": "usd_millions",
            "as_of_date": "2026-04-21", "source": "company",
        }])
        assert res.inserted == 1
        row = session.execute(select(ConsensusEstimateRow)).scalar_one()
        assert float(row.value) == 93_000_000_000.0
        assert row.estimate_type == "actual"


class TestUnitUtil:
    def test_parse_unit_accepts_enum_and_string(self):
        assert parse_unit("usd_raw") == ValueUnit.USD_RAW
        assert parse_unit(ValueUnit.USD_RAW) == ValueUnit.USD_RAW

    def test_parse_unit_missing(self):
        with pytest.raises(UnitError):
            parse_unit(None)
        with pytest.raises(UnitError):
            parse_unit("")

    def test_canonical_unit_for(self):
        assert canonical_unit_for("eps") == ValueUnit.USD_PER_SHARE
        assert canonical_unit_for("revenue") == ValueUnit.USD_RAW

    def test_normalize_billions(self):
        v, u = normalize_to_canonical("revenue", 95.0, ValueUnit.USD_BILLIONS)
        assert v == 95_000_000_000.0
        assert u == ValueUnit.USD_RAW

    def test_normalize_thousands(self):
        v, u = normalize_to_canonical("revenue", 95_000_000.0, ValueUnit.USD_THOUSANDS)
        assert v == 95_000_000_000.0

    def test_mismatch_raises(self):
        with pytest.raises(UnitError):
            normalize_to_canonical("eps", 1.5, ValueUnit.USD_RAW)


# ---------------------------------------------------------------------------
# Content hash — deterministic + dedupe behavior
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_canonical_hash_deterministic(self):
        a = canonical_hash(["zacks", "AAPL", dt.date(2026, 4, 21), 1.5])
        b = canonical_hash(["zacks", "AAPL", dt.date(2026, 4, 21), 1.5])
        assert a == b
        assert len(a) == 40   # SHA-1 hex

    def test_earnings_hash_different_on_symbol(self):
        h1 = earnings_content_hash(
            source="z", symbol="AAPL", event_date=dt.date(2026, 4, 21),
            event_time="after_close", fiscal_period=None,
            announcement_timestamp_utc=None,
        )
        h2 = earnings_content_hash(
            source="z", symbol="MSFT", event_date=dt.date(2026, 4, 21),
            event_time="after_close", fiscal_period=None,
            announcement_timestamp_utc=None,
        )
        assert h1 != h2

    def test_consensus_hash_different_on_value(self):
        h1 = consensus_content_hash(
            source="r", symbol="AAPL", event_date=dt.date(2026, 4, 21),
            metric="eps", estimate_type="consensus",
            as_of_date=dt.date(2026, 4, 10),
            normalized_value=1.45, value_unit="usd_per_share",
        )
        h2 = consensus_content_hash(
            source="r", symbol="AAPL", event_date=dt.date(2026, 4, 21),
            metric="eps", estimate_type="consensus",
            as_of_date=dt.date(2026, 4, 10),
            normalized_value=1.50, value_unit="usd_per_share",
        )
        assert h1 != h2

    def test_shares_hash_stable_across_runs(self):
        h = shares_content_hash(
            source="edgar", symbol="AAPL",
            effective_date=dt.date(2025, 12, 31),
            filing_date=dt.date(2026, 2, 1),
            shares_outstanding=16_000_000_000,
        )
        assert isinstance(h, str) and len(h) == 40


class TestContentHashDedupeEnforced:
    def test_duplicate_null_external_id_deduped_by_content_hash(self, session):
        """Same source + null external_id + same semantic content -> UNIQUE
        constraint on (source, content_hash) blocks the second insert."""
        rec = {
            "asset_id": "aapl", "symbol": "AAPL",
            "effective_date": "2025-12-31", "filing_date": "2026-02-01",
            "shares_outstanding": 16_000_000_000,
            "source": "edgar",
            # external_id deliberately omitted
        }
        r1 = ingest_shares(session, [rec])
        assert r1.inserted == 1
        # Second ingest of identical rec -> second raw insert should fail
        # unique (source, content_hash), rolled back to quarantine-style.
        # Our ingestion pipeline does not catch the IntegrityError here
        # because raw inserts flush immediately; we test the CONSTRAINT's
        # existence by inserting directly.
        from sqlalchemy.exc import IntegrityError
        first_raw = session.execute(select(RawSharesIngestion)).scalar_one()
        dup = RawSharesIngestion(
            source=first_raw.source,
            external_id=None,
            content_hash=first_raw.content_hash,
            payload=dict(first_raw.payload),
            status="pending",
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    def test_revisions_with_different_value_distinct(self, session):
        """Same key fields but different value → different content_hash →
        NOT deduped (correct; revisions should be preserved)."""
        r1 = ingest_consensus(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "metric": "eps",
            "estimate_type": "consensus",
            "value": 1.45, "value_unit": "usd_per_share",
            "as_of_date": "2026-04-01", "source": "refinitiv",
        }])
        r2 = ingest_consensus(session, [{
            "asset_id": "aapl", "symbol": "AAPL",
            "event_date": "2026-04-21", "metric": "eps",
            "estimate_type": "consensus",
            "value": 1.50, "value_unit": "usd_per_share",
            "as_of_date": "2026-04-10", "source": "refinitiv",
        }])
        assert r1.inserted == 1 and r2.inserted == 1
        n = session.execute(select(func.count(ConsensusEstimateRow.id))).scalar_one()
        assert n == 2


# ---------------------------------------------------------------------------
# Expanded validation counters
# ---------------------------------------------------------------------------


class TestExpandedValidation:
    def test_naive_quarantine_surfaced_in_report(self, session):
        ingest_earnings(session, [{
            "asset_id": "x", "symbol": "X",
            "event_date": "2026-04-21", "event_time": "after_close",
            "announcement_timestamp": "2026-04-21T16:30:00",   # naive
            "source": "feed",
        }])
        r = run_validation(session)
        assert r.events_naive_timestamp_rejected == 1

    def test_ambiguous_unit_surfaced(self, session):
        ingest_consensus(session, [{
            "asset_id": "x", "symbol": "X",
            "event_date": "2026-04-21", "metric": "revenue",
            "estimate_type": "consensus",
            "value": 1.0, "value_unit": "bogus",
            "as_of_date": "2026-04-10", "source": "feed",
        }])
        r = run_validation(session)
        assert r.events_ambiguous_unit_rejected == 1

    def test_consensus_no_actual_counted(self, session):
        # Event + consensus only, no actual
        ingest_earnings(session, [{
            "asset_id": "a", "symbol": "A",
            "event_date": "2026-04-21", "event_time": "after_close",
            "source": "zacks",
        }])
        ingest_consensus(session, [{
            "asset_id": "a", "symbol": "A",
            "event_date": "2026-04-21", "metric": "eps",
            "estimate_type": "consensus",
            "value": 1.50, "value_unit": "usd_per_share",
            "as_of_date": "2026-04-10", "source": "refinitiv",
        }])
        r = run_validation(session)
        assert r.events_with_consensus_no_actual == 1

    def test_actual_no_consensus_counted(self, session):
        ingest_earnings(session, [{
            "asset_id": "a", "symbol": "A",
            "event_date": "2026-04-21", "event_time": "after_close",
            "source": "zacks",
        }])
        ingest_consensus(session, [{
            "asset_id": "a", "symbol": "A",
            "event_date": "2026-04-21", "metric": "eps",
            "estimate_type": "actual",
            "value": 1.62, "value_unit": "usd_per_share",
            "as_of_date": "2026-04-21", "source": "company",
        }])
        r = run_validation(session)
        assert r.events_with_actual_no_consensus == 1

    def test_missing_shares_counted(self, session):
        ingest_earnings(session, [{
            "asset_id": "a", "symbol": "A",
            "event_date": "2026-04-21", "event_time": "after_close",
            "source": "zacks",
        }])
        r = run_validation(session)
        assert r.events_missing_shares == 1

    def test_impossible_timing_before_open_with_late_ts(self, session):
        """Before-open announcement with UTC timestamp > 15:00 is
        inconsistent (that's post US market open)."""
        ingest_earnings(
            session,
            [{
                "asset_id": "a", "symbol": "A",
                "event_date": "2026-04-21", "event_time": "before_open",
                # 18:00 UTC = 14:00 ET = after US open
                "announcement_timestamp": "2026-04-21T18:00:00Z",
                "source": "feed",
            }],
        )
        r = run_validation(session)
        assert r.events_impossible_timing == 1


# ---------------------------------------------------------------------------
# Regression: Phase 9/10 PIT semantics preserved
# ---------------------------------------------------------------------------


class TestPhase9RegressionStillGreen:
    """Prove Phase 9/10 strict semantics were not weakened by 10.6."""

    def test_strict_less_than_consensus_still_holds(self, session):
        # Three consensus revisions; lookup with as_of=event_date should
        # NOT include the event-day revision (strict <).
        recs = [
            {"asset_id": "a", "symbol": "A",
             "event_date": "2026-04-21", "metric": "eps",
             "estimate_type": "consensus",
             "value": 1.45, "value_unit": "usd_per_share",
             "as_of_date": "2026-04-01", "source": "r"},
            {"asset_id": "a", "symbol": "A",
             "event_date": "2026-04-21", "metric": "eps",
             "estimate_type": "consensus",
             "value": 1.50, "value_unit": "usd_per_share",
             "as_of_date": "2026-04-10", "source": "r"},
            # Same-day revision — should NOT be chosen
            {"asset_id": "a", "symbol": "A",
             "event_date": "2026-04-21", "metric": "eps",
             "estimate_type": "consensus",
             "value": 1.70, "value_unit": "usd_per_share",
             "as_of_date": "2026-04-21", "source": "r2"},
        ]
        ingest_consensus(session, recs)
        from apps.api.src.domain.data.consensus.models import Metric
        from apps.api.src.domain.data.consensus.sql_repo import SqlConsensusRepo
        repo = SqlConsensusRepo(session)
        got = repo.get_consensus(
            "A", dt.date(2026, 4, 21), Metric.EPS, dt.date(2026, 4, 21),
        )
        assert got.value == 1.50   # NOT 1.70, NOT 1.45
