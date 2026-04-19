"""Recommendations API — engine-backed with latest/sort/limit filters."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import Asset, Recommendation, RecommendationEvidence
from apps.api.src.domain.recommendations.recommendation_engine import (
    list_latest_per_asset,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

SortBy = Literal["generated_at", "confidence"]


def _parse_json(text: str | None, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not text:
        return default or {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"raw": parsed}
    except (json.JSONDecodeError, TypeError):
        return {"raw": text}


def _evidence_payload(ev: RecommendationEvidence) -> dict[str, Any]:
    parsed = _parse_json(ev.summary, {})
    return {
        "factor_key": ev.evidence_type,
        "family": ev.source,
        "weight": str(ev.weight) if ev.weight is not None else None,
        "value": parsed.get("value"),
        "threshold": parsed.get("threshold"),
        "direction": parsed.get("direction"),
        "score": parsed.get("score"),
        "narrative": parsed.get("narrative", ""),
    }


def _rec_payload(
    rec: Recommendation,
    symbol: str | None,
    evidences: list[RecommendationEvidence],
) -> dict[str, Any]:
    rationale = _parse_json(rec.rationale)
    return {
        "id": rec.id,
        "asset_id": rec.asset_id,
        "symbol": symbol,
        "action": rec.action,
        "confidence": str(rec.conviction) if rec.conviction is not None else None,
        "enough_data": rationale.get("enough_data", True),
        "engine_version": rec.model_version,
        "snapshot_hash": rationale.get("snapshot_hash"),
        "thesis": rationale.get("thesis"),
        "tags": rationale.get("tags", []),
        "composite_score": rationale.get("composite_score"),
        "family_scores": rationale.get("family_scores", {}),
        "generated_at": rec.generated_at.isoformat() if rec.generated_at else None,
        "evidence": [_evidence_payload(e) for e in evidences],
    }


def _attach_evidence(session: Session, recs: list[Recommendation]) -> dict[str, list[RecommendationEvidence]]:
    if not recs:
        return {}
    ids = [r.id for r in recs]
    stmt = select(RecommendationEvidence).where(
        RecommendationEvidence.recommendation_id.in_(ids)
    )
    ev_map: dict[str, list[RecommendationEvidence]] = {rid: [] for rid in ids}
    for ev in session.execute(stmt).scalars():
        ev_map.setdefault(ev.recommendation_id, []).append(ev)
    return ev_map


@router.get("")
def list_recommendations(
    latest: bool = Query(False, description="return only latest per asset"),
    sort_by: SortBy = Query("generated_at"),
    order: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if latest:
        recs = list_latest_per_asset(session, limit=limit)
    else:
        sort_col = (
            Recommendation.conviction if sort_by == "confidence"
            else Recommendation.generated_at
        )
        sort_col = sort_col.desc() if order == "desc" else sort_col.asc()
        stmt = select(Recommendation).order_by(sort_col).limit(limit)
        recs = list(session.execute(stmt).scalars())

    # In-python sort so we can apply sort_by after latest-filter
    if sort_by == "confidence":
        recs.sort(
            key=lambda r: r.conviction if r.conviction is not None else 0,
            reverse=(order == "desc"),
        )
    elif sort_by == "generated_at":
        recs.sort(
            key=lambda r: r.generated_at or 0,
            reverse=(order == "desc"),
        )

    # Resolve symbols in one query
    asset_ids = [r.asset_id for r in recs]
    symbol_map: dict[str, str] = {}
    if asset_ids:
        for asset_id, symbol in session.execute(
            select(Asset.id, Asset.symbol).where(Asset.id.in_(asset_ids))
        ).all():
            symbol_map[asset_id] = symbol

    ev_map = _attach_evidence(session, recs)

    payload = [
        _rec_payload(r, symbol_map.get(r.asset_id), ev_map.get(r.id, []))
        for r in recs
    ]
    return {"recommendations": payload, "count": len(payload)}


@router.get("/{rec_id}/evidence")
def get_recommendation_evidence(
    rec_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rec = session.get(Recommendation, rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"unknown recommendation: {rec_id}")
    evs = list(
        session.execute(
            select(RecommendationEvidence).where(
                RecommendationEvidence.recommendation_id == rec_id
            )
        ).scalars()
    )
    return {
        "recommendation_id": rec_id,
        "evidence": [_evidence_payload(e) for e in evs],
        "count": len(evs),
    }
