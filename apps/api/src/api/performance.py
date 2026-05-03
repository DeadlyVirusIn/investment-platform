"""Performance API — tiered report: core + conditional + experimental."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    Asset,
    Recommendation,
    RecommendationOutcome,
)
from apps.api.src.domain.performance.paper_performance import (
    compute_paper_metrics,
    equity_curve_points,
    resolve_default_portfolio_id,
)
from apps.api.src.domain.performance.report import OutcomeRecord, compute_report

router = APIRouter(prefix="/performance", tags=["performance"])

Window = Literal["30d", "90d"]


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, dict):
        return {k: _jsonable(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


def _to_records(
    rows: list[tuple[RecommendationOutcome, Recommendation, str]],
    window: Window,
) -> list[OutcomeRecord]:
    attr = "realized_30d_return" if window == "30d" else "realized_90d_return"
    out: list[OutcomeRecord] = []
    for outcome, rec, symbol in rows:
        raw = getattr(outcome, attr)
        ret: Decimal | None
        if raw is None:
            ret = None
        elif isinstance(raw, Decimal):
            ret = raw
        else:
            ret = Decimal(str(raw))
        conf: Decimal | None
        if rec.conviction is None:
            conf = None
        elif isinstance(rec.conviction, Decimal):
            conf = rec.conviction
        else:
            conf = Decimal(str(rec.conviction))
        out.append(OutcomeRecord(
            generated_at_iso=rec.generated_at.isoformat() if rec.generated_at else "",
            symbol=symbol,
            asset_id=rec.asset_id,
            confidence=conf,
            return_value=ret,
            label=outcome.barrier_label,
            trend_regime=outcome.trend_regime,
            volatility_regime=outcome.volatility_regime,
            drawdown_regime=outcome.drawdown_regime,
        ))
    return out


@router.get("")
def get_performance(
    window: Window = Query("30d"),
    limit: int = Query(500, ge=1, le=5000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt = (
        select(RecommendationOutcome, Recommendation, Asset.symbol)
        .join(Recommendation, RecommendationOutcome.recommendation_id == Recommendation.id)
        .join(Asset, Recommendation.asset_id == Asset.id)
        .order_by(Recommendation.generated_at.asc())
        .limit(limit)
    )
    rows = list(session.execute(stmt).all())

    records_30 = _to_records(rows, "30d")
    records_90 = _to_records(rows, "90d")

    report_30 = compute_report(records_30, annualization=12)
    report_90 = compute_report(records_90, annualization=4)
    active_report = report_30 if window == "30d" else report_90

    outcomes_payload: list[dict[str, Any]] = []
    for outcome, rec, symbol in rows:
        outcomes_payload.append({
            "recommendation_id": rec.id,
            "asset_id": rec.asset_id,
            "symbol": symbol,
            "action": rec.action,
            "confidence": rec.conviction,
            "generated_at": rec.generated_at.isoformat() if rec.generated_at else None,
            "price_at_recommendation": outcome.price_at_recommendation,
            "price_after_30d": outcome.price_after_30d,
            "price_after_90d": outcome.price_after_90d,
            "realized_30d_return": outcome.realized_30d_return,
            "realized_90d_return": outcome.realized_90d_return,
            "barrier_label": outcome.barrier_label,
            "barrier_first_touch_at": (
                outcome.barrier_first_touch_at.isoformat()
                if outcome.barrier_first_touch_at else None
            ),
            "trend_regime": outcome.trend_regime,
            "volatility_regime": outcome.volatility_regime,
            "drawdown_regime": outcome.drawdown_regime,
        })

    return _jsonable({
        "window": window,
        "recommendation_metrics": active_report["recommendation_metrics"],
        "experimental_metrics": active_report["experimental_metrics"],
        "breakdown_by_window": {
            "30d": report_30,
            "90d": report_90,
        },
        "outcomes": outcomes_payload,
    })


# ---------------------------------------------------------------------------
# Paper trading performance — practical metrics from paper portfolio
# ---------------------------------------------------------------------------


@router.get("/summary")
def get_paper_summary(
    portfolio_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    pid = portfolio_id or resolve_default_portfolio_id(session)
    if pid is None:
        return {
            "portfolio_id": None,
            "total_return": None,
            "max_drawdown": None,
            "hit_rate": None,
            "expectancy": None,
            "profit_factor": None,
            "sharpe": None,
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "breakeven": 0,
            "empty_state": True,
        }

    m = compute_paper_metrics(session, pid)
    return _jsonable({
        "portfolio_id": pid,
        "total_return": m.total_return,
        "max_drawdown": m.max_drawdown,
        "hit_rate": m.hit_rate,
        "expectancy": m.expectancy,
        "profit_factor": m.profit_factor,
        "sharpe": m.sharpe,
        "trades": m.trades,
        "wins": m.wins,
        "losses": m.losses,
        "breakeven": m.breakeven,
        "empty_state": m.trades == 0,
    })


@router.get("/equity-curve")
def get_equity_curve(
    portfolio_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    pid = portfolio_id or resolve_default_portfolio_id(session)
    if pid is None:
        return {"portfolio_id": None, "points": []}

    points = equity_curve_points(session, pid)
    return _jsonable({
        "portfolio_id": pid,
        "points": [
            {"date": p.date.isoformat(), "equity": p.equity}
            for p in points
        ],
    })
