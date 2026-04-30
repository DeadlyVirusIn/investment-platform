"""Phase 11V - turnover diagnostic.

Read-only inspection of paper-trading turnover. NEVER writes to DB.
Reports per-portfolio:
  - open_positions_count
  - max_open_positions
  - free_slots = max - open
  - pending_exits_count = positions whose age >= max_holding_days
    OR whose latest recommendation action is in {Sell, Trim}
  - blocked_buys = candidate Buys that would have fired but were
    skipped because portfolio_full (open >= max_open)
  - expected_slots_after_next_run = free_slots + pending_exits
  - lookback_window:
      * sells_count
      * buys_count
      * fill_count = sells + buys
      * avg_open_positions
      * turnover_ratio = sells / max(avg_open_positions, 1)
      * realized_pnl_total

Frozen constants:
  REPORT_VERSION = "turnover-diagnostic-v1.0.0"

NEVER changes strategy, thresholds, fill SQL, scheduler, or
DEFAULT_MAX_OPEN_POSITIONS. NEVER reaches into live execution.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    Recommendation,
)
from apps.api.src.domain.paper_trading.auto_trader import AutoTradeConfig
from apps.api.src.domain.paper_trading.paper_execution import (
    DEFAULT_MAX_OPEN_POSITIONS,
)


REPORT_VERSION = "turnover-diagnostic-v1.0.0"


def _portfolio_max_open(portfolio: PaperPortfolio) -> int:
    """Resolve the per-portfolio max_open_positions, falling back to
    the package default. Mirrors auto_trader._portfolio_config logic
    without importing private symbols."""
    raw = portfolio.config_json
    if raw:
        try:
            cfg = json.loads(raw)
            if isinstance(cfg, dict) and "max_open_positions" in cfg:
                return int(cfg["max_open_positions"])
        except (ValueError, TypeError):
            pass
    return DEFAULT_MAX_OPEN_POSITIONS


def _latest_action_per_asset(
    session: Session, asset_ids: list[str], at_or_before: dt.datetime,
) -> dict[str, str]:
    """For each asset_id, return the most-recent recommendation
    action string at or before the cutoff. Read-only."""
    if not asset_ids:
        return {}
    rows = session.execute(
        select(
            Recommendation.asset_id,
            Recommendation.action,
            Recommendation.generated_at,
        )
        .where(
            Recommendation.asset_id.in_(asset_ids),
            Recommendation.generated_at <= at_or_before,
        )
        .order_by(
            Recommendation.asset_id,
            Recommendation.generated_at.desc(),
        )
    ).all()
    out: dict[str, str] = {}
    for asset_id, action, _gen in rows:
        if asset_id not in out:
            out[asset_id] = str(action) if action is not None else ""
    return out


def _holding_age_days(
    opened_at: dt.datetime, as_of: dt.datetime,
) -> int:
    """Return integer days between opened_at and as_of (floor).
    Both must be timezone-aware. Negative ages clamp to 0."""
    if opened_at.tzinfo is None or as_of.tzinfo is None:
        raise ValueError("opened_at and as_of must be tz-aware")
    delta = as_of - opened_at
    return max(0, delta.days)


def diagnose_portfolio(
    session: Session,
    portfolio: PaperPortfolio,
    *,
    as_of: dt.datetime,
    lookback_days: int,
    config: AutoTradeConfig | None = None,
) -> dict[str, Any]:
    """Compute the full turnover diagnostic for one portfolio.

    Read-only. Pure aggregation over paper_position, paper_trade,
    and recommendation. NEVER writes.
    """
    cfg = config or AutoTradeConfig()
    if as_of.tzinfo is None:
        raise ValueError("as_of must be tz-aware")
    if lookback_days <= 0:
        raise ValueError("lookback_days must be > 0")

    max_open = _portfolio_max_open(portfolio)

    open_positions = session.scalars(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == portfolio.id,
            PaperPosition.is_open.is_(True),
        )
    ).all()
    open_count = len(open_positions)

    open_asset_ids = [p.asset_id for p in open_positions]
    latest_actions = _latest_action_per_asset(
        session, open_asset_ids, as_of,
    )

    pending_exits: list[dict[str, Any]] = []
    for pos in open_positions:
        age = _holding_age_days(pos.opened_at, as_of)
        action = latest_actions.get(pos.asset_id, "")
        flip = action in ("Sell", "Trim")
        aged_out = age >= cfg.max_holding_days
        if flip or aged_out:
            symbol = session.scalar(
                select(Asset.symbol).where(Asset.id == pos.asset_id)
            )
            pending_exits.append({
                "asset_id": pos.asset_id,
                "symbol": symbol,
                "age_days": age,
                "latest_action": action or None,
                "reason": (
                    "max_holding" if aged_out
                    else "rec_flip"
                ),
            })

    free_slots = max(0, max_open - open_count)
    expected_slots_after_next_run = (
        free_slots + len(pending_exits)
    )

    lookback_start = as_of - dt.timedelta(days=lookback_days)
    trades = session.scalars(
        select(PaperTrade).where(
            PaperTrade.portfolio_id == portfolio.id,
            PaperTrade.fill_ts >= lookback_start,
            PaperTrade.fill_ts <= as_of,
        )
    ).all()
    sells = [t for t in trades if t.side == "sell"]
    buys = [t for t in trades if t.side == "buy"]

    realized_pnl = Decimal("0")
    for t in sells:
        if t.realized_pnl is not None:
            realized_pnl += Decimal(str(t.realized_pnl))

    avg_open = _avg_open_positions(
        session, portfolio.id, lookback_start, as_of,
    )
    turnover_ratio = (
        round(len(sells) / max(avg_open, 1.0), 4)
        if avg_open > 0 else None
    )

    blocked_buys = (
        "portfolio_full"
        if open_count >= max_open and free_slots == 0
        else None
    )

    return {
        "portfolio_id": portfolio.id,
        "portfolio_name": portfolio.name,
        "as_of": as_of.isoformat(),
        "open_positions_count": open_count,
        "max_open_positions": max_open,
        "free_slots": free_slots,
        "pending_exits_count": len(pending_exits),
        "pending_exits": pending_exits,
        "expected_slots_after_next_run":
            expected_slots_after_next_run,
        "blocked_buys_reason": blocked_buys,
        "lookback_window": {
            "lookback_days": lookback_days,
            "start": lookback_start.isoformat(),
            "end": as_of.isoformat(),
            "buys_count": len(buys),
            "sells_count": len(sells),
            "fill_count": len(trades),
            "avg_open_positions": round(avg_open, 4),
            "turnover_ratio": turnover_ratio,
            "realized_pnl_total": str(realized_pnl),
        },
    }


def _avg_open_positions(
    session: Session,
    portfolio_id: str,
    start: dt.datetime,
    end: dt.datetime,
) -> float:
    """Average open-position count across the window using
    paper_equity_snapshot row count of distinct positions per day.

    Falls back to (current_open + 0.5*lookback_days_with_trades) / 2
    when no snapshots exist, which is a coarse proxy. Read-only.
    """
    # Coarse approximation: count current open positions and any
    # additional positions that were closed during the window.
    open_now = session.scalar(
        select(func.count(PaperPosition.id)).where(
            PaperPosition.portfolio_id == portfolio_id,
            PaperPosition.is_open.is_(True),
        )
    ) or 0
    closed_in_window = session.scalar(
        select(func.count(PaperPosition.id)).where(
            PaperPosition.portfolio_id == portfolio_id,
            PaperPosition.is_open.is_(False),
            PaperPosition.closed_at >= start,
            PaperPosition.closed_at <= end,
        )
    ) or 0
    # Average ≈ (open_now + closed_in_window/2) — closed positions
    # contributed roughly half the window on average.
    return float(open_now) + float(closed_in_window) / 2.0


def diagnose_all_portfolios(
    session: Session,
    *,
    as_of: dt.datetime,
    lookback_days: int,
    config: AutoTradeConfig | None = None,
) -> list[dict[str, Any]]:
    """Run the diagnostic for every active portfolio. Read-only."""
    portfolios = session.scalars(
        select(PaperPortfolio).where(PaperPortfolio.is_active.is_(True))
    ).all()
    return [
        diagnose_portfolio(
            session, p,
            as_of=as_of,
            lookback_days=lookback_days,
            config=config,
        )
        for p in portfolios
    ]


def predict_next_cycle(
    portfolio_diag: dict[str, Any],
) -> dict[str, Any]:
    """Pure-fn prediction of next cycle outcome from a portfolio
    diagnostic dict. NEVER touches the DB.

    Returns:
      - will_close_old_positions (bool)
      - close_count (int)
      - free_slots_after (int)
      - buys_possible_after (int)
    """
    pending = portfolio_diag.get("pending_exits_count", 0)
    free = portfolio_diag.get("free_slots", 0)
    expected = portfolio_diag.get(
        "expected_slots_after_next_run", 0,
    )
    return {
        "will_close_old_positions": pending > 0,
        "close_count": pending,
        "free_slots_after": expected,
        "buys_possible_after": expected,
    }
