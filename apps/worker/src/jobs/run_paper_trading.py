"""Scheduled job: run the paper-trading auto-trader over active portfolios.

For each active PaperPortfolio:
    1. Generate decisions via auto_trader (sells evaluated first, then buys)
    2. Execute via submit_trade (next-day-open fill)
    3. Snapshot equity

Per-portfolio try/except — one failure does not abort the batch. Idempotent:
re-running on the same day reuses the existing daily equity snapshot row
(UPSERT) and skips decisions whose fills cannot be satisfied.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import PaperPortfolio
from apps.api.src.domain.paper_trading.auto_trader import (
    AutoTradeConfig,
    auto_trade_portfolio,
)
from apps.api.src.domain.paper_trading.paper_service import snapshot_equity_now

SKIPS_DIR = Path("artifacts/paper_trading_skips")


async def run_paper_trading(as_of: dt.date | None = None) -> None:
    """Run the auto-trader for every active paper portfolio.

    When ``as_of`` is supplied, the run is replayed *as of* that historical
    date: signals come from candidate_idea rows for that date, and trade
    submission timestamps are anchored to 15:00 UTC on as_of so next-bar
    fills land on the correct historical open.
    """
    if as_of is not None:
        now = dt.datetime.combine(as_of, dt.time(15, 0), tzinfo=dt.timezone.utc)
    else:
        # Phase 11V — anchor live submitted_at to the same 15:00 UTC
        # convention used by historical replay above. Without this the
        # cron-fired live run sets submitted_at = run-time
        # (~03:30/04:30 UTC), which under the strict next-bar-fill
        # rule (`bar.ts > submitted_at`, with bar.ts = trading-day
        # 00:00 UTC) can never match a future bar. The fix preserves
        # T+1 semantics: today's bar (00:00 UTC) is still < 15:00,
        # so no same-day fill; tomorrow's bar (00:00 UTC of next
        # trading day) is > today's 15:00 UTC, so the next run fills
        # correctly. NEVER changes the strict `>` fill condition,
        # the price_bar schema, or the cron schedule.
        now = dt.datetime.combine(
            dt.datetime.now(dt.timezone.utc).date(),
            dt.time(15, 0),
            tzinfo=dt.timezone.utc,
        )
    total_decisions = 0
    total_executed = 0
    total_rejected = 0

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
                result = auto_trade_portfolio(
                    session, portfolio, AutoTradeConfig(),
                    now=now, as_of=as_of,
                )
                # Persist buy_skips for observability / alert classification
                if result.buy_skips:
                    SKIPS_DIR.mkdir(parents=True, exist_ok=True)
                    skip_date = (as_of or now.date()).isoformat()
                    path = SKIPS_DIR / f"{skip_date}.jsonl"
                    with path.open("a", encoding="utf-8") as f:
                        for s in result.buy_skips:
                            f.write(json.dumps({
                                "as_of_date": skip_date,
                                "portfolio_id": portfolio_id,
                                **s,
                            }) + "\n")
                # Anchor snapshot at 22:00 UTC on the date (end-of-session feel)
                snapshot_at = (
                    dt.datetime.combine(as_of, dt.time(22, 0), tzinfo=dt.timezone.utc)
                    if as_of is not None else now
                )
                snapshot_equity_now(session, portfolio, as_of=snapshot_at)
                session.commit()
                total_decisions += len(result.decisions)
                total_executed += len(result.executed)
                total_rejected += len(result.rejected)
                logger.info(
                    "paper_trading portfolio={} decisions={} executed={} rejected={}",
                    portfolio_id,
                    len(result.decisions),
                    len(result.executed),
                    len(result.rejected),
                )
        except Exception as exc:  # noqa: BLE001 — one portfolio must not kill the job
            logger.error("run_paper_trading failed for {}: {}", portfolio_id, exc)

    logger.info(
        "run_paper_trading complete: decisions={} executed={} rejected={}",
        total_decisions, total_executed, total_rejected,
    )
