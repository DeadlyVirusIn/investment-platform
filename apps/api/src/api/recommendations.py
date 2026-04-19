"""Recommendations API — real engine-backed endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import Asset, Recommendation, RecommendationEvidence

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


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


@router.get("")
def list_recommendations(
    active: bool = Query(False, description="reserved for future filtering"),
    limit: int = Query(100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt = (
        select(Recommendation, Asset.symbol)
        .join(Asset, Recommendation.asset_id == Asset.id)
        .order_by(Recommendation.generated_at.desc())
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    recs: list[dict[str, Any]] = []
    for rec, symbol in rows:
        evs = list(
            session.execute(
                select(RecommendationEvidence).where(
                    RecommendationEvidence.recommendation_id == rec.id
                )
            ).scalars()
        )
        recs.append(_rec_payload(rec, symbol, evs))
    return {"recommendations": recs, "count": len(recs)}


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
