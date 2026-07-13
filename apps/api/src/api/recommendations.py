"""Recommendations API — engine-backed with latest/sort/limit filters."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from decimal import Decimal

from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.db.models import Asset, Recommendation, RecommendationEvidence
from apps.api.src.domain.recommendations.diagnostics import (
    DEFAULT_BUY_THRESHOLD,
    BatchSummary,
    Diagnostic,
    analyze_recommendation,
    order_by_closest_to_buy,
    summarize_batch,
)
from apps.api.src.domain.recommendations.recommendation_engine import (
    list_latest_per_asset,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

# Wave 1A/1B read-side bounds — see the preflight block in
# list_recommendations for semantics.
import threading  # noqa: E402

MAX_PREFLIGHT_EVALS_PER_REQUEST = 250
_preflight_gate_lock = threading.Lock()

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
    sector: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    rationale = _parse_json(rec.rationale)
    policy = rationale.get("policy") or {}
    return {
        "id": rec.id,
        "asset_id": rec.asset_id,
        "symbol": symbol,
        # Human company name (e.g. "Royalty Pharma plc"); null until the
        # Polygon backfill populates it. Never fabricated — UI falls back to
        # the ticker.
        "name": name,
        # Coded sector (e.g. "consumer_disc"); the frontend humanizes it.
        # Null when the asset has no sector. Never fabricated.
        "sector": sector,
        "action": rec.action,
        "confidence": str(rec.conviction) if rec.conviction is not None else None,
        "confidence_label": rationale.get("confidence_label"),
        "enough_data": rationale.get("enough_data", True),
        "stale_data": rationale.get("stale_data", False),
        "engine_version": rec.model_version,
        "snapshot_hash": rec.snapshot_hash or rationale.get("snapshot_hash"),
        "thesis": rationale.get("thesis"),
        "tags": rationale.get("tags", []),
        "composite_score": rationale.get("composite_score"),
        "family_scores": rationale.get("family_scores", {}),
        "generated_at": rec.generated_at.isoformat() if rec.generated_at else None,
        "evidence": [_evidence_payload(e) for e in evidences],
        # Policy layer — original fields above remain the engine output;
        # these surface any after-policy adjustments.
        "policy": policy or None,
        "adjusted_action": policy.get("adjusted_action"),
        "adjusted_confidence": policy.get("adjusted_confidence"),
        "adjusted_composite_score": policy.get("adjusted_composite_score"),
        "policy_adjustments": policy.get("adjustments", []),
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

    # Resolve symbols + sectors in one query
    asset_ids = [r.asset_id for r in recs]
    symbol_map: dict[str, str] = {}
    sector_map: dict[str, str | None] = {}
    name_map: dict[str, str | None] = {}
    if asset_ids:
        for asset_id, symbol, sector, name in session.execute(
            select(Asset.id, Asset.symbol, Asset.sector, Asset.name).where(Asset.id.in_(asset_ids))
        ).all():
            symbol_map[asset_id] = symbol
            sector_map[asset_id] = sector
            name_map[asset_id] = name

    ev_map = _attach_evidence(session, recs)

    # Wave 1A — publication preflight (flag-off = byte-identical legacy
    # behavior). When enabled: every candidate gets a verdict matched to its
    # EXACT current input hash (ensure_current_verdict re-evaluates on any
    # fact change and fails closed to HOLD); only READY /
    # READY_WITH_LIMITATIONS publish to beginner surfaces, each carrying a
    # redacted public projection. HOLD/BLOCKED stay owner-visible via
    # /admin/preflight and /recommendations/diagnostics — rows are never
    # deleted or rewritten.
    projections: dict[str, dict[str, Any]] = {}
    if settings.RECOMMENDATION_PREFLIGHT_ENABLED:
        from apps.api.src.api.publication_preflight import public_projection
        from apps.api.src.domain.publication.preflight import (
            ensure_current_verdicts_bulk,
        )

        # Read-side-effect bounds (Wave 1B review): at most
        # MAX_PREFLIGHT_EVALS_PER_REQUEST candidates are evaluated per
        # request (typical steady state: zero — verdicts for the current
        # input hash already exist and evaluation short-circuits to a
        # SELECT). Candidates beyond the cap fail CLOSED (not published this
        # request) rather than fail open. _preflight_gate_lock single-flights
        # concurrent cold requests so a thundering herd cannot multiply
        # identical evaluations (losers of the DB unique-key race would be
        # harmless but wasteful).
        published: list[Recommendation] = []
        with _preflight_gate_lock:
            batch = recs
            rows = ensure_current_verdicts_bulk(
                session, batch,
                max_evaluations=MAX_PREFLIGHT_EVALS_PER_REQUEST,
            )
        for r in batch:
            row = rows.get(r.id) or {}
            if row.get("verdict") in ("READY", "READY_WITH_LIMITATIONS"):
                published.append(r)
                projections[r.id] = public_projection(row)
        recs = published

    payload = []
    for r in recs:
        p = _rec_payload(
            r, symbol_map.get(r.asset_id), ev_map.get(r.id, []),
            sector_map.get(r.asset_id), name_map.get(r.asset_id),
        )
        if r.id in projections:
            p["preflight"] = projections[r.id]
        payload.append(p)
    return {"recommendations": payload, "count": len(payload)}


def _d_to_str(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


def _contributor_dict(c: Any) -> dict[str, Any]:
    return {
        "factor_key": c.factor_key,
        "family": c.family,
        "score": _d_to_str(c.score),
        "weight": _d_to_str(c.weight),
        "direction": c.direction,
        "narrative": c.narrative,
    }


def _damper_dict(f: Any) -> dict[str, Any]:
    return {
        "rule": f.rule,
        "factor": f.factor,
        "score_before": _d_to_str(f.score_before),
        "score_after": _d_to_str(f.score_after),
        "reason": f.reason,
    }


def _diagnostic_dict(d: Diagnostic) -> dict[str, Any]:
    return {
        "recommendation_id": d.recommendation_id,
        "asset_id": d.asset_id,
        "symbol": d.symbol,
        "action": d.action,
        "composite_score": _d_to_str(d.composite_score),
        "original_composite_score": _d_to_str(d.original_composite_score),
        "confidence": _d_to_str(d.confidence),
        "confidence_label": d.confidence_label,
        "distance_to_buy": _d_to_str(d.distance_to_buy),
        "top_positive": [_contributor_dict(c) for c in d.top_positive],
        "top_negative": [_contributor_dict(c) for c in d.top_negative],
        "dampers": [_damper_dict(f) for f in d.dampers],
        "stale_data": d.stale_data,
        "enough_data": d.enough_data,
        "family_scores": {k: _d_to_str(v) for k, v in d.family_scores.items()},
        "generated_at": d.generated_at_iso,
    }


def _summary_dict(s: BatchSummary) -> dict[str, Any]:
    return {
        "total": s.total,
        "buy_threshold": _d_to_str(s.buy_threshold),
        "buys": s.buys,
        "action_distribution": s.action_distribution,
        "score_distribution": [
            {"bucket": b.label, "count": b.count} for b in s.score_distribution
        ],
        "confidence_distribution": [
            {"bucket": b.label, "count": b.count} for b in s.confidence_distribution
        ],
        "near_buy_tight_pct": 0.05,
        "near_buy_tight_count": s.near_buy_tight,
        "near_buy_loose_pct": 0.10,
        "near_buy_loose_count": s.near_buy_loose,
        "dampers_applied": s.dampers_applied,
        "stale_count": s.stale_count,
        "insufficient_data_count": s.insufficient_data_count,
        "max_composite": _d_to_str(s.max_composite),
        "min_composite": _d_to_str(s.min_composite),
        "median_composite": _d_to_str(s.median_composite),
    }


@router.get("/diagnostics")
def get_recommendation_diagnostics(
    buy_threshold: float = Query(float(DEFAULT_BUY_THRESHOLD), ge=-1.0, le=1.0),
    limit: int = Query(100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Explain *why* Buy signals aren't appearing across the latest batch.

    Ranks assets by closest-to-Buy; surfaces contributors + damper flags;
    returns batch-level score/confidence histograms. Derived from existing
    Recommendation + RecommendationEvidence rows — no engine re-run.
    """
    recs = list_latest_per_asset(session, limit=limit)
    asset_ids = [r.asset_id for r in recs]
    symbol_map: dict[str, str] = {}
    if asset_ids:
        for aid, sym in session.execute(
            select(Asset.id, Asset.symbol).where(Asset.id.in_(asset_ids))
        ).all():
            symbol_map[aid] = sym

    ev_map = _attach_evidence(session, recs)

    threshold = Decimal(str(buy_threshold))
    diagnostics: list[Diagnostic] = []
    for rec in recs:
        diagnostics.append(analyze_recommendation(
            recommendation_id=rec.id,
            asset_id=rec.asset_id,
            symbol=symbol_map.get(rec.asset_id),
            action=rec.action,
            rationale_json=rec.rationale,
            conviction=rec.conviction if isinstance(rec.conviction, Decimal) or rec.conviction is None
                      else Decimal(str(rec.conviction)),
            generated_at_iso=rec.generated_at.isoformat() if rec.generated_at else None,
            evidences=ev_map.get(rec.id, []),
            buy_threshold=threshold,
        ))

    ordered = order_by_closest_to_buy(diagnostics)
    summary = summarize_batch(diagnostics, buy_threshold=threshold)

    return {
        "summary": _summary_dict(summary),
        "diagnostics": [_diagnostic_dict(d) for d in ordered],
        "count": len(ordered),
    }


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
