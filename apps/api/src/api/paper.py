"""Paper-trading API — portfolio CRUD, trade submission, equity + trade log."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.auth.identity import resolve_identity
from apps.api.src.api.admin_guard import _email_and_role, is_owner
from apps.api.src.domain.paper_trading.paper_execution import (
    PaperTradeRejected,
    submit_trade,
)
from apps.api.src.domain.paper_trading.paper_service import (
    PortfolioCreate,
    TradeRequest,
    compute_confidence_validation,
    compute_equity_breakdown,
    compute_paper_max_drawdown,
    create_portfolio,
    get_equity_curve,
    get_portfolio,
    list_open_positions,
    list_portfolios,
    list_trades,
    is_user_paper_book,
    public_book_label,
    resolve_asset_id,
    snapshot_equity_now,
    trade_counts,
    user_stock_portfolio_name,
)

router = APIRouter(prefix="/paper", tags=["paper-trading"])


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, dict):
        return {k: _jsonable(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


def _request_is_owner(request: Request, session: Session) -> bool:
    """Use the admin guard ownership predicate without exposing a 403."""
    uid = resolve_identity(request, session)
    if not uid:
        return False
    email, role = _email_and_role(session, uid)
    return role == "owner" or is_owner(email)


def _require_portfolio_access(
    request: Request,
    session: Session,
    portfolio_id: str,
    *,
    write: bool,
):
    """Return an authorized portfolio; denied books are always hidden as 404."""
    portfolio = get_portfolio(session, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    uid = resolve_identity(request, session)
    if not uid:
        raise HTTPException(status_code=404)
    if _request_is_owner(request, session):
        return portfolio
    own_book = user_stock_portfolio_name(uid)
    allowed = portfolio.name == own_book if write else (
        not is_user_paper_book(portfolio.name) or portfolio.name == own_book
    )
    if not allowed:
        raise HTTPException(status_code=404)
    return portfolio


def _require_owner(request: Request, session: Session) -> None:
    if not _request_is_owner(request, session):
        raise HTTPException(status_code=404)


def _portfolio_summary(
    portfolio, breakdown: dict[str, Any], *, request_is_owner: bool
) -> dict[str, Any]:
    return {
        "id": portfolio.id,
        "name": public_book_label(portfolio.name, is_owner=request_is_owner),
        "starting_cash": portfolio.starting_cash,
        "cash": breakdown["cash"],
        "positions_value": breakdown["positions_value"],
        "total_equity": breakdown["total_equity"],
        "unrealized_pnl": breakdown["unrealized_pnl"],
        "realized_pnl_cumulative": breakdown["realized_pnl_cumulative"],
        "total_return_pct": (
            (breakdown["total_equity"] / Decimal(str(portfolio.starting_cash)) - Decimal("1"))
            if portfolio.starting_cash else None
        ),
        "is_active": portfolio.is_active,
        "created_at": portfolio.created_at.isoformat() if portfolio.created_at else None,
    }


@router.get("/portfolios")
def get_portfolios(
    request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _require_owner(request, session)
    portfolios = list_portfolios(session)
    out = []
    for p in portfolios:
        breakdown = compute_equity_breakdown(session, p)
        out.append(_portfolio_summary(p, breakdown, request_is_owner=True))
    return _jsonable({"portfolios": out, "count": len(out)})


@router.post("/portfolios", status_code=201)
def post_portfolio(
    payload: PortfolioCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_owner(request, session)
    try:
        portfolio = create_portfolio(session, payload)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    breakdown = compute_equity_breakdown(session, portfolio)
    return _jsonable(_portfolio_summary(portfolio, breakdown, request_is_owner=True))


@router.get("/portfolios/{portfolio_id}")
def get_portfolio_detail(
    portfolio_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    portfolio = _require_portfolio_access(request, session, portfolio_id, write=False)
    breakdown = compute_equity_breakdown(session, portfolio)
    counts = trade_counts(session, portfolio_id)
    positions = list_open_positions(session, portfolio_id)
    snapshots = get_equity_curve(session, portfolio_id)
    drawdown = compute_paper_max_drawdown(snapshots)
    conf_validation = compute_confidence_validation(session, portfolio_id)
    return _jsonable({
        **_portfolio_summary(
            portfolio, breakdown, request_is_owner=_request_is_owner(request, session)
        ),
        "open_positions": positions,
        "trade_counts": counts,
        "validation": {
            "drawdown": drawdown,
            "confidence_validation": conf_validation,
        },
    })


@router.post("/portfolios/{portfolio_id}/trade", status_code=201)
def post_trade(
    portfolio_id: str,
    payload: TradeRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_portfolio_access(request, session, portfolio_id, write=True)
    try:
        asset_id = resolve_asset_id(session, payload.asset_id, payload.symbol)
        result = submit_trade(
            session,
            portfolio_id=portfolio_id,
            asset_id=asset_id,
            side=payload.side,
            quantity=payload.quantity,
            usd_amount=payload.usd_amount,
            submitted_at=payload.submitted_at,
            reason=payload.reason,
            recommendation_id=payload.recommendation_id,
        )
    except (ValueError, PaperTradeRejected) as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return _jsonable({
        "trade_id": result.trade_id,
        "side": result.side,
        "quantity": result.quantity,
        "fill_price": result.fill_price,
        "fill_ts": result.fill_ts.isoformat(),
        "cash_after": result.cash_after,
        "realized_pnl": result.realized_pnl,
    })


@router.get("/portfolios/{portfolio_id}/trades")
def get_trades(
    portfolio_id: str,
    request: Request,
    limit: int = 500,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_portfolio_access(request, session, portfolio_id, write=False)
    trades = list_trades(session, portfolio_id, limit=limit)
    counts = trade_counts(session, portfolio_id)
    return _jsonable({"trades": trades, "count": len(trades), "counts": counts})


@router.get("/portfolios/{portfolio_id}/equity")
def get_equity(
    portfolio_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    portfolio = _require_portfolio_access(request, session, portfolio_id, write=False)
    breakdown = compute_equity_breakdown(session, portfolio)
    snapshots = get_equity_curve(session, portfolio_id)
    return _jsonable({
        "current": breakdown,
        "curve": [{
            "snapshot_date": s.snapshot_date.isoformat() if s.snapshot_date else None,
            "cash": s.cash,
            "positions_value": s.positions_value,
            "total_equity": s.total_equity,
            "unrealized_pnl": s.unrealized_pnl,
            "realized_pnl_cumulative": s.realized_pnl_cumulative,
        } for s in snapshots],
    })


@router.post("/portfolios/{portfolio_id}/snapshot", status_code=201)
def post_snapshot(
    portfolio_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    portfolio = _require_portfolio_access(request, session, portfolio_id, write=True)
    # Phase L M079: operator-triggered snapshot via API → operator_manual.
    snap = snapshot_equity_now(session, portfolio, source="operator_manual")
    session.commit()
    return _jsonable({
        "snapshot_id": snap.id,
        "snapshot_date": snap.snapshot_date.isoformat(),
        "total_equity": snap.total_equity,
    })