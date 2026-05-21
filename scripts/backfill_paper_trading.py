"""Historical paper-trading replay through the LIVE stack.

Pipeline per day (identical to production scheduler):

    candidate_idea(as_of) → auto_trader(as_of) → submit_trade → snapshot

Prerequisite: `candidate_idea` must already contain rows for every
replay day. Run `scripts.backfill_recommendations` first.

No historical_label shortcut. No strategy bypass. ML sizing respects
ENABLE_ML_SIZING flag exactly as live.

Usage::

    # 1. Backfill signals (if not already done)
    python -m scripts.backfill_recommendations --days 60

    # 2. Replay paper trading over those signals
    python -m scripts.backfill_paper_trading --days 60 --reset
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt

from loguru import logger
from sqlalchemy import delete, select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import (
    CandidateIdea,
    PaperEquitySnapshot,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
)
from apps.worker.src.jobs.run_paper_trading import run_paper_trading


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


def _reset_paper_state() -> None:
    logger.warning("[replay] RESET: clearing paper_trade, paper_position, paper_equity_snapshot")
    with SessionLocal() as session:
        session.execute(delete(PaperTrade))
        session.execute(delete(PaperPosition))
        session.execute(delete(PaperEquitySnapshot))
        for p in session.scalars(
            select(PaperPortfolio).where(PaperPortfolio.is_active.is_(True))
        ):
            p.cash = p.starting_cash
        session.commit()


def _candidate_coverage(as_of: dt.date) -> dict:
    with SessionLocal() as session:
        rows = list(session.scalars(
            select(CandidateIdea).where(CandidateIdea.as_of_date == as_of)
        ))
    buys = sum(1 for r in rows if r.status == "accepted" and r.action == "Buy")
    trims = sum(1 for r in rows if r.status == "accepted" and r.action == "Trim")
    sells = sum(1 for r in rows if r.status == "accepted" and r.action == "Sell")
    return {"total": len(rows), "buys": buys, "trims": trims, "sells": sells}


async def _run(days: list[dt.date]) -> None:
    for day in days:
        cov = _candidate_coverage(day)
        if cov["total"] == 0:
            logger.info("[replay] {} SKIP no candidate_idea rows (run backfill_recommendations first)", day)
            continue
        logger.info(
            "[replay] {} candidates total={} buys={} trims={} sells={}",
            day, cov["total"], cov["buys"], cov["trims"], cov["sells"],
        )
        try:
            await run_paper_trading(as_of=day)
        except Exception as exc:
            logger.error("[replay] {} failed: {}", day, exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay paper trading via live stack per day.")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--from", dest="from_", type=_parse_date)
    grp.add_argument("--days", type=int)
    parser.add_argument("--to", dest="to", type=_parse_date)
    parser.add_argument("--reset", action="store_true",
                        help="Clear paper_trade/paper_position/paper_equity_snapshot first.")
    args = parser.parse_args()

    # Default end = latest date with candidate_idea rows
    with SessionLocal() as session:
        latest_cand = session.execute(
            select(CandidateIdea.as_of_date).order_by(CandidateIdea.as_of_date.desc()).limit(1)
        ).scalar_one_or_none()
    end = args.to or latest_cand or dt.date.today()
    if args.from_:
        days = list(_business_days(args.from_, end))
    elif args.days:
        days = _last_n_business_days(end, args.days)
    else:
        days = _last_n_business_days(end, 30)

    if not days:
        raise SystemExit("empty date range")

    logger.info("[replay] window {} → {} ({} days)", days[0], days[-1], len(days))
    if args.reset:
        _reset_paper_state()

    asyncio.run(_run(days))

    # Summary
    with SessionLocal() as session:
        trade_count = session.execute(select(PaperTrade)).fetchall()
        pos_open = session.execute(
            select(PaperPosition).where(PaperPosition.is_open.is_(True))
        ).fetchall()
        snap_count = session.execute(select(PaperEquitySnapshot)).fetchall()
    logger.info(
        "[replay] DONE trades={} open_positions={} snapshots={}",
        len(trade_count), len(pos_open), len(snap_count),
    )


if __name__ == "__main__":
    main()
