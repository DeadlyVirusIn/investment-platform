"""Walk-forward validation API."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.backtest.walk_forward import (
    DEFAULT_STEP_DAYS,
    DEFAULT_TEST_DAYS,
    DEFAULT_TRAIN_DAYS,
    SplitResult,
    WalkForwardReport,
    WindowMetrics,
    load_outcome_rows,
    run_walk_forward,
)

router = APIRouter(prefix="/backtest", tags=["backtest"])


def _dec(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


def _window_dict(m: WindowMetrics) -> dict[str, Any]:
    return {
        "count": m.count,
        "wins": m.wins,
        "losses": m.losses,
        "breakeven": m.breakeven,
        "total_return_proxy": _dec(m.total_return_proxy),
        "hit_rate": _dec(m.hit_rate),
        "expectancy": _dec(m.expectancy),
        "profit_factor": _dec(m.profit_factor),
        "sharpe": _dec(m.sharpe),
    }


def _split_dict(s: SplitResult) -> dict[str, Any]:
    return {
        "index": s.index,
        "train_start": s.window.train_start.isoformat(),
        "train_end": s.window.train_end.isoformat(),
        "test_start": s.window.test_start.isoformat(),
        "test_end": s.window.test_end.isoformat(),
        "is_metrics": _window_dict(s.is_metrics),
        "oos_metrics": _window_dict(s.oos_metrics),
        "wfe": _dec(s.wfe),
        "stability": s.stability,
        "notes": s.notes,
    }


def _report_dict(r: WalkForwardReport) -> dict[str, Any]:
    return {
        "config": r.config,
        "stratified_by": r.stratified_by,
        "splits": [_split_dict(s) for s in r.splits],
        "aggregate_wfe": _dec(r.aggregate_wfe),
        "aggregate_stability": r.aggregate_stability,
        "split_count": len(r.splits),
    }


@router.get("/walk-forward/summary")
def walk_forward_summary(
    train_days: int = Query(DEFAULT_TRAIN_DAYS, ge=1, le=3650),
    test_days: int = Query(DEFAULT_TEST_DAYS, ge=1, le=3650),
    step_days: int = Query(DEFAULT_STEP_DAYS, ge=1, le=3650),
    signal_type: str | None = Query(None, pattern=r"^(trend|mean_reversion|default)$"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = load_outcome_rows(session)
    report = run_walk_forward(
        rows,
        train_days=train_days,
        test_days=test_days,
        step_days=step_days,
        signal_type=signal_type,
    )
    return _report_dict(report)
