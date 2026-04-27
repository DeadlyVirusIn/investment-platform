"""Read-only Options FastAPI router (Phase 11F).

ALL endpoints are GET. The module is statically scanned by tests for the
absence of POST/PUT/PATCH/DELETE decorators. There is intentionally no
mutation surface here.

NEVER imports V2 / equity / governance / ML / paper engine internals.
The only imports allowed are from `apps.api.src.options.service_readonly`
plus FastAPI + db.get_session.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.options import service_readonly as svc


router = APIRouter(prefix="/options", tags=["options"])


PAPER_ONLY_NOTICE = "Options are paper-trading only"


@router.get("/health")
def options_health() -> dict[str, Any]:
    """Lightweight metadata endpoint — used by the WebUI banner."""
    return {
        "status": "ok",
        "paper_only": True,
        "ml_can_affect_trades": False,
        "notice": PAPER_ONLY_NOTICE,
    }


@router.get("/symbols")
def get_symbols(session: Session = Depends(get_session)) -> dict[str, Any]:
    return {
        "notice": PAPER_ONLY_NOTICE,
        "symbols": svc.list_symbols(session),
    }


@router.get("/expiries")
def get_expiries(
    symbol: str = Query(..., min_length=1, max_length=12),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return {
        "notice": PAPER_ONLY_NOTICE,
        "symbol": symbol,
        "expiries": svc.list_expiries(session, symbol=symbol),
    }


@router.get("/chain")
def get_chain(
    symbol: str = Query(..., min_length=1, max_length=12),
    expiry: str = Query(..., min_length=10, max_length=10),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = svc.get_chain(session, symbol=symbol, expiry=expiry)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/features")
def get_features(
    symbol: str = Query(..., min_length=1, max_length=12),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = svc.get_latest_features(session, symbol=symbol)
    return {
        "notice": PAPER_ONLY_NOTICE,
        "symbol": symbol,
        "features": row,        # may be None when not yet computed
        "gamma_exposure_label": (
            "Naive gamma exposure proxy — not dealer GEX"
        ),
    }


@router.get("/paper-trades")
def list_paper_trades(
    status: str | None = Query(default=None, max_length=24),
    underlying: str | None = Query(default=None, max_length=12),
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    trades = svc.list_paper_trades(
        session, status=status, underlying=underlying, limit=limit,
    )
    return {
        "notice": PAPER_ONLY_NOTICE,
        "count": len(trades),
        "trades": trades,
    }


@router.get("/paper-trades/{trade_id}")
def get_paper_trade(
    trade_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    detail = svc.get_trade_detail(session, trade_id=trade_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="trade not found")
    detail["notice"] = PAPER_ONLY_NOTICE
    return detail


@router.get("/risk-summary")
def get_risk_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    summary = svc.get_risk_summary(session)
    summary["notice"] = PAPER_ONLY_NOTICE
    return summary
