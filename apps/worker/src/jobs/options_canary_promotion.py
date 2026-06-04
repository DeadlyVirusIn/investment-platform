"""Phase P6A — options canary promotion handler.

Gated on OPTIONS_CANARY_ENABLED (default false → fully inert; this only stops
the no-handler spam). When enabled it runs one promotion cycle per active
canary portfolio. P6A keeps promotion inert: the candidate seam returns []
so NOTHING is auto-opened even if the gate is flipped. Paper-only.

Concurrency: a best-effort handler-level pg_try_advisory_lock (held on its
own connection for the whole run) skips overlapping executions; correctness
still rests on the per-portfolio xact lock inside the cycle.
"""

from __future__ import annotations

import datetime as dt

from loguru import logger
from sqlalchemy import text

# Dedicated namespace for handler-level (coarse) advisory locks — separate
# from positions.ADVISORY_NS (per-portfolio) to avoid key overlap.
_HANDLER_LOCK_NS = 4243
_PROMOTION_LOCK_KEY = 1


async def run_options_canary_promotion() -> None:
    from apps.api.src.config import settings

    if not getattr(settings, "OPTIONS_CANARY_ENABLED", False):
        logger.info(
            "run_options_canary_promotion: OPTIONS_CANARY_ENABLED=false — "
            "inert, skipping (no positions opened)"
        )
        return

    from apps.api.src.db import SessionLocal
    from apps.api.src.options.canary import engine as canary_engine

    now = dt.datetime.now(dt.timezone.utc)
    run_date = now.date()    # logical job date, pinned once for this run

    lock_s = SessionLocal()
    try:
        got = lock_s.execute(
            text("SELECT pg_try_advisory_lock(:ns, :k)"),
            {"ns": _HANDLER_LOCK_NS, "k": _PROMOTION_LOCK_KEY},
        ).scalar()
        if not got:
            logger.warning(
                "run_options_canary_promotion: another run holds the lock — skipping"
            )
            return

        with SessionLocal() as s:
            portfolio_ids = [
                r[0] for r in s.execute(text(
                    "SELECT id FROM options_paper_portfolio WHERE active = TRUE "
                    "ORDER BY created_at"
                )).all()
            ]

        promoted_total = 0
        for pid in portfolio_ids:
            try:
                counts = canary_engine.run_promotion_cycle(
                    portfolio_id=pid, run_date=run_date, now=now,
                )
                promoted_total += counts.promoted
            except Exception as exc:   # noqa: BLE001
                logger.error("promotion cycle failed pid={}: {}", pid, exc)

        logger.info(
            "run_options_canary_promotion complete: portfolios={} promoted={}",
            len(portfolio_ids), promoted_total,
        )
    finally:
        try:
            lock_s.execute(
                text("SELECT pg_advisory_unlock(:ns, :k)"),
                {"ns": _HANDLER_LOCK_NS, "k": _PROMOTION_LOCK_KEY},
            )
        except Exception:   # noqa: BLE001
            pass
        lock_s.close()
