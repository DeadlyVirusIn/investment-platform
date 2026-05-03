"""PnL + attribution endpoints. Read-only."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.diagnostics.csv_tools import rows_to_csv
from apps.api.src.domain.pnl.attribution import (
    DEFAULT_BLOCKED_HORIZON_DAYS,
    DEFAULT_BLOCKED_MIN_SCORE,
    attribution_by_regime,
    attribution_by_score_bucket,
    blocked_alpha_sim,
)
from apps.api.src.domain.pnl.engine import (
    per_symbol_pnl,
    portfolio_pnl,
    resolve_portfolio,
)

router = APIRouter(prefix="/pnl", tags=["pnl"])


def _dec(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


def _require_portfolio(session: Session, portfolio_id: str | None):
    p = resolve_portfolio(session, portfolio_id)
    if p is None:
        raise HTTPException(status_code=404, detail="no active paper portfolio")
    return p


@router.get("/summary")
def get_pnl_summary(
    portfolio_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    portfolio = _require_portfolio(session, portfolio_id)
    pnl = portfolio_pnl(session, portfolio)
    return {
        "as_of_date": dt.date.today().isoformat(),
        "portfolio_id": pnl.portfolio_id,
        "starting_cash": _dec(pnl.starting_cash),
        "cash": _dec(pnl.cash),
        "invested": _dec(pnl.invested),
        "nav": _dec(pnl.nav),
        "cumulative_pnl": _dec(pnl.cumulative_pnl),
        "daily_pnl": _dec(pnl.daily_pnl),
        "realized_pnl": _dec(pnl.realized_pnl),
        "unrealized_pnl": _dec(pnl.unrealized_pnl),
        "open_positions": pnl.open_positions_count,
        "closed_trades": pnl.closed_trade_count,
        "wins": pnl.wins, "losses": pnl.losses, "breakeven": pnl.breakeven,
        "win_rate": _dec(pnl.win_rate),
        "avg_win": _dec(pnl.avg_win),
        "avg_loss": _dec(pnl.avg_loss),
    }


_SYMBOL_CSV_COLUMNS = (
    "symbol", "asset_id", "status", "quantity", "avg_cost", "mark",
    "realized_pnl", "unrealized_pnl", "total_pnl", "holding_days",
    "entry_composite_score", "entry_confidence",
    "entry_market_trend", "entry_vol_regime",
)


@router.get("/by-symbol")
def get_pnl_by_symbol(
    portfolio_id: str | None = Query(None),
    format: str = Query("json", pattern="^(json|csv)$"),
    session: Session = Depends(get_session),
) -> Any:
    portfolio = _require_portfolio(session, portfolio_id)
    rows = per_symbol_pnl(session, portfolio)
    items = [
        {
            "asset_id": r.asset_id,
            "symbol": r.symbol,
            "status": r.status,
            "quantity": _dec(r.quantity),
            "avg_cost": _dec(r.avg_cost),
            "mark": _dec(r.mark),
            "realized_pnl": _dec(r.realized_pnl),
            "unrealized_pnl": _dec(r.unrealized_pnl),
            "total_pnl": _dec(r.total_pnl),
            "holding_days": r.holding_days,
            "entry_composite_score": _dec(r.entry_composite_score),
            "entry_confidence": _dec(r.entry_confidence),
            "entry_market_trend": r.entry_market_trend,
            "entry_vol_regime": r.entry_vol_regime,
        }
        for r in rows
    ]
    if format == "csv":
        body = rows_to_csv(items, _SYMBOL_CSV_COLUMNS)
        return Response(content=body, media_type="text/csv")
    return {
        "portfolio_id": portfolio.id,
        "count": len(rows),
        "items": items,
    }


_BUCKET_CSV_COLUMNS = (
    "bucket", "trade_count", "wins",
    "realized_pnl", "unrealized_pnl", "total_pnl", "avg_pnl_per_trade",
)


@router.get("/by-score-bucket")
def get_pnl_by_score_bucket(
    portfolio_id: str | None = Query(None),
    format: str = Query("json", pattern="^(json|csv)$"),
    session: Session = Depends(get_session),
) -> Any:
    portfolio = _require_portfolio(session, portfolio_id)
    buckets = attribution_by_score_bucket(session, portfolio)
    items = [
        {
            "bucket": b.bucket,
            "trade_count": b.trade_count,
            "wins": b.wins,
            "realized_pnl": _dec(b.realized_pnl),
            "unrealized_pnl": _dec(b.unrealized_pnl),
            "total_pnl": _dec(b.total_pnl),
            "avg_pnl_per_trade": _dec(b.avg_pnl_per_trade),
        }
        for b in buckets
    ]
    if format == "csv":
        body = rows_to_csv(items, _BUCKET_CSV_COLUMNS)
        return Response(content=body, media_type="text/csv")
    return {
        "portfolio_id": portfolio.id,
        "buckets": items,
    }


_REGIME_CSV_COLUMNS = (
    "market_trend", "vol_regime", "trade_count",
    "realized_pnl", "unrealized_pnl", "total_pnl", "avg_pnl_per_trade",
)


@router.get("/by-regime")
def get_pnl_by_regime(
    portfolio_id: str | None = Query(None),
    format: str = Query("json", pattern="^(json|csv)$"),
    session: Session = Depends(get_session),
) -> Any:
    portfolio = _require_portfolio(session, portfolio_id)
    stats = attribution_by_regime(session, portfolio)
    items = [
        {
            "market_trend": s.market_trend,
            "vol_regime": s.vol_regime,
            "trade_count": s.trade_count,
            "realized_pnl": _dec(s.realized_pnl),
            "unrealized_pnl": _dec(s.unrealized_pnl),
            "total_pnl": _dec(s.total_pnl),
            "avg_pnl_per_trade": _dec(s.avg_pnl_per_trade),
        }
        for s in stats
    ]
    if format == "csv":
        body = rows_to_csv(items, _REGIME_CSV_COLUMNS)
        return Response(content=body, media_type="text/csv")
    return {
        "portfolio_id": portfolio.id,
        "regimes": items,
    }


@router.get("/blocked-alpha-sim")
def get_blocked_alpha_sim(
    min_score: float = Query(float(DEFAULT_BLOCKED_MIN_SCORE), ge=-1.0, le=1.0),
    horizon_days: int = Query(DEFAULT_BLOCKED_HORIZON_DAYS, ge=1, le=365),
    from_date: dt.date | None = Query(None, alias="from"),
    to_date: dt.date | None = Query(None, alias="to"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    report = blocked_alpha_sim(
        session,
        min_score=Decimal(str(min_score)),
        horizon_days=horizon_days,
        from_date=from_date, to_date=to_date,
    )
    return {
        "min_score": _dec(report.min_score),
        "horizon_days": report.horizon_days,
        "from": report.from_date.isoformat(),
        "to": report.to_date.isoformat(),
        "simulated_count": report.simulated_count,
        "skipped_count": report.skipped_count,
        "avg_return": _dec(report.avg_return),
        "total_return": _dec(report.total_return),
        "wins": report.wins, "losses": report.losses,
        "win_rate": _dec(report.win_rate),
        "top_winners": [
            {
                "symbol": s.symbol, "as_of_date": s.as_of_date.isoformat(),
                "entry_date": s.entry_date.isoformat() if s.entry_date else None,
                "exit_date": s.exit_date.isoformat() if s.exit_date else None,
                "return_pct": _dec(s.return_pct),
                "rejection_reason": s.rejection_reason,
                "composite_score": _dec(s.composite_score),
            }
            for s in report.top_winners
        ],
        "top_losers": [
            {
                "symbol": s.symbol, "as_of_date": s.as_of_date.isoformat(),
                "entry_date": s.entry_date.isoformat() if s.entry_date else None,
                "exit_date": s.exit_date.isoformat() if s.exit_date else None,
                "return_pct": _dec(s.return_pct),
                "rejection_reason": s.rejection_reason,
                "composite_score": _dec(s.composite_score),
            }
            for s in report.top_losers
        ],
    }
