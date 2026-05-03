"""Ingestion orchestrator. Tiingo primary → Yahoo fallback.

Sequence per symbol:
    1. find start date (incremental with 5-bar buffer, else requested range)
    2. fetch from provider chain until first non-empty (or exhaust)
    3. normalize → validate → dedupe
    4. per-bar source-priority upsert
    5. return per-symbol RunReport for logging/ops
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PriceBar
from apps.api.src.domain.prices.canonical import CanonicalBar
from apps.api.src.domain.prices.normalize import normalize_batch
from apps.api.src.domain.prices.providers.base import (
    DailyPriceProvider,
    NoDataError,
    ProviderError,
)
from apps.api.src.domain.prices.reconcile import (
    ExistingBar,
    dedupe_payload,
    should_upsert,
)
from apps.api.src.domain.prices.validate import validate_batch

BENCHMARK_SYMBOLS: tuple[str, ...] = ("SPY",)
INCREMENTAL_BUFFER_DAYS = 5          # lookback buffer for incremental runs


@dataclass
class SymbolRunReport:
    symbol: str
    provider_attempted: list[str] = field(default_factory=list)
    provider_used: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    bars_fetched: int = 0
    bars_rejected: int = 0
    bars_written: int = 0
    bars_updated: int = 0
    bars_skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass
class IngestionRunReport:
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    symbols: list[SymbolRunReport] = field(default_factory=list)

    @property
    def total_written(self) -> int:
        return sum(s.bars_written + s.bars_updated for s in self.symbols)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_or_create_asset(session: Session, symbol: str) -> Asset:
    asset = session.scalars(select(Asset).where(Asset.symbol == symbol.upper())).first()
    if asset is not None:
        return asset
    asset = Asset(
        symbol=symbol.upper(),
        asset_class="etf" if symbol.upper() == "SPY" else "equity",
        exchange="NYSE" if symbol.upper() == "SPY" else "NASDAQ",
        currency="USD",
        is_active=True,
    )
    session.add(asset)
    session.flush()
    return asset


def _latest_ts(session: Session, asset_id: str) -> dt.datetime | None:
    stmt = (
        select(PriceBar.ts)
        .where(PriceBar.asset_id == asset_id, PriceBar.timeframe == "1d")
        .order_by(PriceBar.ts.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


def _existing_for_date(
    session: Session, asset_id: str, ts: dt.datetime
) -> ExistingBar | None:
    """Pick the best existing PriceBar for (asset, 1d, ts) by source priority."""
    from apps.api.src.domain.prices.canonical import source_priority
    stmt = (
        select(PriceBar)
        .where(
            PriceBar.asset_id == asset_id,
            PriceBar.timeframe == "1d",
            PriceBar.ts == ts,
        )
    )
    rows = list(session.execute(stmt).scalars())
    if not rows:
        return None
    # Best = highest source_priority, tiebreak by adjusted_close presence
    rows.sort(
        key=lambda r: (
            source_priority(r.provider or ""),
            1 if r.adjusted_close is not None else 0,
        ),
        reverse=True,
    )
    best = rows[0]
    return ExistingBar(
        source=best.provider or "",
        open=best.open,
        close=best.close,
        adjusted_close=best.adjusted_close,
        volume=best.volume,
    )


def _ts_for_date(d: dt.date) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)


# ---------------------------------------------------------------------------
# Core ingestion
# ---------------------------------------------------------------------------


async def ingest_symbol(
    session: Session,
    symbol: str,
    *,
    providers: Sequence[DailyPriceProvider],
    start_date: dt.date,
    end_date: dt.date,
    now: dt.datetime | None = None,
) -> SymbolRunReport:
    """Fetch + normalize + validate + upsert for one symbol. Never raises."""
    now = now or dt.datetime.now(dt.timezone.utc)
    report = SymbolRunReport(
        symbol=symbol.upper(),
        start_date=start_date,
        end_date=end_date,
    )

    # --- 1. Provider chain ---
    raws = None
    used_provider: DailyPriceProvider | None = None
    for p in providers:
        report.provider_attempted.append(p.name)
        try:
            fetched = await p.fetch_daily_bars(symbol, start_date, end_date)
        except NoDataError as exc:
            report.warnings.append(f"{p.name}: no data ({exc})")
            continue
        except ProviderError as exc:
            report.warnings.append(f"{p.name}: error ({exc})")
            continue
        if not fetched:
            report.warnings.append(f"{p.name}: empty payload")
            continue
        raws = fetched
        used_provider = p
        break

    if raws is None or used_provider is None:
        report.failure_reason = "all providers failed or empty"
        return report

    report.provider_used = used_provider.name
    report.bars_fetched = len(raws)

    # --- 2. Normalize ---
    canonicals, dropped = normalize_batch(
        raws, source=used_provider.name, fetched_at=now,
    )
    if dropped:
        report.warnings.append(f"normalize dropped {dropped} malformed rows")

    # --- 3. Dedupe payload ---
    deduped = dedupe_payload(canonicals)
    if len(deduped) != len(canonicals):
        report.warnings.append(
            f"deduped {len(canonicals) - len(deduped)} intra-payload dupes"
        )

    # --- 4. Validate ---
    accepted, rejected = validate_batch(deduped)
    report.bars_rejected = len(rejected)
    if rejected:
        sample = "; ".join(r[1].reject_reason or "?" for r in rejected[:3])
        report.warnings.append(f"validation rejected {len(rejected)}: {sample}")

    if not accepted:
        return report

    # --- 5. Resolve asset ---
    asset = _get_or_create_asset(session, symbol)

    # --- 6. Upsert with source-priority policy ---
    for bar in accepted:
        ts = _ts_for_date(bar.trade_date)
        existing = _existing_for_date(session, asset.id, ts)
        if not should_upsert(bar, existing):
            report.bars_skipped += 1
            continue
        result = _upsert_bar(session, asset.id, bar, ts)
        if result == "inserted":
            report.bars_written += 1
        elif result == "updated":
            report.bars_updated += 1

    session.flush()
    return report


def _upsert_bar(
    session: Session,
    asset_id: str,
    bar: CanonicalBar,
    ts: dt.datetime,
) -> str:
    """Upsert keyed on (asset_id, timeframe, ts, provider). Returns 'inserted'
    or 'updated'."""
    stmt = (
        pg_insert(PriceBar)
        .values(
            asset_id=asset_id,
            timeframe="1d",
            ts=ts,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            adjusted_close=bar.adjusted_close,
            volume=bar.volume,
            provider=bar.source,
        )
        .on_conflict_do_update(
            constraint="uq_price_bar",
            set_={
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "adjusted_close": bar.adjusted_close,
                "volume": bar.volume,
            },
        )
        .returning(PriceBar.id, PriceBar.created_at)
    )
    row = session.execute(stmt).first()
    # pg doesn't tell us insert-vs-update via ON CONFLICT DO UPDATE return
    # without xmax tricks. For the purpose of per-symbol reporting treat any
    # conflict resolution as "updated" and fresh inserts as "inserted" using
    # created_at recency.
    if row is None:
        return "skipped"
    now = dt.datetime.now(dt.timezone.utc)
    created_at = row[1]
    if created_at is None:
        return "inserted"
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=dt.timezone.utc)
    return "inserted" if (now - created_at).total_seconds() < 5 else "updated"


# ---------------------------------------------------------------------------
# High-level runners
# ---------------------------------------------------------------------------


def resolve_start_date(
    session: Session,
    asset_id: str,
    *,
    incremental_floor: dt.date,
    lookback_buffer_days: int = INCREMENTAL_BUFFER_DAYS,
) -> dt.date:
    """Pick incremental start date given the latest stored bar.

    Returns the later of:
      - latest_ts - lookback_buffer_days (to allow late corrections)
      - ``incremental_floor`` (hard cap so we don't regress forever)
    If no bars exist yet, returns ``incremental_floor`` (caller's backfill
    floor).
    """
    latest = _latest_ts(session, asset_id)
    if latest is None:
        return incremental_floor
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=dt.timezone.utc)
    start = latest.date() - dt.timedelta(days=lookback_buffer_days)
    return max(start, incremental_floor)


async def ingest_symbols(
    session: Session,
    symbols: list[str],
    *,
    providers: Sequence[DailyPriceProvider],
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    incremental: bool = True,
    incremental_floor_days: int = 365,
    now: dt.datetime | None = None,
) -> IngestionRunReport:
    """Run ingestion over a list of symbols. Always includes benchmark symbols."""
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.date()

    # Always include benchmarks
    symbol_set = {s.upper() for s in symbols}
    for b in BENCHMARK_SYMBOLS:
        symbol_set.add(b)
    symbols_sorted = sorted(symbol_set)

    run = IngestionRunReport(started_at=now)

    absolute_end = end_date or today
    fixed_start = start_date

    for symbol in symbols_sorted:
        try:
            asset = _get_or_create_asset(session, symbol)
            session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("failed to resolve asset {}: {}", symbol, exc)
            continue

        if fixed_start is not None:
            effective_start = fixed_start
        elif incremental:
            floor = absolute_end - dt.timedelta(days=incremental_floor_days)
            effective_start = resolve_start_date(
                session, asset.id, incremental_floor=floor,
            )
        else:
            effective_start = absolute_end - dt.timedelta(days=incremental_floor_days)

        try:
            report = await ingest_symbol(
                session, symbol,
                providers=providers,
                start_date=effective_start,
                end_date=absolute_end,
                now=now,
            )
            session.commit()
            run.symbols.append(report)
            _log_symbol(report)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            sr = SymbolRunReport(symbol=symbol, failure_reason=str(exc))
            run.symbols.append(sr)
            logger.error("ingest_symbol crashed for {}: {}", symbol, exc)

    run.finished_at = dt.datetime.now(dt.timezone.utc)
    logger.info(
        "ingest_symbols complete: symbols={} total_written={}",
        len(run.symbols), run.total_written,
    )
    return run


def _log_symbol(r: SymbolRunReport) -> None:
    logger.info(
        "ingest {} provider={} fetched={} written={} updated={} "
        "rejected={} skipped={} failure={}",
        r.symbol, r.provider_used, r.bars_fetched, r.bars_written,
        r.bars_updated, r.bars_rejected, r.bars_skipped, r.failure_reason,
    )
    for w in r.warnings:
        logger.warning("  {}: {}", r.symbol, w)
