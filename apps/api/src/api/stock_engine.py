"""Stock-engine API — candidates, rejection summary, top-N."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import Asset, CandidateIdea
from apps.api.src.domain.diagnostics.csv_tools import rows_to_csv
from apps.api.src.domain.stock_engine.candidate_repo import rejection_summary

router = APIRouter(prefix="/stock-engine", tags=["stock-engine"])


def _dec(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


def _candidate_payload(
    c: CandidateIdea, symbol: str | None,
) -> dict[str, Any]:
    return {
        "id": c.id,
        "as_of_date": c.as_of_date.isoformat(),
        "asset_id": c.asset_id,
        "symbol": symbol,
        "model_version": c.model_version,
        "engine": c.engine,
        "status": c.status,
        "action": c.action,
        "rejection_reason": c.rejection_reason,
        "composite_score": _dec(c.composite_score),
        "confidence": _dec(c.confidence),
        "factor_breakdown": c.factor_breakdown,
        "regime_snapshot": c.regime_snapshot,
        "recommendation_id": c.recommendation_id,
        "generated_at": c.created_at.isoformat() if c.created_at else None,
    }


def _latest_as_of(session: Session) -> dt.date | None:
    stmt = (
        select(CandidateIdea.as_of_date)
        .order_by(desc(CandidateIdea.as_of_date))
        .limit(1)
    )
    row = session.execute(stmt).first()
    return row[0] if row else None


def _symbol_map(session: Session, asset_ids: list[str]) -> dict[str, str]:
    if not asset_ids:
        return {}
    rows = session.execute(
        select(Asset.id, Asset.symbol).where(Asset.id.in_(asset_ids))
    ).all()
    return {aid: sym for aid, sym in rows}


_CANDIDATE_CSV_COLUMNS = (
    "as_of_date", "symbol", "asset_id", "status", "action",
    "rejection_reason", "composite_score", "confidence",
    "model_version",
)


@router.get("/candidates")
def list_candidates(
    as_of: dt.date | None = Query(
        None, description="YYYY-MM-DD; defaults to latest available",
    ),
    status: Literal["accepted", "rejected"] | None = Query(None),
    action: str | None = Query(None, description="Filter by action (e.g. Buy)"),
    limit: int = Query(100, ge=1, le=1000),
    format: Literal["json", "csv"] = Query("json"),
    session: Session = Depends(get_session),
) -> Any:
    effective = as_of or _latest_as_of(session)
    if effective is None:
        return {"as_of_date": None, "count": 0, "candidates": []}

    stmt = select(CandidateIdea).where(CandidateIdea.as_of_date == effective)
    if status is not None:
        stmt = stmt.where(CandidateIdea.status == status)
    if action is not None:
        stmt = stmt.where(CandidateIdea.action == action)
    stmt = stmt.order_by(
        desc(CandidateIdea.composite_score.is_(None)),   # nulls last
        desc(CandidateIdea.composite_score),
    ).limit(limit)

    rows = list(session.scalars(stmt))
    symbols = _symbol_map(session, [r.asset_id for r in rows])

    payload = {
        "as_of_date": effective.isoformat(),
        "count": len(rows),
        "candidates": [_candidate_payload(r, symbols.get(r.asset_id)) for r in rows],
    }
    if format == "csv":
        csv_rows = [
            {k: c.get(k) for k in _CANDIDATE_CSV_COLUMNS}
            for c in payload["candidates"]
        ]
        body = rows_to_csv(csv_rows, _CANDIDATE_CSV_COLUMNS)
        return Response(content=body, media_type="text/csv")
    return payload


@router.get("/rejections/summary")
def rejections_summary(
    as_of: dt.date | None = Query(None),
    model_version: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    effective = as_of or _latest_as_of(session)
    if effective is None:
        return {
            "as_of_date": None, "total_evaluated": 0,
            "accepted": 0, "rejected": 0, "reasons": {},
        }
    summary = rejection_summary(session, effective, model_version=model_version)
    return {"as_of_date": effective.isoformat(), **summary}


@router.get("/top")
def top_candidates(
    horizon: Literal["swing"] = Query("swing"),
    as_of: dt.date | None = Query(None),
    n: int = Query(10, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    # horizon reserved — swing is the only one in v1
    _ = horizon
    effective = as_of or _latest_as_of(session)
    if effective is None:
        return {
            "as_of_date": None, "horizon": "swing",
            "count": 0, "candidates": [],
        }

    stmt = (
        select(CandidateIdea)
        .where(
            CandidateIdea.as_of_date == effective,
            CandidateIdea.status == "accepted",
            CandidateIdea.action == "Buy",
        )
        .order_by(desc(CandidateIdea.composite_score))
        .limit(n)
    )
    rows = list(session.scalars(stmt))
    symbols = _symbol_map(session, [r.asset_id for r in rows])
    return {
        "as_of_date": effective.isoformat(),
        "horizon": "swing",
        "count": len(rows),
        "candidates": [_candidate_payload(r, symbols.get(r.asset_id)) for r in rows],
    }
