"""Phase 11C integration test — chain_ingest end-to-end against Postgres.

Verifies:
  * Mock-substituted ThetaDataAdapter → ingest_chain_snapshot → options_chain_snapshot
  * INSERT-only behavior (re-ingest is a no-op via ON CONFLICT DO NOTHING)
  * Liquidity-filter rejections never reach the table
  * provider_unavailable / provider_error paths produce summary, no INSERTs
  * partial-chain path produces summary status='partial' and still inserts accepted rows
  * Universe ingest writes per-underlying rows; one bad symbol does not stop the others
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.options_models import OptionsChainSnapshot  # noqa: F401 — register on Base
from apps.api.src.options.data import chain_ingest as ci
from apps.api.src.options.data_provider.base_adapter import (
    PartialChainWarning,
    ProviderError,
    ProviderUnavailable,
)
from apps.api.src.options.data_provider.thetadata_adapter import ThetaDataAdapter


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Mock adapter — substitutes _raw_chain_pull for deterministic test data
# ---------------------------------------------------------------------------

class _MockTheta(ThetaDataAdapter):
    def __init__(self, raw, raise_exc=None):
        super().__init__()
        self._raw = raw
        self._exc = raise_exc

    def _raw_chain_pull(self, *, symbol, timestamp):
        if self._exc is not None:
            raise self._exc
        return self._raw

    def _raw_health_check(self):
        return None


def _row(
    *,
    expiry: str = "2026-06-18",
    strike: float = 440.0,
    option_type: str = "P",
    option_symbol: str | None = None,
    bid: float = 1.50,
    ask: float = 1.55,
    open_interest: int = 1000,
    quote_age_seconds: int = 2,
) -> dict:
    return {
        "expiry": expiry,
        "strike": strike,
        "option_type": option_type,
        "option_symbol": option_symbol or f"SPY260618{option_type}{int(strike*1000):08d}",
        "bid": bid, "ask": ask, "mid": (bid + ask) / 2, "last": bid,
        "volume": 100, "open_interest": open_interest,
        "delta": -0.20, "gamma": 0.02, "theta": -0.05, "vega": 0.10, "iv": 0.18,
        "quote_age_seconds": quote_age_seconds,
    }


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)


# ===========================================================================
# Happy path — INSERTs land in options_chain_snapshot
# ===========================================================================

def test_ingest_inserts_accepted_quotes(pg_session, session_factory):
    raw = {
        "rows": [
            _row(strike=440, option_type="P", bid=1.50, ask=1.55),
            _row(strike=445, option_type="P", bid=2.10, ask=2.15),
            _row(strike=460, option_type="C", bid=1.40, ask=1.45),
        ],
        "underlying_price": 450.0,
        "interest_rate": 0.05,
        "dividend_yield": 0.015,
        "partial": False,
    }
    summary = ci.ingest_chain_snapshot(
        underlying="SPY",
        snapshot_at_utc=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
        adapter=_MockTheta(raw),
        session_factory=session_factory,
    )
    assert summary.status == "ok"
    assert summary.n_provider_quotes == 3
    assert summary.n_filtered == 3
    assert summary.n_inserted == 3
    assert summary.n_skipped_existing == 0

    rows = pg_session.execute(text(
        "SELECT underlying, strike, option_type, bid, ask, provider "
        "FROM options_chain_snapshot ORDER BY strike, option_type"
    )).all()
    assert len(rows) == 3
    assert {r.underlying for r in rows} == {"SPY"}
    assert {r.provider for r in rows} == {"thetadata"}


def test_reingest_is_idempotent_no_duplicates(pg_session, session_factory):
    raw = {"rows": [_row()], "underlying_price": 450.0, "partial": False}
    snap_at = dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc)
    s1 = ci.ingest_chain_snapshot(
        underlying="SPY", snapshot_at_utc=snap_at,
        adapter=_MockTheta(raw), session_factory=session_factory,
    )
    s2 = ci.ingest_chain_snapshot(
        underlying="SPY", snapshot_at_utc=snap_at,
        adapter=_MockTheta(raw), session_factory=session_factory,
    )
    assert s1.n_inserted == 1 and s2.n_inserted == 0
    assert s2.n_skipped_existing == 1
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_chain_snapshot"
    )).scalar_one()
    assert n == 1


# ===========================================================================
# Filter rejections — never reach the table
# ===========================================================================

def test_filtered_rows_not_inserted(pg_session, session_factory):
    raw = {
        "rows": [
            _row(strike=440, bid=1.50, ask=1.55),                      # ok
            _row(strike=441, open_interest=10),                          # LOW_OI
            _row(strike=442, bid=1.50, ask=2.00),                        # WIDE_SPREAD
            _row(strike=443, quote_age_seconds=300),                     # STALE
        ],
        "underlying_price": 450.0, "partial": False,
    }
    summary = ci.ingest_chain_snapshot(
        underlying="SPY",
        snapshot_at_utc=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
        adapter=_MockTheta(raw),
        session_factory=session_factory,
    )
    assert summary.n_provider_quotes == 4
    assert summary.n_filtered == 1
    assert summary.n_inserted == 1
    assert summary.reject_counts.get("LOW_OPEN_INTEREST") == 1
    assert summary.reject_counts.get("WIDE_SPREAD") == 1
    assert summary.reject_counts.get("STALE_QUOTE") == 1
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_chain_snapshot"
    )).scalar_one()
    assert n == 1


# ===========================================================================
# Error paths — no INSERTs on provider failure
# ===========================================================================

def test_provider_unavailable_skips_no_inserts(pg_session, session_factory):
    summary = ci.ingest_chain_snapshot(
        underlying="SPY",
        snapshot_at_utc=dt.datetime(2026, 5, 18, tzinfo=dt.timezone.utc),
        adapter=_MockTheta({"rows": []},
                           raise_exc=ProviderUnavailable("net down")),
        session_factory=session_factory,
    )
    assert summary.status == "skipped_unavailable"
    assert summary.n_inserted == 0
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_chain_snapshot"
    )).scalar_one()
    assert n == 0


def test_provider_error_records_status_no_inserts(pg_session, session_factory):
    summary = ci.ingest_chain_snapshot(
        underlying="SPY",
        snapshot_at_utc=dt.datetime(2026, 5, 18, tzinfo=dt.timezone.utc),
        adapter=_MockTheta({"rows": []},
                           raise_exc=ProviderError("garbled")),
        session_factory=session_factory,
    )
    assert summary.status == "error"
    assert summary.n_inserted == 0
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_chain_snapshot"
    )).scalar_one()
    assert n == 0


# ===========================================================================
# Partial-chain — proceeds with what it has
# ===========================================================================

def test_partial_chain_inserts_accepted_and_marks_partial(
    pg_session, session_factory,
):
    """Adapter raises PartialChainWarning carrying the partial result;
    ingest must use it (no re-pull) and mark status='partial'."""
    raw = {
        "rows": [_row()],
        "underlying_price": 450.0,
        "partial": True,
        "partial_reason": "expiries 2026-09-18 unavailable",
    }
    summary = ci.ingest_chain_snapshot(
        underlying="SPY",
        snapshot_at_utc=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
        adapter=_MockTheta(raw),
        session_factory=session_factory,
    )
    assert summary.status == "partial"
    assert summary.n_inserted == 1
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_chain_snapshot"
    )).scalar_one()
    assert n == 1


# ===========================================================================
# Universe ingest — one bad symbol does not stop the others
# ===========================================================================

def test_universe_ingest_isolates_per_symbol_failure(
    pg_session, session_factory,
):
    """Build per-symbol adapters via a dispatcher: GLD raises, others succeed."""

    good_raw = {"rows": [_row()], "underlying_price": 450.0, "partial": False}

    class _Dispatcher(_MockTheta):
        def __init__(self):
            super().__init__(good_raw)

        def _raw_chain_pull(self, *, symbol, timestamp):
            if symbol == "GLD":
                raise ProviderUnavailable("vendor down for GLD")
            return good_raw

    summaries = ci.ingest_universe(
        universe=("SPY", "QQQ", "GLD", "TLT"),
        snapshot_at_utc=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
        adapter=_Dispatcher(),
        session_factory=session_factory,
    )
    by_sym = {s.underlying: s for s in summaries}
    assert by_sym["SPY"].status == "ok" and by_sym["SPY"].n_inserted == 1
    assert by_sym["QQQ"].status == "ok" and by_sym["QQQ"].n_inserted == 1
    assert by_sym["GLD"].status == "skipped_unavailable"
    assert by_sym["TLT"].status == "ok" and by_sym["TLT"].n_inserted == 1
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_chain_snapshot"
    )).scalar_one()
    assert n == 3


# ===========================================================================
# Numeric column round-trip — verifies Decimal precision survives
# ===========================================================================

def test_numeric_columns_round_trip(pg_session, session_factory):
    raw = {
        "rows": [_row(strike=440.5, bid=1.50, ask=1.55)],
        "underlying_price": 450.25,
        "partial": False,
    }
    ci.ingest_chain_snapshot(
        underlying="SPY",
        snapshot_at_utc=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
        adapter=_MockTheta(raw),
        session_factory=session_factory,
    )
    row = pg_session.execute(text(
        "SELECT strike, bid, ask, mid FROM options_chain_snapshot"
    )).one()
    assert row.strike == Decimal("440.5000")
    assert row.bid == Decimal("1.5000")
    assert row.ask == Decimal("1.5500")
