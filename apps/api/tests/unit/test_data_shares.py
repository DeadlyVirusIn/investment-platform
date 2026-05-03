"""Phase 9 — shares-outstanding PIT tests."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.data.shares.models import SharesOutstandingRecord
from apps.api.src.domain.data.shares.repo import InMemorySharesRepo


def _rec(
    effective: dt.date, filing: dt.date, shares: int,
    symbol: str = "AAPL", source: str = "edgar",
) -> SharesOutstandingRecord:
    return SharesOutstandingRecord(
        symbol=symbol, asset_id=symbol.lower(),
        effective_date=effective, filing_date=filing,
        shares_outstanding=shares, source=source,
    )


class TestModelInvariants:
    def test_negative_shares_rejected(self):
        with pytest.raises(ValueError):
            _rec(dt.date(2026, 3, 31), dt.date(2026, 5, 15), -1)

    def test_filing_before_effective_rejected(self):
        """Cannot file a measurement before it was measured."""
        with pytest.raises(ValueError):
            _rec(dt.date(2026, 5, 15), dt.date(2026, 3, 31), 1_000_000)


class TestPITLookup:
    def test_latest_filing_wins(self):
        repo = InMemorySharesRepo()
        repo.upsert(_rec(dt.date(2026, 3, 31), dt.date(2026, 5, 15), 100))
        repo.upsert(_rec(dt.date(2026, 6, 30), dt.date(2026, 8, 10), 95))
        got = repo.get_as_of("AAPL", dt.date(2026, 9, 1))
        assert got.shares_outstanding == 95
        assert got.filing_date == dt.date(2026, 8, 10)

    def test_no_future_leak_before_filing(self):
        """As_of before the filing date must NOT see the future measurement."""
        repo = InMemorySharesRepo()
        repo.upsert(_rec(dt.date(2026, 3, 31), dt.date(2026, 5, 15), 100))
        repo.upsert(_rec(dt.date(2026, 6, 30), dt.date(2026, 8, 10), 95))
        # As of July 1: the June-30 data exists but was not filed yet
        got = repo.get_as_of("AAPL", dt.date(2026, 7, 1))
        assert got.shares_outstanding == 100   # old value, still correct PIT
        assert got.filing_date == dt.date(2026, 5, 15)

    def test_no_record_returns_none(self):
        repo = InMemorySharesRepo()
        assert repo.get_as_of("AAPL", dt.date(2026, 4, 1)) is None

    def test_as_of_equals_filing_date_included(self):
        """filing_date <= as_of — boundary inclusive."""
        repo = InMemorySharesRepo()
        repo.upsert(_rec(dt.date(2026, 3, 31), dt.date(2026, 5, 15), 100))
        got = repo.get_as_of("AAPL", dt.date(2026, 5, 15))
        assert got is not None
        assert got.shares_outstanding == 100

    def test_as_of_one_day_before_filing_excluded(self):
        repo = InMemorySharesRepo()
        repo.upsert(_rec(dt.date(2026, 3, 31), dt.date(2026, 5, 15), 100))
        got = repo.get_as_of("AAPL", dt.date(2026, 5, 14))
        assert got is None

    def test_upsert_dedupes_by_effective_and_source(self):
        repo = InMemorySharesRepo()
        repo.upsert(_rec(dt.date(2026, 3, 31), dt.date(2026, 5, 15), 100, source="edgar"))
        # Re-upsert with corrected shares — should replace
        repo.upsert(_rec(dt.date(2026, 3, 31), dt.date(2026, 5, 20), 99, source="edgar"))
        history = repo.get_history("AAPL")
        assert len(history) == 1
        assert history[0].shares_outstanding == 99

    def test_multi_symbol_isolation(self):
        repo = InMemorySharesRepo()
        repo.upsert(_rec(dt.date(2026, 3, 31), dt.date(2026, 5, 15), 100, symbol="AAPL"))
        repo.upsert(_rec(dt.date(2026, 3, 31), dt.date(2026, 5, 15), 200, symbol="MSFT"))
        assert repo.get_as_of("AAPL", dt.date(2026, 6, 1)).shares_outstanding == 100
        assert repo.get_as_of("MSFT", dt.date(2026, 6, 1)).shares_outstanding == 200
