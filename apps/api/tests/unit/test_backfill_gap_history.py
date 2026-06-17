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


# --- shared fake ingest_symbols (postgres pg_insert can't run on sqlite) ----


class _SR:
    """Stand-in for SymbolRunReport."""
    def __init__(self, symbol: str, bars_written: int = 0, bars_updated: int = 0):
        self.symbol = symbol
        self.bars_written = bars_written
        self.bars_updated = bars_updated


class _Report:
    def __init__(self, srs: list[_SR]):
        self.symbols = srs

    @property
    def total_written(self) -> int:
        return sum(s.bars_written + s.bars_updated for s in self.symbols)


def _fake_ingest_factory(bars_by_symbol, *, seen=None, calls=None, benchmark_rows=0):
    async def _fake(sess, batch, *, providers, start_date, incremental,
                    include_benchmark=True):
        if seen is not None:
            seen.append(list(batch))
        if calls is not None:
            calls.append(include_benchmark)
        srs = [_SR(s, bars_written=bars_by_symbol.get(s, 0)) for s in batch]
        if include_benchmark and benchmark_rows:
            srs.append(_SR("SPY", bars_written=benchmark_rows))
        return _Report(srs)
    return _fake


def test_resume_live_writes_checkpoint_then_skips(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(3):
        _add_asset(session, f"gap{i}")   # 3 zero-history gaps
    session.commit()

    seen: list[list[str]] = []
    monkeypatch.setattr(bgh, "ingest_symbols", _fake_ingest_factory(
        {"GAP0": 5, "GAP1": 5, "GAP2": 5}, seen=seen))

    ckpt = tmp_path / "ckpt.json"
    s1 = asyncio.run(
        bgh.backfill_gap_history(
            dry_run=False, batch_size=2, checkpoint_path=ckpt,
            session_factory=lambda: session, providers=[object()],
        )
    )
    assert s1.batches == 2
    assert sorted(s1.completed_with_data) == ["GAP0", "GAP1", "GAP2"]
    assert s1.bars_written == 15          # 3 symbols * 5
    assert s1.bars_written_by_symbol == {"GAP0": 5, "GAP1": 5, "GAP2": 5}
    saved = json.loads(ckpt.read_text(encoding="utf-8"))
    assert sorted(saved["completed"]) == ["GAP0", "GAP1", "GAP2"]
    assert saved["no_data"] == []
    assert saved["floor"] == bgh.HISTORY_FLOOR.isoformat()

    # Second run resumes: everything already in checkpoint → nothing re-ingested
    seen.clear()
    s2 = asyncio.run(
        bgh.backfill_gap_history(
            dry_run=False, batch_size=2, checkpoint_path=ckpt,
            session_factory=lambda: session, providers=[object()],
        )
    )
    assert s2.processed == []
    assert sorted(s2.skipped_resume) == ["GAP0", "GAP1", "GAP2"]
    assert seen == []                     # idempotent: no re-fetch


# ---------------------------------------------------------------------------
# 6. BP29C — no-data visibility, benchmark control, no-data resume
# ---------------------------------------------------------------------------


def test_no_data_symbol_recorded_distinctly(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add_asset(session, "withdata")
    _add_asset(session, "nodata")
    session.commit()
    monkeypatch.setattr(bgh, "ingest_symbols", _fake_ingest_factory(
        {"WITHDATA": 800}))   # NODATA absent -> 0 bars

    ckpt = tmp_path / "ckpt.json"
    s = asyncio.run(bgh.backfill_gap_history(
        dry_run=False, batch_size=25, checkpoint_path=ckpt,
        session_factory=lambda: session, providers=[object()]))

    assert s.completed_with_data == ["WITHDATA"]
    assert s.completed_no_data == ["NODATA"]
    assert s.failures == {}                       # no-data is NOT a failure
    assert s.bars_written_by_symbol == {"WITHDATA": 800, "NODATA": 0}
    saved = json.loads(ckpt.read_text(encoding="utf-8"))
    assert saved["completed"] == ["WITHDATA"]
    assert saved["no_data"] == ["NODATA"]


def test_batch_failure_separate_from_no_data(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add_asset(session, "boom")
    session.commit()

    async def _raise(sess, batch, *, providers, start_date, incremental,
                     include_benchmark=True):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(bgh, "ingest_symbols", _raise)
    s = asyncio.run(bgh.backfill_gap_history(
        dry_run=False, checkpoint_path=tmp_path / "c.json",
        session_factory=lambda: session, providers=[object()]))

    assert "BOOM" in s.failures                    # batch exception -> failure
    assert s.completed_no_data == []               # NOT conflated with no-data
    assert s.completed_with_data == []


def test_benchmark_disabled_by_default_else_reported(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add_asset(session, "aaa")
    session.commit()

    # default: include_benchmark must be False (no SPY)
    calls: list[bool] = []
    monkeypatch.setattr(bgh, "ingest_symbols", _fake_ingest_factory(
        {"AAA": 500}, calls=calls, benchmark_rows=83))
    s = asyncio.run(bgh.backfill_gap_history(
        dry_run=False, checkpoint_path=tmp_path / "c1.json",
        session_factory=lambda: session, providers=[object()]))
    assert calls == [False]                        # driver disabled benchmark
    assert s.benchmark == [] and s.benchmark_rows == 0
    assert s.bars_written == 500

    # opt-in: SPY reported under its own bucket, not in gap totals
    calls2: list[bool] = []
    monkeypatch.setattr(bgh, "ingest_symbols", _fake_ingest_factory(
        {"AAA": 500}, calls=calls2, benchmark_rows=83))
    s2 = asyncio.run(bgh.backfill_gap_history(
        dry_run=False, include_benchmark=True, checkpoint_path=tmp_path / "c2.json",
        session_factory=lambda: session, providers=[object()]))
    assert calls2 == [True]
    assert s2.benchmark == ["SPY"] and s2.benchmark_rows == 83
    assert "SPY" not in s2.bars_written_by_symbol
    assert "SPY" not in s2.completed_with_data
    assert s2.bars_written == 500                  # gap-only total excludes SPY


def test_rerun_skips_no_data_unless_retry(session: Session, tmp_path: Path) -> None:
    _add_asset(session, "brkb")        # zero-history gap
    session.commit()
    ckpt = tmp_path / "ckpt.json"
    ckpt.write_text(json.dumps({"completed": [], "no_data": ["BRKB"]}), encoding="utf-8")

    # default: no_data skipped on rerun
    s = asyncio.run(bgh.backfill_gap_history(
        dry_run=True, checkpoint_path=ckpt, session_factory=lambda: session))
    assert s.skipped_resume == ["BRKB"]

    # retry_no_data=True: BRKB is reprocessed
    s2 = asyncio.run(bgh.backfill_gap_history(
        dry_run=True, retry_no_data=True, checkpoint_path=ckpt,
        session_factory=lambda: session))
    assert s2.skipped_resume == []
    assert {g.symbol for g in s2.gap_symbols} == {"BRKB"}


# ---------------------------------------------------------------------------
# 5. only_symbols pilot scope (BP29A)
# ---------------------------------------------------------------------------


def _seed_two_cohorts(s: Session) -> None:
    """LATE (2025 gap) + EMPTY (no-bars gap) + DEEP (2022-05-02 complete)."""
    late = _add_asset(s, "late")
    _add_bar(s, late.id, dt.date(2025, 5, 5))
    _add_asset(s, "empty")
    deep = _add_asset(s, "deep")
    _add_bar(s, deep.id, dt.date(2022, 5, 2))
    s.commit()


def test_only_symbols_limits_dry_run_scope(session: Session) -> None:
    _seed_two_cohorts(session)
    summary = asyncio.run(
        bgh.backfill_gap_history(
            dry_run=True, only_symbols={"LATE"}, session_factory=lambda: session
        )
    )
    assert {g.symbol for g in summary.gap_symbols} == {"LATE"}   # EMPTY excluded
    assert summary.only_symbols == {"LATE"}


def test_only_symbols_normalization(session: Session) -> None:
    _seed_two_cohorts(session)
    summary = asyncio.run(
        bgh.backfill_gap_history(
            dry_run=True,
            only_symbols={" late ", "Empty"},   # whitespace + mixed case
            session_factory=lambda: session,
        )
    )
    assert summary.only_symbols == {"LATE", "EMPTY"}
    assert {g.symbol for g in summary.gap_symbols} == {"LATE", "EMPTY"}


def test_only_symbols_ignores_non_gap_symbols(session: Session) -> None:
    _seed_two_cohorts(session)
    summary = asyncio.run(
        bgh.backfill_gap_history(
            dry_run=True,
            only_symbols={"DEEP", "ZZZZ"},   # DEEP complete, ZZZZ unknown
            session_factory=lambda: session,
        )
    )
    assert summary.gap_symbols == []        # neither is in the gap set


def test_only_symbols_with_resume(session: Session, tmp_path: Path) -> None:
    _seed_two_cohorts(session)
    ckpt = tmp_path / "ckpt.json"
    ckpt.write_text(json.dumps({"completed": ["LATE"]}), encoding="utf-8")

    summary = asyncio.run(
        bgh.backfill_gap_history(
            dry_run=True,
            only_symbols={"LATE", "EMPTY"},
            checkpoint_path=ckpt,
            session_factory=lambda: session,
        )
    )
    # scope keeps both gaps; resume drops LATE; EMPTY remains to process
    assert {g.symbol for g in summary.gap_symbols} == {"LATE", "EMPTY"}
    assert summary.skipped_resume == ["LATE"]
    to_process = [g.symbol for g in summary.gap_symbols
                  if g.symbol not in summary.skipped_resume]
    assert to_process == ["EMPTY"]
