"""BP28 — gap-backfill driver unit tests (sqlite in-memory).

Covers: universe enumeration, gap detection (incl. first-trading-day tolerance
and zero-history symbols), dry-run safety, and resume/idempotent behaviour.

The live ingest path uses ``pg_insert`` (postgres-only), so the resume test
monkeypatches ``ingest_symbols`` to exercise the driver's batch/checkpoint loop
without a real DB write.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.src.db import Base, models  # noqa: F401  (register ORM models)
from apps.api.src.db.models import Asset, PriceBar
from apps.worker.src.jobs import backfill_gap_history as bgh

UTC = dt.timezone.utc


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    # Create only the tables under test. Full Base.metadata.create_all() fails on
    # sqlite (an unrelated model uses a postgres ARRAY column with no sqlite
    # variant); asset + price_bar are plain types and create cleanly.
    Base.metadata.create_all(
        engine, tables=[Asset.__table__, PriceBar.__table__]
    )
    s = Session(bind=engine, autoflush=False, future=True)
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _add_asset(
    s: Session, symbol: str, *, asset_class: str = "equity", active: bool = True
) -> Asset:
    a = Asset(
        symbol=symbol,
        asset_class=asset_class,
        exchange="NASDAQ",
        currency="USD",
        is_active=active,
    )
    s.add(a)
    s.flush()
    return a


def _add_bar(s: Session, asset_id: str, day: dt.date, provider: str = "test") -> None:
    s.add(
        PriceBar(
            asset_id=asset_id,
            timeframe="1d",
            ts=dt.datetime(day.year, day.month, day.day, tzinfo=UTC),
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10.5"),
            adjusted_close=Decimal("10.5"),
            volume=1000,
            provider=provider,
        )
    )
    s.flush()


# ---------------------------------------------------------------------------
# 1. universe enumeration
# ---------------------------------------------------------------------------


def test_enumerate_universe_active_equity_only(session: Session) -> None:
    _add_asset(session, "msft")
    _add_asset(session, "aapl")
    _add_asset(session, "deadco", active=False)        # inactive → excluded
    _add_asset(session, "spy", asset_class="etf")      # non-equity → excluded
    _add_asset(session, "btc", asset_class="crypto")   # non-equity → excluded
    session.commit()

    assert bgh.enumerate_universe(session) == ["AAPL", "MSFT"]


# ---------------------------------------------------------------------------
# 2. gap detection
# ---------------------------------------------------------------------------


def test_detect_gap_symbols(session: Session) -> None:
    """Mirrors the real dev-DB two-cohort split (BP28A)."""
    deep = _add_asset(session, "deep")
    _add_bar(session, deep.id, dt.date(2022, 5, 2))     # deep cohort → complete

    late = _add_asset(session, "late")
    _add_bar(session, late.id, dt.date(2025, 5, 5))     # shallow cohort → GAP

    _add_asset(session, "empty")                        # no bars at all → GAP
    session.commit()

    gaps = bgh.detect_gap_symbols(session)              # default cutoff 2024-01-01
    syms = {g.symbol for g in gaps}
    assert syms == {"LATE", "EMPTY"}

    by = {g.symbol: g.earliest for g in gaps}
    assert by["EMPTY"] is None
    assert by["LATE"] == dt.date(2025, 5, 5)


def test_cutoff_boundary(session: Session) -> None:
    """earliest == cutoff is complete; earliest one day later is a gap."""
    on = _add_asset(session, "oncut")
    _add_bar(session, on.id, dt.date(2024, 1, 1))       # == cutoff → complete

    after = _add_asset(session, "after")
    _add_bar(session, after.id, dt.date(2024, 1, 2))    # > cutoff → GAP
    session.commit()

    gaps = bgh.detect_gap_symbols(session, deep_cohort_cutoff=dt.date(2024, 1, 1))
    assert {g.symbol for g in gaps} == {"AFTER"}


def test_dotted_ticker_hints_present() -> None:
    """BP28B flag — dotted tickers documented, not yet remapped."""
    assert bgh.DOTTED_TICKER_HINTS == {
        "BRKB": "BRK.B",
        "HEIA": "HEI.A",
        "MOGA": "MOG.A",
        "UHALB": "UHAL.B",
    }


# ---------------------------------------------------------------------------
# 3. dry run
# ---------------------------------------------------------------------------


def test_dry_run_detects_but_never_writes(session: Session, tmp_path: Path) -> None:
    late = _add_asset(session, "late")
    _add_bar(session, late.id, dt.date(2025, 6, 2))
    _add_asset(session, "empty")
    session.commit()

    ckpt = tmp_path / "ckpt.json"

    summary = asyncio.run(
        bgh.backfill_gap_history(
            dry_run=True,
            batch_size=10,
            checkpoint_path=ckpt,
            session_factory=lambda: session,
            providers=[],
        )
    )

    assert summary.dry_run is True
    assert {g.symbol for g in summary.gap_symbols} == {"LATE", "EMPTY"}
    assert summary.processed == []
    assert summary.bars_written == 0
    assert not ckpt.exists()         # dry-run writes no checkpoint


# ---------------------------------------------------------------------------
# 4. resume / idempotent behaviour
# ---------------------------------------------------------------------------


def test_resume_filters_completed_in_dry_run(session: Session, tmp_path: Path) -> None:
    late = _add_asset(session, "late")
    _add_bar(session, late.id, dt.date(2025, 6, 2))
    _add_asset(session, "empty")
    session.commit()

    ckpt = tmp_path / "ckpt.json"
    ckpt.write_text(json.dumps({"completed": ["LATE"]}), encoding="utf-8")

    summary = asyncio.run(
        bgh.backfill_gap_history(
            dry_run=True, checkpoint_path=ckpt, session_factory=lambda: session
        )
    )
    assert summary.skipped_resume == ["LATE"]
    # EMPTY still needs processing; LATE skipped via resume
    assert {g.symbol for g in summary.gap_symbols} == {"LATE", "EMPTY"}


def test_resume_live_writes_checkpoint_then_skips(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(3):
        _add_asset(session, f"gap{i}")   # 3 zero-history gaps
    session.commit()

    seen: list[list[str]] = []

    class _Report:
        total_written = 5

    async def _fake_ingest(sess, batch, *, providers, start_date, incremental):
        seen.append(list(batch))
        assert start_date == bgh.HISTORY_FLOOR
        assert incremental is False
        return _Report()

    monkeypatch.setattr(bgh, "ingest_symbols", _fake_ingest)

    ckpt = tmp_path / "ckpt.json"
    s1 = asyncio.run(
        bgh.backfill_gap_history(
            dry_run=False,
            batch_size=2,
            checkpoint_path=ckpt,
            session_factory=lambda: session,
            providers=[object()],   # bypass real chain construction
        )
    )

    # 3 gaps, batch_size 2 → 2 batches; all processed
    assert s1.batches == 2
    assert sorted(s1.processed) == ["GAP0", "GAP1", "GAP2"]
    assert s1.bars_written == 10          # 2 batches * 5
    saved = json.loads(ckpt.read_text(encoding="utf-8"))
    assert sorted(saved["completed"]) == ["GAP0", "GAP1", "GAP2"]
    assert saved["floor"] == bgh.HISTORY_FLOOR.isoformat()

    # Second run resumes: everything already in checkpoint → nothing re-ingested
    seen.clear()
    s2 = asyncio.run(
        bgh.backfill_gap_history(
            dry_run=False,
            batch_size=2,
            checkpoint_path=ckpt,
            session_factory=lambda: session,
            providers=[object()],
        )
    )
    assert s2.processed == []
    assert sorted(s2.skipped_resume) == ["GAP0", "GAP1", "GAP2"]
    assert seen == []                     # idempotent: no re-fetch
