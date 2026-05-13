"""Phase Opt-B3a Phase 6b-1 — observational analytics HTTP routes.

GET-only endpoints under prefix `/api/options/analytics`. All handlers
delegate to `analytics_queries` (pure SELECT). Zero mutation paths.

Hard rules:
  * Every handler decorated with @router.get(...). No POST/PUT/PATCH/DELETE.
  * Backing query module is SELECT-only (verified by grep test).
  * No filesystem writes. No external HTTP calls. No cache writes.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.options import analytics_queries as Q


router = APIRouter(
    prefix="/options/analytics", tags=["options-analytics"])


def _today_utc() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def _parse_date_or_today(date: str | None) -> dt.date:
    if not date:
        return _today_utc()
    try:
        return dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"invalid date {date!r}; expect YYYY-MM-DD")


# ---------------------------------------------------------------------------
# 1. Integrity 4+1 flags
# ---------------------------------------------------------------------------

@router.get("/integrity")
def integrity_status(
    date: str | None = Query(default=None, description="YYYY-MM-DD; default=today"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return Q.integrity_status(
        session,
        run_date=_parse_date_or_today(date),
        production_providers=settings.OPTIONS_PRODUCTION_PROVIDERS,
        max_age_hours=int(settings.MAX_RUN_CHAIN_AGE_HOURS),
        run_universe=settings.OPTIONS_RUN_UNIVERSE,
        options_shadow_eval_enabled=bool(
            settings.OPTIONS_SHADOW_EVAL_ENABLED),
    )


# ---------------------------------------------------------------------------
# 2. Daily counts time-series
# ---------------------------------------------------------------------------

@router.get("/daily-counts")
def daily_counts(
    days: int = Query(default=14, ge=1, le=365),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = Q.daily_counts(session, days=days)
    return {"days": days, "count": len(rows), "series": rows}


# ---------------------------------------------------------------------------
# 3. By strategy
# ---------------------------------------------------------------------------

@router.get("/by-strategy")
def by_strategy(
    date: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    d = _parse_date_or_today(date)
    return {"run_date": d.isoformat(), "strategies": Q.by_strategy(session, run_date=d)}


# ---------------------------------------------------------------------------
# 4. By rejection (with day-over-day deltas)
# ---------------------------------------------------------------------------

@router.get("/by-rejection")
def by_rejection(
    date: str | None = Query(default=None),
    days: int = Query(default=7, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return Q.by_rejection(
        session, run_date=_parse_date_or_today(date), days=days)


# ---------------------------------------------------------------------------
# 5. Provider mix
# ---------------------------------------------------------------------------

@router.get("/provider-mix")
def provider_mix(
    days: int = Query(default=14, ge=1, le=365),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = Q.provider_mix(session, days=days)
    return {"days": days, "count": len(rows), "rows": rows}


# ---------------------------------------------------------------------------
# 6. Universe coverage
# ---------------------------------------------------------------------------

@router.get("/universe-coverage")
def universe_coverage(
    date: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return Q.universe_coverage(
        session,
        run_date=_parse_date_or_today(date),
        run_universe=settings.OPTIONS_RUN_UNIVERSE,
    )


# ---------------------------------------------------------------------------
# 7. Freshness
# ---------------------------------------------------------------------------

@router.get("/freshness")
def freshness(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return Q.freshness(
        session,
        max_age_hours=int(settings.MAX_RUN_CHAIN_AGE_HOURS),
    )


# ---------------------------------------------------------------------------
# 8. Learning readiness (extended)
# ---------------------------------------------------------------------------

@router.get("/learning-readiness")
def learning_readiness(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = Q.learning_readiness(
        session, run_universe=settings.OPTIONS_RUN_UNIVERSE)
    out["ml_options_learning_enabled"] = bool(
        getattr(settings, "ML_OPTIONS_LEARNING_ENABLED", False))
    out["enabled"] = (
        out["all_gates_pass"]
        and out["ml_options_learning_enabled"])
    return out
