"""Canonical practice-portfolio endpoints (Phase A).

GET /api/paper/canonical/stock — the ONE canonical stock practice
portfolio (settings.CANONICAL_STOCK_PORTFOLIO_ID). No aggregation across
active portfolios; test/demo fixtures are never included. M079 invariant:
only paper_equity_snapshot rows with source='live' are read.

Read-only. No writes, no migration.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import get_session

# Reuse the freshness SLA classifier so the portfolio freshness band
# matches the rest of the product (intraday vs overnight tiers).
from apps.api.src.api.freshness import (
    _classify_portfolio,
    _hours_since,
    _is_market_hours,
    _now_utc,
)

router = APIRouter(prefix="/paper/canonical", tags=["paper-canonical"])


def _iso(ts: dt.datetime | dt.date | None) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, dt.datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        return ts.isoformat()
    return ts.isoformat()


@router.get("/stock")
def canonical_stock(
    request: Request,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Canonical stock practice book. M1: identity resolves from the session
    cookie (authenticated user) or, only in demo/dev mode, the X-Auth-User-Id
    device header. Resolved identity -> the caller's own ``user:<id>:stock``
    book; truly anonymous callers fall back to the shared demo portfolio. A
    spoofed device header outside demo mode yields anonymous, never a targeted
    user's book."""
    from apps.api.src.auth.identity import resolve_identity
    from apps.api.src.domain.paper_trading.paper_service import (
        resolve_user_stock_portfolio,
    )
    uid = resolve_identity(request, db)
    if uid:
        # Per-user isolation: get-or-create THIS user's OWN book via the single
        # shared resolver. A cold user gets a fresh EMPTY book — it must NEVER
        # fall back to the shared demo/Replay-Recovery portfolio.
        pid = resolve_user_stock_portfolio(db, uid)
        db.commit()
    else:
        # Truly anonymous callers only → shared demo portfolio.
        pid = settings.CANONICAL_STOCK_PORTFOLIO_ID
    now = _now_utc()

    portfolio = db.execute(
        text("SELECT name, starting_cash FROM paper_portfolio WHERE id = :pid"),
        {"pid": pid},
    ).first()

    # Latest live snapshot for THIS portfolio only (M079: source='live').
    snap = db.execute(
        text("""
            SELECT id, snapshot_date, total_equity, cash, positions_value,
                   unrealized_pnl, realized_pnl_cumulative, recorded_at
            FROM paper_equity_snapshot
            WHERE portfolio_id = :pid AND source = 'live'
            ORDER BY snapshot_date DESC, recorded_at DESC, id DESC
            LIMIT 1
        """),
        {"pid": pid},
    ).first()

    open_positions = db.execute(
        text("""
            SELECT count(*) FROM paper_position
            WHERE portfolio_id = :pid AND is_open = TRUE
        """),
        {"pid": pid},
    ).scalar() or 0

    if portfolio is None or snap is None:
        # Honest empty contract — never fabricate. Portfolio missing or no
        # live snapshot yet.
        return {
            "portfolio_id": pid,
            "name": portfolio.name if portfolio is not None else None,
            "nav": None, "cash": None, "positions_value": None,
            "realized_pnl": None, "unrealized_pnl": None, "daily_pnl": None,
            "daily_pnl_prior_snapshot_date": None,
            "starting_capital": (
                float(portfolio.starting_cash) if portfolio is not None else None
            ),
            "total_return_pct": None,
            "open_positions_count": int(open_positions),
            "as_of": None,
            "freshness": "unknown",
            "source_snapshot_id": None,
            "source": "live",
            "status": "no_live_snapshot",
        }

    nav = float(snap.total_equity)
    starting = float(portfolio.starting_cash or 0)
    as_of = snap.snapshot_date

    # Daily P&L = nav - prior live snapshot's nav (this portfolio only).
    prev_row = db.execute(
        text("""
            SELECT total_equity, snapshot_date FROM paper_equity_snapshot
            WHERE portfolio_id = :pid AND source = 'live'
              AND snapshot_date < :as_of
            ORDER BY snapshot_date DESC, recorded_at DESC, id DESC
            LIMIT 1
        """),
        {"pid": pid, "as_of": as_of},
    ).first()
    daily_pnl = (
        (nav - float(prev_row.total_equity)) if prev_row is not None else None
    )
    # The date daily_pnl is measured against. Snapshots can be sparse, so this
    # delta may span >1 day — expose the basis date so the UI labels it
    # honestly ("since <date>") rather than implying a same-day mark-to-market.
    daily_pnl_prior_snapshot_date = (
        prev_row.snapshot_date if prev_row is not None else None
    )

    total_return_pct = (
        ((nav - starting) / starting) * 100.0 if starting > 0 else None
    )

    # RC3: freshness measured from recorded_at (the actual valuation
    # instant), not snapshot_date promoted to midnight (which inflated
    # age by up to +24h). `as_of` below still reports the trading date
    # for display — only the staleness math changes.
    hours = _hours_since(snap.recorded_at)
    freshness = _classify_portfolio(hours, _is_market_hours(now))

    return {
        "portfolio_id": pid,
        "name": portfolio.name,
        "nav": nav,
        "cash": float(snap.cash),
        "positions_value": float(snap.positions_value),
        "realized_pnl": float(snap.realized_pnl_cumulative or 0),
        "unrealized_pnl": float(snap.unrealized_pnl or 0),
        "daily_pnl": daily_pnl,
        "daily_pnl_prior_snapshot_date": _iso(daily_pnl_prior_snapshot_date),
        "starting_capital": starting,
        "total_return_pct": total_return_pct,
        "open_positions_count": int(open_positions),
        "as_of": _iso(as_of),
        "freshness": freshness,
        "source_snapshot_id": str(snap.id),
        "source": "live",
        "status": "live",
    }
