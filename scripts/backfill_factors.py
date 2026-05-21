"""Backfill factor_snapshot rows for a date range.

Iterates business days (Mon–Fri, skips weekends; no market-holiday calendar)
between ``--from`` and ``--to`` inclusive and runs the worker job for each
day. Idempotent — existing rows are upserted.

Usage::

    python -m scripts.backfill_factors --from 2026-01-01 --to 2026-04-19
    python -m scripts.backfill_factors --from 2026-04-01            # to today
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt

from loguru import logger

from apps.worker.src.jobs.compute_factor_snapshots import compute_factor_snapshots

DEFAULT_UNIVERSE = "stock_swing_v1"


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _business_days(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        if d.weekday() < 5:  # 0..4 = Mon..Fri
            yield d
        d += dt.timedelta(days=1)


async def _run(start: dt.date, end: dt.date, universe: str) -> None:
    total = 0
    for d in _business_days(start, end):
        await compute_factor_snapshots(d, universe_name=universe)
        total += 1
    logger.info("backfill_factors complete: range={}..{} days={}", start, end, total)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill factor_snapshot rows.")
    parser.add_argument("--from", dest="from_", required=True, type=_parse_date)
    parser.add_argument("--to", dest="to", type=_parse_date, default=dt.date.today())
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE)
    args = parser.parse_args()

    if args.to < args.from_:
        raise SystemExit("--to must be >= --from")

    asyncio.run(_run(args.from_, args.to, args.universe))


if __name__ == "__main__":
    main()
