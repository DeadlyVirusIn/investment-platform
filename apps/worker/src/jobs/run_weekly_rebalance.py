"""Scheduled job: weekly rebalance for active paper portfolios.

Cron target (stated default): ``0 13 * * 1`` (Monday 13:00 UTC, near US
equity-market open). All trades route through
``rebalance_engine.run_rebalance`` → ``submit_trade``. No bypass path.
"""

from __future__ import annotations

import datetime as dt

from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import PaperPortfolio
from apps.api.src.domain.stock_engine.portfolio.rebalance_engine import (
    DEFAULT_UNIVERSE,
    run_rebalance,
)


async def run_weekly_rebalance(
    as_of: dt.date | None = None,
    universe_name: str = DEFAULT_UNIVERSE,
) -> None:
    target = as_of or dt.date.today()

    with SessionLocal() as session:
        portfolio_ids = [
            p.id for p in session.scalars(
                select(PaperPortfolio).where(PaperPortfolio.is_active.is_(True))
            )
        ]

    for portfolio_id in portfolio_ids:
        try:
            with SessionLocal() as session:
                portfolio = session.get(PaperPortfolio, portfolio_id)
                if portfolio is None:
                    continue
                report = run_rebalance(
                    session, portfolio, as_of=target, universe_name=universe_name,
                )
                session.commit()

                executed_entries = sum(1 for e in report.entries if e.status == "executed")
                executed_exits = sum(1 for e in report.exits if e.status == "executed")
                logger.info(
                    "run_weekly_rebalance portfolio={} regime={}/{} "
                    "entries_ok={} exits_ok={} notes={}",
                    portfolio_id,
                    report.market_trend, report.vol_regime,
                    executed_entries, executed_exits, report.notes,
                )
        except Exception as exc:  # noqa: BLE001 — one portfolio must not kill batch
            logger.error("run_weekly_rebalance failed for {}: {}", portfolio_id, exc)
