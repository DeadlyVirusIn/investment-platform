"""BP28 — universe gap-backfill driver.

Explicit, idempotent driver that widens the *deep-history* cross-section. Many
equity-universe symbols only have price history from ~2025 onward; durable
cross-sectional factor research needs them back to the 2022 floor. This driver:

  1. enumerates the active equity universe from the ``asset`` table,
  2. detects "gap" symbols whose earliest stored ``price_bar`` is materially
     later than the history floor (or that have no bars at all),
  3. backfills each gap symbol from ``start_date = 2022-01-01`` via
     ``ingest_symbols(..., incremental=False)`` over a Polygon(raw) → Tiingo →
     Yahoo provider chain.

Operational features: ``dry_run`` (default ON — preview only, no network/writes),
``batch_size``, per-batch progress logging, a JSON checkpoint for
resume/idempotent behaviour, and a structured summary report.

This module is BUILD-ONLY plumbing — it does not run on the scheduler and does
not touch strategy / replay / alpha code. ``ingest_symbols`` already upserts on
``uq_price_bar`` (per-provider rows; lower-priority providers never overwrite a
complete total-return bar), so repeated runs are safe.

NOTE — gap-detection cutoff (BP28B): the DB has a clean two-cohort split — 55
"deep" symbols starting 2022-05-02 (the complete baseline) and 941 "shallow"
symbols starting 2025-05-05. A symbol is a gap when it has no bars OR its
earliest bar is later than ``deep_cohort_cutoff`` (default 2024-01-01, which sits
cleanly between the two cohorts). This replaces the earlier ``tolerance_days``
heuristic, which assumed the only artifact was the Jan-1 weekend (deepest data
2022-01-03) and could not express the real 4-month cohort offset. The backfill
*start_date* remains exactly ``HISTORY_FLOOR`` (2022-01-01) so the shallow cohort
gets maximum history.

NOTE — dotted tickers (BP28B follow-up): four symbols are stored without their
class dot and have no bars because providers expect the dotted form — see
``DOTTED_TICKER_HINTS``. NOT remapped in this patch.

NOTE — benchmark (BP29C): the gap-backfill passes ``include_benchmark=False`` to
``ingest_symbols`` so a scoped run writes ONLY the requested gap symbols (no SPY
rows). Pass ``include_benchmark=True`` to re-enable; SPY rows are then counted in
their own ``benchmark`` bucket, never mixed into the gap-symbol totals.

NOTE — no-data symbols (BP29C): a gap symbol whose providers all return empty
(e.g. dotted tickers stored without the class dot) is recorded as
``completed_no_data`` (0 bars) — distinct from a batch ``failure`` (an exception).
No-data symbols are checkpointed separately so reruns skip them unless
``retry_no_data=True``.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset, PriceBar
from apps.api.src.domain.prices.providers.base import DailyPriceProvider
from apps.api.src.domain.prices.providers.polygon import PolygonProvider
from apps.api.src.domain.prices.providers.tiingo import TiingoProvider
from apps.api.src.domain.prices.providers.yahoo import YahooProvider
from apps.api.src.domain.prices.service import BENCHMARK_SYMBOLS, ingest_symbols

# --- defaults -------------------------------------------------------------
HISTORY_FLOOR = dt.date(2022, 1, 1)                 # backfill start_date (unchanged)
DEFAULT_DEEP_COHORT_CUTOFF = dt.date(2024, 1, 1)    # earliest > this (or no bars) => gap
DEFAULT_BATCH_SIZE = 25
EQUITY_ASSET_CLASS = "equity"
TIMEFRAME = "1d"

# Symbols stored without their class dot; providers expect the dotted form.
# Flagged for a BP28B follow-up — NOT remapped here.
DOTTED_TICKER_HINTS: dict[str, str] = {
    "BRKB": "BRK.B",
    "HEIA": "HEI.A",
    "MOGA": "MOG.A",
    "UHALB": "UHAL.B",
}


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GapSymbol:
    symbol: str
    earliest: dt.date | None      # None = no bars stored at all


@dataclass
class BackfillSummary:
    floor: dt.date
    deep_cohort_cutoff: dt.date
    dry_run: bool
    batch_size: int
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    universe_size: int = 0
    only_symbols: set[str] | None = None    # pilot scope, if any (normalized)
    include_benchmark: bool = False
    gap_symbols: list[GapSymbol] = field(default_factory=list)
    skipped_resume: list[str] = field(default_factory=list)
    processed: list[str] = field(default_factory=list)
    completed_with_data: list[str] = field(default_factory=list)
    completed_no_data: list[str] = field(default_factory=list)
    bars_written_by_symbol: dict[str, int] = field(default_factory=dict)
    benchmark: list[str] = field(default_factory=list)      # SPY etc., if appended
    benchmark_rows: int = 0
    bars_written: int = 0                                   # gap-symbol rows only
    failures: dict[str, str] = field(default_factory=dict)  # batch-level exceptions only
    batches: int = 0

    @property
    def gap_count(self) -> int:
        return len(self.gap_symbols)

    def _sample(self, names: list[str], n: int = 15) -> str:
        head = names[:n]
        tail = " …" if len(names) > n else ""
        return ", ".join(head) + tail

    def render(self) -> str:
        lines = [
            "=== BP28 gap-backfill summary ===",
            f"mode               : {'DRY-RUN (no network, no writes)' if self.dry_run else 'LIVE'}",
            f"backfill from      : {self.floor.isoformat()}  (start_date)",
            f"deep cohort cut    : {self.deep_cohort_cutoff.isoformat()}  (earliest > this => gap)",
            f"batch size         : {self.batch_size}",
            f"universe (equity)  : {self.universe_size}",
            f"pilot scope        : {len(self.only_symbols)} symbols" if self.only_symbols else "pilot scope        : (full universe)",
            f"gap symbols        : {self.gap_count}",
            f"skipped (resume)   : {len(self.skipped_resume)}",
            f"to process         : {len(self.gap_symbols) - len(self.skipped_resume)}",
            f"batches            : {self.batches}",
            f"processed          : {len(self.processed)}",
            f"  with data        : {len(self.completed_with_data)}",
            f"  no data          : {len(self.completed_no_data)}",
            f"bars written (gap) : {self.bars_written}",
            f"benchmark          : {'%d rows (%s)' % (self.benchmark_rows, ', '.join(self.benchmark)) if self.benchmark else 'disabled'}",
            f"batch failures     : {len(self.failures)}",
        ]
        if self.gap_symbols:
            lines.append(f"gap sample         : {self._sample([g.symbol for g in self.gap_symbols])}")
        if self.completed_no_data:
            lines.append(f"NO-DATA symbols    : {self._sample(sorted(self.completed_no_data))}")
        if self.failures:
            for sym, reason in list(self.failures.items())[:10]:
                lines.append(f"  FAIL {sym}: {reason}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Universe enumeration + gap detection (pure reads — sqlite/pg portable)
# ---------------------------------------------------------------------------


def enumerate_universe(session: Session) -> list[str]:
    """Active equity symbols from the ``asset`` table, upper-cased + sorted."""
    rows = session.scalars(
        select(Asset.symbol)
        .where(Asset.is_active.is_(True), Asset.asset_class == EQUITY_ASSET_CLASS)
        .order_by(Asset.symbol.asc())
    )
    return sorted({s.upper() for s in rows})


def earliest_bar_dates(session: Session) -> dict[str, dt.date | None]:
    """Map each active-equity symbol → earliest stored 1d bar date (None if no
    bars). Outer-joins so zero-history symbols are included; the timeframe
    filter lives in the JOIN ON clause to preserve the null rows."""
    stmt = (
        select(Asset.symbol, func.min(PriceBar.ts))
        .select_from(Asset)
        .join(
            PriceBar,
            and_(PriceBar.asset_id == Asset.id, PriceBar.timeframe == TIMEFRAME),
            isouter=True,
        )
        .where(Asset.is_active.is_(True), Asset.asset_class == EQUITY_ASSET_CLASS)
        .group_by(Asset.symbol)
    )
    out: dict[str, dt.date | None] = {}
    for symbol, min_ts in session.execute(stmt):
        out[symbol.upper()] = _as_date(min_ts)
    return out


def detect_gap_symbols(
    session: Session,
    *,
    deep_cohort_cutoff: dt.date = DEFAULT_DEEP_COHORT_CUTOFF,
) -> list[GapSymbol]:
    """Symbols needing backfill: no bars, or earliest bar later than
    ``deep_cohort_cutoff``. Sorted by symbol for deterministic batching."""
    gaps: list[GapSymbol] = []
    for symbol, earliest in earliest_bar_dates(session).items():
        if earliest is None or earliest > deep_cohort_cutoff:
            gaps.append(GapSymbol(symbol=symbol, earliest=earliest))
    gaps.sort(key=lambda g: g.symbol)
    return gaps


def _as_date(value: object) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        # Some drivers (e.g. sqlite) return func.min(ts) as an ISO string.
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return dt.date.fromisoformat(value[:10])
            except ValueError:
                return None
    return None


# ---------------------------------------------------------------------------
# Provider chain (Polygon raw → Tiingo → Yahoo) — distinct from the daily chain
# ---------------------------------------------------------------------------


def backfill_provider_chain() -> list[DailyPriceProvider]:
    """Polygon(raw) primary → Tiingo → Yahoo. Polygon leads here (unlike the
    daily chain) because the gap-backfill explicitly monetizes the paid Polygon
    history; its raw bars carry ``adjusted_close=None`` (priority 40 keeps it
    from overwriting Tiingo/Yahoo total-return bars on shared dates)."""
    from apps.api.src.config import settings

    chain: list[DailyPriceProvider] = []
    if settings.POLYGON_API_KEY:
        chain.append(PolygonProvider(api_key=settings.POLYGON_API_KEY))
    else:
        logger.warning("POLYGON_API_KEY not set — gap-backfill falls back to Tiingo/Yahoo")
    if settings.TIINGO_API_KEY:
        chain.append(TiingoProvider(api_key=settings.TIINGO_API_KEY))
    chain.append(YahooProvider())
    return chain


# ---------------------------------------------------------------------------
# Checkpoint (resume / idempotent)
# ---------------------------------------------------------------------------


def load_checkpoint(path: Path | None) -> dict[str, set[str]]:
    """Prior-run state: ``{"completed": {...}, "no_data": {...}}`` (both upper).
    ``completed`` = symbols backfilled with data; ``no_data`` = symbols whose
    providers returned nothing. Missing/corrupt → empties. Back-compatible with
    old checkpoints that only had ``completed``."""
    empty: dict[str, set[str]] = {"completed": set(), "no_data": set()}
    if path is None or not path.exists():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        logger.warning("checkpoint unreadable ({}): {} — starting fresh", path, exc)
        return empty
    return {
        "completed": {str(s).upper() for s in data.get("completed", [])},
        "no_data": {str(s).upper() for s in data.get("no_data", [])},
    }


def write_checkpoint(
    path: Path | None,
    *,
    floor: dt.date,
    completed: set[str],
    no_data: set[str],
    failures: dict[str, str],
) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "floor": floor.isoformat(),
        "completed": sorted(completed),     # backfilled with data
        "no_data": sorted(no_data),         # providers returned nothing
        "failed": failures,                 # batch-level exceptions
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _chunk(items: list[str], size: int) -> list[list[str]]:
    size = max(1, size)
    return [items[i : i + size] for i in range(0, len(items), size)]


async def backfill_gap_history(
    *,
    floor: dt.date = HISTORY_FLOOR,
    deep_cohort_cutoff: dt.date = DEFAULT_DEEP_COHORT_CUTOFF,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = True,
    resume: bool = True,
    retry_no_data: bool = False,
    include_benchmark: bool = False,
    only_symbols: set[str] | None = None,
    checkpoint_path: Path | None = None,
    providers: Sequence[DailyPriceProvider] | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    now: dt.datetime | None = None,
) -> BackfillSummary:
    """Detect gap symbols and (unless ``dry_run``) backfill each from ``floor``.

    ``floor`` is the backfill *start_date*; ``deep_cohort_cutoff`` is the
    gap-detection threshold (gap = no bars OR earliest > cutoff).

    ``only_symbols`` scopes the run to a pilot subset: after gap detection, only
    these symbols are kept (case/whitespace-normalized). Symbols not in the gap
    set are silently ignored. Applies to dry-run and live alike.

    Per-symbol outcomes are split into ``completed_with_data`` (>0 bars),
    ``completed_no_data`` (providers returned nothing), and ``failures`` (a batch
    raised). ``include_benchmark=False`` (default) means a scoped run writes ONLY
    the requested symbols; benchmark rows, if enabled, are reported separately.
    Reruns skip ``completed`` and (unless ``retry_no_data``) ``no_data`` symbols.

    ``dry_run=True`` (default) performs detection + resume filtering only — no
    provider calls, no DB writes, no checkpoint write. Safe to invoke anywhere.
    """
    started = now or dt.datetime.now(dt.timezone.utc)
    scope = {s.strip().upper() for s in only_symbols} if only_symbols else None
    summary = BackfillSummary(
        floor=floor,
        deep_cohort_cutoff=deep_cohort_cutoff,
        dry_run=dry_run,
        batch_size=batch_size,
        started_at=started,
        only_symbols=scope,
        include_benchmark=include_benchmark,
    )

    # --- 1. enumerate + detect (read-only) ---
    with session_factory() as session:
        summary.universe_size = len(enumerate_universe(session))
        summary.gap_symbols = detect_gap_symbols(
            session, deep_cohort_cutoff=deep_cohort_cutoff
        )

    # --- 1b. pilot scope filter (after detection, before batching) ---
    if scope is not None:
        summary.gap_symbols = [g for g in summary.gap_symbols if g.symbol in scope]

    # --- 2. resume filtering ---
    ckpt = load_checkpoint(checkpoint_path) if resume else {"completed": set(), "no_data": set()}
    completed: set[str] = set(ckpt["completed"])
    no_data: set[str] = set(ckpt["no_data"])
    skip = set(completed)
    if not retry_no_data:
        skip |= no_data
    to_process = [g.symbol for g in summary.gap_symbols if g.symbol not in skip]
    summary.skipped_resume = [g.symbol for g in summary.gap_symbols if g.symbol in skip]

    batches = _chunk(to_process, batch_size)
    summary.batches = len(batches)
    logger.info(
        "backfill_gap_history: universe={} gaps={} skipped_resume={} "
        "to_process={} batches={} dry_run={}",
        summary.universe_size, summary.gap_count, len(summary.skipped_resume),
        len(to_process), summary.batches, dry_run,
    )

    if dry_run:
        # Preview only — nothing fetched, nothing written, no checkpoint.
        logger.info("DRY-RUN: skipping all provider calls and DB writes")
        summary.finished_at = dt.datetime.now(dt.timezone.utc)
        return summary

    # --- 3. live backfill, batch by batch with checkpointing ---
    chain = list(providers) if providers is not None else backfill_provider_chain()
    benchmark_set = {b.upper() for b in BENCHMARK_SYMBOLS}
    for idx, batch in enumerate(batches, start=1):
        logger.info(
            "backfill batch {}/{} ({} symbols): {}",
            idx, summary.batches, len(batch), ", ".join(batch),
        )
        try:
            with session_factory() as session:
                report = await ingest_symbols(
                    session, batch,
                    providers=chain,
                    start_date=floor,
                    incremental=False,
                    include_benchmark=include_benchmark,
                )
            for sr in report.symbols:
                written = sr.bars_written + sr.bars_updated
                if sr.symbol in benchmark_set:
                    summary.benchmark.append(sr.symbol)
                    summary.benchmark_rows += written
                    continue
                summary.bars_written_by_symbol[sr.symbol] = written
                summary.bars_written += written
                if written > 0:
                    summary.completed_with_data.append(sr.symbol)
                    completed.add(sr.symbol)
                else:
                    summary.completed_no_data.append(sr.symbol)
                    no_data.add(sr.symbol)
            summary.processed.extend(batch)
        except Exception as exc:  # noqa: BLE001
            for sym in batch:
                summary.failures[sym] = str(exc)
            logger.error("backfill batch {} crashed: {}", idx, exc)
        write_checkpoint(
            checkpoint_path,
            floor=floor,
            completed=completed,
            no_data=no_data,
            failures=summary.failures,
        )

    summary.finished_at = dt.datetime.now(dt.timezone.utc)
    logger.info("backfill_gap_history complete:\n{}", summary.render())
    return summary
