"""Phase P6A — options canary lifecycle-check handler.

Gated on OPTIONS_CANARY_ENABLED (default false → fully inert; stops the
no-handler spam). When enabled it runs one ordered reconciliation pass per
active canary portfolio (heal orphan positions → drift / orphan-trade /
reserved-mismatch alerts).

P6B SEAM: MTM observation + exit-policy evaluation + release wiring plug into
run_lifecycle_cycle. P6A reconciles only — no exit decisions, no auto-close.
Paper-only. Handler-level best-effort lock skips overlapping runs.
"""

from __future__ import annotations

import datetime as dt

from loguru import logger
from sqlalchemy import text

_HANDLER_LOCK_NS = 4243
_LIFECYCLE_LOCK_KEY = 2


async def run_options_lifecycle_check() -> None:
    from apps.api.src.config import settings

    if not getattr(settings, "OPTIONS_CANARY_ENABLED", False):
        logger.info(
            "run_options_lifecycle_check: OPTIONS_CANARY_ENABLED=false — "
            "inert, skipping (no reconcile, no close)"
        )
        return

    from apps.api.src.db import SessionLocal
    from apps.api.src.options.canary import engine as canary_engine

    now = dt.datetime.now(dt.timezone.utc)

    lock_s = SessionLocal()
    try:
        got = lock_s.execute(
            text("SELECT pg_try_advisory_lock(:ns, :k)"),
            {"ns": _HANDLER_LOCK_NS, "k": _LIFECYCLE_LOCK_KEY},
        ).scalar()
        if not got:
            logger.warning(
                "run_options_lifecycle_check: another run holds the lock — skipping"
            )
            return

        with SessionLocal() as s:
            portfolio_ids = [
                r[0] for r in s.execute(text(
                    "SELECT id FROM options_paper_portfolio WHERE active = TRUE "
                    "ORDER BY created_at"
                )).all()
            ]

        for pid in portfolio_ids:
            try:
                report = canary_engine.run_lifecycle_cycle(
                    portfolio_id=pid, now=now, heal=True,
                )
                if not report.clean or report.orphan_positions_healed:
                    logger.warning(
                        "lifecycle reconcile pid={}: healed={} orphan_trades={} "
                        "drift={} reserved_mismatch={}",
                        pid, report.orphan_positions_healed,
                        report.orphan_trades, report.cash_drift,
                        report.reserved_mismatch,
                    )
            except Exception as exc:   # noqa: BLE001
                logger.error("lifecycle cycle failed pid={}: {}", pid, exc)

        logger.info(
            "run_options_lifecycle_check complete: portfolios={}",
            len(portfolio_ids),
        )
    finally:
        try:
            lock_s.execute(
                text("SELECT pg_advisory_unlock(:ns, :k)"),
                {"ns": _HANDLER_LOCK_NS, "k": _LIFECYCLE_LOCK_KEY},
            )
        except Exception:   # noqa: BLE001
            pass
        lock_s.close()
