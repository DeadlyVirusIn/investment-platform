"""Read/write helpers for candidate_idea."""

from __future__ import annotations

import datetime as dt
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apps.api.src.db.models import CandidateIdea
from apps.api.src.domain.stock_engine.decision_engine import CandidateRow


def upsert_candidates(
    session: Session, rows: Sequence[CandidateRow],
) -> int:
    """Upsert candidate rows on ``(as_of_date, asset_id, model_version)``.
    Returns the number of rows processed."""
    n = 0
    for r in rows:
        stmt = (
            pg_insert(CandidateIdea)
            .values(
                as_of_date=r.as_of_date,
                asset_id=r.asset_id,
                model_version=r.model_version,
                engine="stock_swing",
                status=r.status,
                action=r.action,
                rejection_reason=r.rejection_reason,
                composite_score=r.composite_score,
                confidence=r.confidence,
                factor_breakdown=r.factor_breakdown,
                regime_snapshot=r.regime_snapshot,
            )
            .on_conflict_do_update(
                index_elements=["as_of_date", "asset_id", "model_version"],
                set_={
                    "status": r.status,
                    "action": r.action,
                    "rejection_reason": r.rejection_reason,
                    "composite_score": r.composite_score,
                    "confidence": r.confidence,
                    "factor_breakdown": r.factor_breakdown,
                    "regime_snapshot": r.regime_snapshot,
                },
            )
        )
        session.execute(stmt)
        n += 1
    session.commit()
    return n


def rejection_summary(
    session: Session, as_of: dt.date, model_version: str | None = None,
) -> dict[str, int | dict[str, int]]:
    """Per-day (accepted/rejected/per-reason) counts."""
    stmt = (
        select(
            CandidateIdea.status,
            CandidateIdea.rejection_reason,
            func.count().label("n"),
        )
        .where(CandidateIdea.as_of_date == as_of)
    )
    if model_version is not None:
        stmt = stmt.where(CandidateIdea.model_version == model_version)
    stmt = stmt.group_by(CandidateIdea.status, CandidateIdea.rejection_reason)

    total = 0
    accepted = 0
    rejected = 0
    reasons: dict[str, int] = {}
    for status, reason, n in session.execute(stmt).all():
        total += int(n)
        if status == "accepted":
            accepted += int(n)
        elif status == "rejected":
            rejected += int(n)
        if reason is not None:
            reasons[reason] = reasons.get(reason, 0) + int(n)

    return {
        "total_evaluated": total,
        "accepted": accepted,
        "rejected": rejected,
        "reasons": reasons,
    }
