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

NOTE — benchmark: ``ingest_symbols`` always appends SPY to every call, so SPY is
(idempotently) re-pulled once per batch in a real run. Harmless given the
source-priority upsert; called out for transparency.
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
from apps.api.src.domain.prices.service import ingest_symbols

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
    gap_symbols: list[GapSymbol] = field(default_factory=list)
    skipped_resume: list[str] = field(default_factory=list)
    processed: list[str] = field(default_factory=list)
    bars_written: int = 0
    failures: dict[str, str] = field(default_factory=dict)
    batches: int = 0

    @property
    def gap_count(self) -> int:
        return len(self.gap_symbols)

    def render(self) -> str:
        lines = [
            "=== BP28 gap-backfill summary ===",
            f"mode             : {'DRY-RUN (no network, no writes)' if self.dry_run else 'LIVE'}",
            f"backfill from    : {self.floor.isoformat()}  (start_date)",
            f"deep cohort cut  : {self.deep_cohort_cutoff.isoformat()}  (earliest > this => gap)",
            f"batch size       : {self.batch_size}",
            f"universe (equity): {self.universe_size}",
            f"gap symbols      : {self.gap_count}",
            f"skipped (resume) : {len(self.skipped_resume)}",
            f"to process       : {len(self.gap_symbols) - len(self.skipped_resume)}",
            f"batches          : {self.batches}",
            f"processed        : {len(self.processed)}",
            f"bars written     : {self.bars_written}",
            f"failures         : {len(self.failures)}",
        ]
        sample = [g.symbol for g in self.gap_symbols][:15]
        if sample:
            tail = " …" if self.gap_count > len(sample) else ""
            lines.append(f"gap sample       : {', '.join(sample)}{tail}")
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


def load_checkpoint(path: Path | None) -> set[str]:
    """Completed-symbol set from a prior run. Missing/corrupt → empty set."""
    if path is None or not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        logger.warning("checkpoint unreadable ({}): {} — starting fresh", path, exc)
        return set()
    return {str(s).upper() for s in data.get("completed", [])}


def write_checkpoint(
    path: Path | None,
    *,
    floor: dt.date,
    completed: set[str],
    failures: dict[str, str],
) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "floor": floor.isoformat(),
        "completed": sorted(completed),
        "failed": failures,
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
    checkpoint_path: Path | None = None,
    providers: Sequence[DailyPriceProvider] | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    now: dt.datetime | None = None,
) -> BackfillSummary:
    """Detect gap symbols and (unless ``dry_run``) backfill each from ``floor``.

    ``floor`` is the backfill *start_date*; ``deep_cohort_cutoff`` is the
    gap-detection threshold (gap = no bars OR earliest > cutoff).

    ``dry_run=True`` (default) performs detection + resume filtering only — no
    provider calls, no DB writes, no checkpoint write. Safe to invoke anywhere.
    """
    started = now or dt.datetime.now(dt.timezone.utc)
    summary = BackfillSummary(
        floor=floor,
        deep_cohort_cutoff=deep_cohort_cutoff,
        dry_run=dry_run,
        batch_size=batch_size,
        started_at=started,
    )

    # --- 1. enumerate + detect (read-only) ---
    with session_factory() as session:
        summary.universe_size = len(enumerate_universe(session))
        summary.gap_symbols = detect_gap_symbols(
            session, deep_cohort_cutoff=deep_cohort_cutoff
        )

    # --- 2. resume filtering ---
    completed = load_checkpoint(checkpoint_path) if resume else set()
    to_process = [g.symbol for g in summary.gap_symbols if g.symbol not in completed]
    summary.skipped_resume = [
        g.symbol for g in summary.gap_symbols if g.symbol in completed
    ]

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
                )
            summary.bars_written += report.total_written
            summary.processed.extend(batch)
            completed.update(batch)
        except Exception as exc:  # noqa: BLE001
            for sym in batch:
                summary.failures[sym] = str(exc)
            logger.error("backfill batch {} crashed: {}", idx, exc)
        write_checkpoint(
            checkpoint_path,
            floor=floor,
            completed=completed,
            failures=summary.failures,
        )

    summary.finished_at = dt.datetime.now(dt.timezone.utc)
    logger.info("backfill_gap_history complete:\n{}", summary.render())
    return summary
