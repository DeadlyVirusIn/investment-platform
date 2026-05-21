"""Historical recommendation backfill — runs the live decision engine
(`generate_stock_candidates`) per business day and persists candidate_idea
rows with full status/action/rejection_reason/composite/confidence/factor
breakdown payloads. Reuses production code; no strategy changes.

Usage::

    python -m scripts.backfill_recommendations --from 2024-01-01 --to 2026-03-13
    python -m scripts.backfill_recommendations --days 60
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt

from loguru import logger

from apps.worker.src.jobs.generate_stock_candidates import (
    generate_stock_candidates,
)
from apps.api.src.domain.stock_engine.decision_engine import DEFAULT_UNIVERSE


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _business_days(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def _last_n_business_days(end: dt.date, n: int) -> list[dt.date]:
    out: list[dt.date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return sorted(out)


async def _run(days: list[dt.date], universe: str) -> None:
    total = 0
    ok = 0
    for d in days:
        total += 1
        try:
            await generate_stock_candidates(d, universe_name=universe)
            ok += 1
        except Exception as exc:
            logger.error("[backfill_recs] {} failed: {}", d, exc)
    logger.info(
        "[backfill_recs] done range={}..{} attempted={} succeeded={}",
        days[0], days[-1], total, ok,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill candidate_idea via live engine per day.")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--from", dest="from_", type=_parse_date)
    grp.add_argument("--days", type=int)
    parser.add_argument("--to", dest="to", type=_parse_date, default=dt.date.today())
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE)
    args = parser.parse_args()

    if args.from_:
        days = list(_business_days(args.from_, args.to))
    elif args.days:
        days = _last_n_business_days(args.to, args.days)
    else:
        days = _last_n_business_days(args.to, 30)

    if not days:
        raise SystemExit("empty date range")
    logger.info("[backfill_recs] window {} → {} ({} days) universe={}",
                days[0], days[-1], len(days), args.universe)
    asyncio.run(_run(days, args.universe))


if __name__ == "__main__":
    main()
