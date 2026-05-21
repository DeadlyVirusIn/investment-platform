"""Phase L Decision Detail substrate.

GET-only API for retrieving the reasoning envelope + rendered output
attached to a paper-trading decision.

Endpoints (mounted under /api/v2/decisions):
  GET /v2/decisions/{paper_trade_id}/reasoning
      Returns the latest envelope + rendered reasoning for a trade.
      404 if no envelope is on file for the trade.

Phase L scope: this endpoint reads — it does NOT generate. Envelope
generation happens in the worker decision path (lands in a later day);
this endpoint surfaces what's already in `reasoning_audit`.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.reasoning.envelope import (
    EnvelopeSource, ExpectedSignal, InvalidationTrigger,
    ReasoningEnvelope, ThesisHorizon, ThesisStatement, build_envelope,
)
from apps.api.src.reasoning.renderer import render
from apps.api.src.reasoning.skeletons import SkeletonId
from apps.api.src.reasoning.uncertainty_markers import UncertaintyMarker


router = APIRouter(prefix="/v2/decisions", tags=["reasoning"])
health_router = APIRouter(prefix="/v2/envelope-generation", tags=["reasoning-health"])


def _row_to_envelope(row: Any) -> ReasoningEnvelope:
    """Reconstruct an envelope from a reasoning_audit row."""
    slot_fills = (
        json.loads(row.slot_fills_json)
        if isinstance(row.slot_fills_json, str)
        else row.slot_fills_json
    )
    inv = (
        json.loads(row.invalidation_json)
        if isinstance(row.invalidation_json, str)
        else row.invalidation_json
    )
    th = (
        json.loads(row.thesis_json)
        if isinstance(row.thesis_json, str)
        else row.thesis_json
    )
    markers = (
        json.loads(row.uncertainty_markers)
        if isinstance(row.uncertainty_markers, str)
        else row.uncertainty_markers
    )
    return build_envelope(
        skeleton_id=row.skeleton_id,
        slot_fills=slot_fills,
        invalidation=InvalidationTrigger(
            inv["condition_vocab"], inv.get("threshold"),
        ),
        thesis=ThesisStatement(
            ThesisHorizon(th["horizon"]),
            ExpectedSignal(th["expected_signal"]),
        ),
        uncertainty_markers=markers,
        generated_at=row.envelope_generated_at,
        source=EnvelopeSource(row.source),
    )


@health_router.get("/health")
def get_envelope_generation_health(
    days: int = 14,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Per-day, per-portfolio coverage stats over the last N days.

    Read-only. Sources the v_envelope_gen_coverage view. Always returns
    structure even when the view has no rows (honest absence).
    """
    days = max(1, min(days, 90))
    rows = session.execute(
        text(
            "SELECT portfolio_id, day::text, trades_executed, "
            "       envelopes_attached, coverage_pct, skip_features, "
            "       skip_min_signals, skip_no_skeleton, skip_empty_slots, "
            "       skip_exception "
            "FROM v_envelope_gen_coverage "
            "WHERE day >= (CURRENT_DATE - (:days || ' days')::interval)::date "
            "ORDER BY day DESC, portfolio_id"
        ),
        {"days": days},
    ).all()
    items = [
        {
            "portfolio_id": r.portfolio_id,
            "day": r.day,
            "trades_executed": int(r.trades_executed),
            "envelopes_attached": int(r.envelopes_attached),
            "coverage_pct": float(r.coverage_pct or 0),
            "skip": {
                "features": int(r.skip_features),
                "min_signals": int(r.skip_min_signals),
                "no_skeleton": int(r.skip_no_skeleton),
                "empty_slots": int(r.skip_empty_slots),
                "exception": int(r.skip_exception),
            },
        }
        for r in rows
    ]

    # Recent skeleton distribution across the same window.
    dist_rows = session.execute(
        text(
            "SELECT skeleton_id, COUNT(*) AS n "
            "FROM reasoning_audit "
            "WHERE rendered_at >= NOW() - (:days || ' days')::interval "
            "GROUP BY skeleton_id "
            "ORDER BY n DESC"
        ),
        {"days": days},
    ).all()
    skeleton_dist = {r.skeleton_id: int(r.n) for r in dist_rows}

    return {
        "window_days": days,
        "items": items,
        "recent_skeleton_distribution": skeleton_dist,
        "items_count": len(items),
    }


@health_router.get("/gaps")
def get_envelope_gaps(
    days: int = 30,
    limit: int = 100,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """List paper_trades over the last N days with NO attached envelope.

    Honest absence surface: every gap is a real trade where the engine
    produced no structured reasoning. Operator can review them and
    decide whether the absence is acceptable (substrate gap) or
    indicates a regression.
    """
    days = max(1, min(days, 365))
    limit = max(1, min(limit, 500))
    rows = session.execute(
        text(
            "SELECT pt.id AS paper_trade_id, pt.side, pt.fill_ts::text AS fill_ts, "
            "       pt.recommendation_id, pt.portfolio_id, pt.asset_id "
            "FROM paper_trade pt "
            "LEFT JOIN reasoning_audit ra ON ra.paper_trade_id = pt.id "
            "WHERE pt.fill_ts >= NOW() - (:days || ' days')::interval "
            "  AND ra.id IS NULL "
            "ORDER BY pt.fill_ts DESC "
            "LIMIT :limit"
        ),
        {"days": days, "limit": limit},
    ).all()

    items = [
        {
            "paper_trade_id": r.paper_trade_id,
            "side": r.side,
            "fill_ts": r.fill_ts,
            "recommendation_id": r.recommendation_id,
            "portfolio_id": r.portfolio_id,
            "asset_id": r.asset_id,
        }
        for r in rows
    ]

    total_recent = session.execute(
        text(
            "SELECT COUNT(*) FROM paper_trade "
            "WHERE fill_ts >= NOW() - (:days || ' days')::interval"
        ),
        {"days": days},
    ).scalar() or 0
    with_envelope = total_recent - len(items) if total_recent >= len(items) else 0

    return {
        "window_days": days,
        "total_trades_in_window": int(total_recent),
        "trades_with_envelope": int(with_envelope),
        "gaps_count": len(items),
        "gaps": items,
    }


@health_router.get("/quality")
def get_envelope_quality(
    days: int = 14,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Per-day, per-skeleton reasoning quality stats.

    Sources v_reasoning_quality. Exposes marker firing rate, hash
    uniqueness, and source distribution — the metrics an operator
    needs to spot calibration drift / fabricated variety.
    """
    days = max(1, min(days, 90))
    rows = session.execute(
        text(
            "SELECT day::text, skeleton_id, n_envelopes, avg_marker_count, "
            "       pct_with_markers, n_distinct_envelope_hashes, "
            "       source_distribution "
            "FROM v_reasoning_quality "
            "WHERE day >= (CURRENT_DATE - (:days || ' days')::interval)::date "
            "ORDER BY day DESC, n_envelopes DESC"
        ),
        {"days": days},
    ).all()

    items: list[dict[str, Any]] = []
    for r in rows:
        sd = r.source_distribution
        if isinstance(sd, str):
            import json as _json
            sd = _json.loads(sd)
        items.append({
            "day": r.day,
            "skeleton_id": r.skeleton_id,
            "n_envelopes": int(r.n_envelopes),
            "avg_marker_count": float(r.avg_marker_count or 0),
            "pct_with_markers": float(r.pct_with_markers or 0),
            "n_distinct_envelope_hashes": int(r.n_distinct_envelope_hashes),
            "source_distribution": sd,
        })

    # Marker-firing aggregate across the window.
    marker_rows = session.execute(
        text(
            "WITH expanded AS ("
            "  SELECT jsonb_array_elements_text(uncertainty_markers::jsonb) AS marker "
            "  FROM reasoning_audit "
            "  WHERE rendered_at >= NOW() - (:days || ' days')::interval"
            ") "
            "SELECT marker, COUNT(*) AS n FROM expanded "
            "GROUP BY marker ORDER BY n DESC"
        ),
        {"days": days},
    ).all()
    marker_dist = {r.marker: int(r.n) for r in marker_rows}

    return {
        "window_days": days,
        "items": items,
        "marker_firing_distribution": marker_dist,
        "items_count": len(items),
    }


@router.get("/{paper_trade_id}/reasoning")
def get_decision_reasoning(
    paper_trade_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return envelope + rendered reasoning for a paper_trade."""
    row = session.execute(
        text(
            "SELECT envelope_hash, skeleton_id, slot_fills_json, "
            "       invalidation_json, thesis_json, uncertainty_markers, "
            "       source, envelope_generated_at, rendered_at "
            "FROM reasoning_audit "
            "WHERE paper_trade_id = :tid "
            "ORDER BY rendered_at DESC "
            "LIMIT 1"
        ),
        {"tid": paper_trade_id},
    ).first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No reasoning envelope on file for paper_trade {paper_trade_id}",
        )
    envelope = _row_to_envelope(row)
    rendered = render(session, envelope)
    return {
        "paper_trade_id": paper_trade_id,
        "envelope_hash": row.envelope_hash,
        "skeleton_id": envelope.skeleton_id.value,
        "rendered": {
            "setup": rendered.setup,
            "thesis": rendered.thesis,
            "uncertainty": rendered.uncertainty,
        },
        "envelope": {
            "slot_fills": envelope.slot_fills,
            "invalidation": {
                "condition_vocab": envelope.invalidation.condition_vocab,
                "threshold": envelope.invalidation.threshold,
            },
            "thesis": {
                "horizon": envelope.thesis.horizon.value,
                "expected_signal": envelope.thesis.expected_signal.value,
            },
            "uncertainty_markers": [m.value for m in envelope.uncertainty_markers],
            "source": envelope.source.value,
            "generated_at": envelope.generated_at.isoformat(),
        },
    }
