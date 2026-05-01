"""Phase 11X — safe gate-evolution shadow driver.

Read-only daily/backfill driver. NEVER writes to paper_trade,
paper_position, paper_run_log, candidate_idea, or any execution
surface. Only writes to public.safe_gate_evolution_shadow.

Usage:
    # single date
    python -m scripts.run_safe_gate_evolution_shadow --as-of 2026-04-29

    # backfill range
    python -m scripts.run_safe_gate_evolution_shadow \\
        --start 2026-04-29 --end 2026-05-01
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Sequence

from loguru import logger

from apps.api.src.data.strategy.safe_gate_evolution_shadow import (
    evaluate_and_persist,
)
from apps.api.src.db import SessionLocal


def _trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    out: list[dt.date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += dt.timedelta(days=1)
    return out


def _parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_safe_gate_evolution_shadow",
        description=(
            "Phase 11X shadow-only diagnostic. Read-only against "
            "production state; writes one row per day to "
            "public.safe_gate_evolution_shadow."
        ),
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--as-of",
        type=lambda s: dt.date.fromisoformat(s),
        help="Single ISO date.",
    )
    g.add_argument(
        "--start",
        type=lambda s: dt.date.fromisoformat(s),
        help="Range start (inclusive); requires --end.",
    )
    p.add_argument(
        "--end",
        type=lambda s: dt.date.fromisoformat(s),
        help="Range end (inclusive); requires --start.",
    )
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    if args.as_of is not None:
        dates = [args.as_of]
    else:
        if args.end is None:
            logger.error("--start requires --end")
            return 2
        if args.start > args.end:
            logger.error("--start must be <= --end")
            return 2
        dates = _trading_days(args.start, args.end)

    out: list[dict] = []
    with SessionLocal() as session:
        for d in dates:
            result, inserted = evaluate_and_persist(session, d)
            out.append({
                "run_date": d.isoformat(),
                "would_trade": result.would_trade,
                "symbol": result.symbol,
                "macro_favorable_count": result.macro_favorable_count,
                "shadow_reason": result.shadow_reason,
                "inserted": inserted,
            })
    logger.info("safe_gate_evolution_shadow summary: {}", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
