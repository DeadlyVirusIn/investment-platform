"""Shadow execution CLI — observation only.

Walks historical_label days, builds PrimarySignal for each row (via
`PrimarySignal.from_raw` to enforce scale invariants), loads SPY closes
for regime classification, runs baseline / normalized / kelly strategies
in parallel, and writes:

  - artifacts/shadow_execution_days.jsonl  (per-day log)
  - artifacts/shadow_execution_report.md   (aggregate comparison)

No writes to recommendation / action / ranked_signal tables.
No auto-selection of winner.

Usage::

    python -m scripts.run_shadow_execution
    python -m scripts.run_shadow_execution --days 60 --market-symbol SPY
    python -m scripts.run_shadow_execution --engine-version X --market-symbol QQQ
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset, HistoricalLabel, PriceBar
from apps.api.src.domain.execution.integrator import PrimarySignal
from apps.api.src.domain.execution.shadow import (
    PrimaryWithReturn,
    aggregate_all,
    compare_strategies,
    format_day_log,
    run_shadow_day,
)
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

ARTIFACTS_DIR = Path("artifacts")
PER_DAY_LOG = ARTIFACTS_DIR / "shadow_execution_days.jsonl"
REPORT_PATH = ARTIFACTS_DIR / "shadow_execution_report.md"


def _load_market_prices(
    session, market_symbol: str, as_of_max: dt.date, lookback_bars: int = 120,
) -> list[float]:
    """Load trailing daily closes for the market proxy up to as_of_max."""
    asset = session.execute(
        select(Asset).where(Asset.symbol == market_symbol),
    ).scalar_one_or_none()
    if asset is None:
        return []
    end_ts = dt.datetime.combine(as_of_max, dt.time(23, 59, 59))
    stmt = (
        select(PriceBar)
        .where(
            PriceBar.asset_id == asset.id,
            PriceBar.timeframe == "1d",
            PriceBar.ts <= end_ts,
        )
        .order_by(PriceBar.ts.desc())
        .limit(lookback_bars)
    )
    bars = list(session.execute(stmt).scalars().all())
    bars = list(reversed(bars))
    return [float(b.close) for b in bars if b.close is not None]


def _load_rows_grouped(
    session, engine_version: str, days: int,
) -> list[tuple[dt.date, list[HistoricalLabel]]]:
    """Return trailing `days` business days of Buy rows, newest last."""
    rows = list(session.execute(
        select(HistoricalLabel).where(
            HistoricalLabel.engine_version == engine_version,
            HistoricalLabel.action == "Buy",
        ).order_by(HistoricalLabel.as_of_date.asc())
    ).scalars().all())
    by_day: dict[dt.date, list[HistoricalLabel]] = defaultdict(list)
    for r in rows:
        by_day[r.as_of_date].append(r)
    sorted_days = sorted(by_day.keys())
    tail = sorted_days[-days:] if days > 0 else sorted_days
    return [(d, by_day[d]) for d in tail]


def _build_primary_with_return(row: HistoricalLabel) -> PrimaryWithReturn:
    """Apply scale invariants at boundary. vol_is_daily=False because
    regime_engine stores realized_vol_20d as annualized.
    """
    primary = PrimarySignal.from_raw(
        symbol=row.symbol,
        composite_score=row.composite_score,
        confidence_raw=row.confidence,
        vol_raw=row.realized_vol_20d,
        vol_is_daily=False,
    )
    return PrimaryWithReturn(
        primary=primary,
        forward_return_pct=float(row.forward_return_pct or 0.0),
        barrier_n_bars=int(row.barrier_n_bars or 20),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-version", type=str, default=MODEL_VERSION)
    parser.add_argument(
        "--market-symbol", type=str, default="SPY",
        help="market proxy for regime classification",
    )
    parser.add_argument(
        "--days", type=int, default=0,
        help="trailing business days to replay (0 = all available)",
    )
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    PER_DAY_LOG.unlink(missing_ok=True)

    with SessionLocal() as session:
        grouped = _load_rows_grouped(session, args.engine_version, args.days)
        if not grouped:
            logger.error(
                "[shadow.cli] no rows for engine_version={}", args.engine_version,
            )
            return 1
        logger.info(
            "[shadow.cli] engine_version={} days={} first={} last={}",
            args.engine_version, len(grouped), grouped[0][0], grouped[-1][0],
        )

        shadow_days = []
        for as_of, rows in grouped:
            market_prices = _load_market_prices(
                session, args.market_symbol, as_of,
            )
            if not market_prices:
                logger.warning(
                    "[shadow.cli] {} no market prices for {}, skipping",
                    as_of, args.market_symbol,
                )
                continue

            pwrs = [_build_primary_with_return(r) for r in rows]
            day = run_shadow_day(as_of, pwrs, market_prices)
            shadow_days.append(day)

            line = format_day_log(day)
            logger.info(line)
            with PER_DAY_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "date": str(day.date),
                    "regime": day.regime.regime,
                    "regime_multiplier": day.regime.multiplier,
                    "n_trades": day.n_trades,
                    "avg_position_size": day.avg_position_size,
                    "total_exposure": day.total_exposure,
                    "daily_return": day.daily_return,
                }) + "\n")

    if not shadow_days:
        logger.error("[shadow.cli] no shadow days produced")
        return 1

    metrics = aggregate_all(shadow_days)
    report = compare_strategies(
        metrics["baseline"], metrics["normalized"], metrics["kelly"],
    )

    # Report
    lines = []
    lines.append("# Shadow Execution Report — Observation Only")
    lines.append("")
    lines.append(f"- engine_version: `{args.engine_version}`")
    lines.append(f"- market_proxy: `{args.market_symbol}`")
    lines.append(f"- days_replayed: {len(shadow_days)}")
    lines.append(f"- first_date: {shadow_days[0].date}")
    lines.append(f"- last_date: {shadow_days[-1].date}")
    lines.append(f"- per_day_log: `{PER_DAY_LOG}`")
    lines.append("")
    lines.append("## Aggregate comparison")
    lines.append("")
    lines.append("```")
    lines.append(report.table)
    lines.append("```")
    lines.append("")

    # Regime breakdown
    regime_counts: dict[str, int] = defaultdict(int)
    for d in shadow_days:
        regime_counts[d.regime.regime] += 1
    lines.append("## Regime distribution over window")
    lines.append("")
    for r in sorted(regime_counts):
        lines.append(f"- {r}: {regime_counts[r]} days")
    lines.append("")
    lines.append("## Last-day snapshot")
    lines.append("")
    last = shadow_days[-1]
    lines.append("```")
    lines.append(format_day_log(last))
    lines.append("```")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- baseline  = size=1.0 flat, no sizing, no regime gating."
    )
    lines.append(
        "- normalized = `normalized_size(composite, confidence, vol_annualized)` "
        "* regime_multiplier."
    )
    lines.append(
        "- kelly     = `kelly_size(composite, confidence, vol_annualized)` "
        "* regime_multiplier (quarter-Kelly)."
    )
    lines.append(
        "- All strategies run on identical primaries; no filtering. This is "
        "observation-only; no auto-selection of best strategy."
    )
    lines.append(
        "- `confidence` normalized at boundary via `normalize_confidence`; "
        "`realized_vol_20d` treated as annualized (regime_engine invariant)."
    )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    logger.info("[shadow.cli] report written -> {}", REPORT_PATH)

    # Also echo the table to stdout
    print()
    print(report.table)
    print()
    print(f"Per-day log  -> {PER_DAY_LOG}")
    print(f"Report memo  -> {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
