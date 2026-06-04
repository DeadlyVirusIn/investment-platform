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

    # GATE SPLIT (P6B.0): the lifecycle path manages EXISTING open positions
    # regardless of OPTIONS_CANARY_ENABLED — the gate controls promotion only,
    # so disabling it never freezes an open position's wind-down. With 0 open
    # positions (the P6A/P6B.0 baseline) this is a reconcile-only no-op.
    gate = getattr(settings, "OPTIONS_CANARY_ENABLED", False)
    logger.info(
        "run_options_lifecycle_check: gate(promotion)={} — managing existing "
        "open positions regardless", gate,
    )

    from apps.api.src.db import SessionLocal
    from apps.api.src.options.canary import engine as canary_engine
    from apps.api.src.options.canary import reconcile

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
                    "SELECT DISTINCT portfolio_id FROM options_paper_position "
                    "WHERE released_at IS NULL"
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

        if not portfolio_ids:
            # No open positions → still reconcile globally to surface orphans.
            with SessionLocal() as s:
                rep = reconcile.run(s, now=now, heal=True)
                s.commit()
            if not rep.clean or rep.orphan_positions_healed:
                logger.warning(
                    "lifecycle global reconcile: healed={} orphan_trades={} "
                    "drift={} reserved_mismatch={}",
                    rep.orphan_positions_healed, rep.orphan_trades,
                    rep.cash_drift, rep.reserved_mismatch,
                )

        logger.info(
            "run_options_lifecycle_check complete: managed_portfolios={}",
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
