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
from apps.api.src.options.observatory import diagnostics as obs_diagnostics
from apps.api.src.options.observatory import observations as obs_observations
from apps.api.src.options.observatory import performance as obs_performance
from apps.api.src.options.observatory import replay as obs_replay
from apps.api.src.options.observatory import rules as obs_rules
from apps.api.src.options.evaluation import score_service as eval_service
from apps.api.src.options.decision_support import diagnostics as ds_diagnostics
from apps.api.src.options.decision_support import review_queue as ds_review_queue


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


# ---------------------------------------------------------------------------
# Phase 11G — Strategy Observatory (read-only, observation only)
# ---------------------------------------------------------------------------


OBSERVATION_ONLY_NOTICE = (
    "Observation only — not investment advice or execution guidance"
)


@router.get("/strategies")
def list_strategies() -> dict[str, Any]:
    """Frozen v1 rule registry — names, summaries, criteria + descriptions."""
    return {
        "notice": PAPER_ONLY_NOTICE,
        "observation_only_notice": OBSERVATION_ONLY_NOTICE,
        "strategies": obs_rules.list_rule_defs(),
    }


@router.get("/strategy-observations")
def list_strategy_observations(
    underlying: str | None = Query(default=None, max_length=12),
    qualified_only: bool = Query(default=False),
    rule_id: str | None = Query(default=None, max_length=64),
    lookback_days: int = Query(default=14, ge=1, le=120),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = obs_observations.list_observations(
        session,
        underlying=underlying,
        qualified_only=qualified_only,
        rule_id=rule_id,
        lookback_days=lookback_days,
        limit=limit,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/strategy-observations/{observation_id}")
def get_strategy_observation(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = obs_observations.get_observation(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(status_code=404, detail="observation not found")
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/performance-summary")
def performance_summary(
    underlying: str | None = Query(default=None, max_length=12),
    strategy_name: str | None = Query(default=None, max_length=64),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = obs_performance.get_performance_summary(
        session, underlying=underlying, strategy_name=strategy_name,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/diagnostics")
def diagnostics(
    lookback_days: int = Query(default=30, ge=1, le=180),
    underlying: str | None = Query(default=None, max_length=12),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = obs_diagnostics.get_diagnostics(
        session, lookback_days=lookback_days, underlying=underlying,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/scenario-replay")
def scenario_replay(
    symbol: str = Query(..., min_length=1, max_length=12),
    as_of: str = Query(..., min_length=10, max_length=10),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    import datetime as _dt
    try:
        as_of_d = _dt.date.fromisoformat(as_of)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid as_of date")
    out = obs_replay.replay(session, symbol=symbol, as_of_date=as_of_d)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


# ---------------------------------------------------------------------------
# Phase 11H — Controlled Strategy Evaluation Layer (read-only, paper-only)
# ---------------------------------------------------------------------------

EVALUATION_DISCLAIMER = (
    "Evaluation scores are fixed rule-based paper analytics. "
    "They are not trade recommendations."
)


@router.get("/evaluation/summary")
def evaluation_summary(
    underlying: str | None = Query(default=None, max_length=12),
    strategy: str | None = Query(default=None, max_length=64),
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = eval_service.get_summary(
        session, underlying=underlying, strategy=strategy,
        lookback_days=lookback_days,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/evaluation/scores")
def evaluation_scores(
    strategy: str | None = Query(default=None, max_length=64),
    underlying: str | None = Query(default=None, max_length=12),
    min_score: int | None = Query(default=None, ge=0, le=100),
    qualified_only: bool = Query(default=False),
    lookback_days: int = Query(default=14, ge=1, le=120),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = eval_service.list_scores(
        session,
        strategy=strategy,
        underlying=underlying,
        min_score=min_score,
        qualified_only=qualified_only,
        lookback_days=lookback_days,
        limit=limit,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/evaluation/scores/{observation_id}")
def evaluation_score_detail(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = eval_service.get_score_detail(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(status_code=404, detail="evaluation score not found")
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/evaluation/distribution")
def evaluation_distribution(
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = eval_service.get_distribution(session, lookback_days=lookback_days)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/evaluation/diagnostics")
def evaluation_diagnostics(
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = eval_service.get_diagnostics(session, lookback_days=lookback_days)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


# ---------------------------------------------------------------------------
# Phase 11I — Decision Support Layer (read-only, paper-only)
# ---------------------------------------------------------------------------


@router.get("/decision-support/summary")
def decision_support_summary(
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ds_review_queue.get_summary(session, lookback_days=lookback_days)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-support/review-queue")
def decision_support_review_queue(
    strategy: str | None = Query(default=None, max_length=64),
    underlying: str | None = Query(default=None, max_length=12),
    min_score: int | None = Query(default=None, ge=0, le=100),
    qualified_only: bool = Query(default=False),
    exclude_severe_flags: bool = Query(default=False),
    bucket: str | None = Query(default=None, max_length=64),
    lookback_days: int = Query(default=14, ge=1, le=120),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ds_review_queue.get_review_queue(
        session,
        strategy=strategy,
        underlying=underlying,
        min_score=min_score,
        qualified_only=qualified_only,
        exclude_severe_flags=exclude_severe_flags,
        bucket=bucket,
        lookback_days=lookback_days,
        limit=limit,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-support/review-queue/{observation_id}")
def decision_support_review_detail(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ds_review_queue.get_review_detail(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(
            status_code=404, detail="review queue entry not found",
        )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-support/buckets")
def decision_support_buckets(
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ds_review_queue.get_buckets(session, lookback_days=lookback_days)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-support/diagnostics")
def decision_support_diagnostics(
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ds_diagnostics.get_diagnostics(session, lookback_days=lookback_days)
    out["notice"] = PAPER_ONLY_NOTICE
    return out
