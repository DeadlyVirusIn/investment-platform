"""Backfill regime_snapshot rows for a date range.

Usage::

    python -m scripts.backfill_regime --from 2025-05-01 --to 2026-04-17
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt

from loguru import logger

from apps.worker.src.jobs.compute_regime_snapshot import compute_regime_snapshot


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _business_days(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


async def _run(start: dt.date, end: dt.date) -> None:
    total = 0
    ok = 0
    for d in _business_days(start, end):
        total += 1
        try:
            await compute_regime_snapshot(d)
            ok += 1
        except Exception as e:
            logger.error("[backfill_regime] {} failed: {}", d, e)
    logger.info(
        "[backfill_regime] done range={}..{} attempted={} succeeded={}",
        start, end, total, ok,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill regime_snapshot rows.")
    parser.add_argument("--from", dest="from_", required=True, type=_parse_date)
    parser.add_argument("--to", dest="to", required=True, type=_parse_date)
    args = parser.parse_args()
    if args.to < args.from_:
        raise SystemExit("--to must be >= --from")
    asyncio.run(_run(args.from_, args.to))


if __name__ == "__main__":
    main()
