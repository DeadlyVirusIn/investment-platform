"""Scheduled job: generate candidate_idea rows for the stock-swing universe.

Idempotent on ``(as_of_date, asset_id, model_version)``. Safe to re-run.
Writes one row per asset evaluated — never silent. Shadow mode in Batch 4:
no ``recommendation`` rows created; paper trader not invoked.
"""

from __future__ import annotations

import datetime as dt

from loguru import logger

from apps.api.src.db import SessionLocal
from apps.api.src.domain.actions.materializer import materialize_actions_for_day
from apps.api.src.domain.stock_engine.candidate_repo import upsert_candidates
from apps.api.src.domain.stock_engine.decision_engine import (
    DEFAULT_UNIVERSE,
    generate_candidates,
)


async def generate_stock_candidates(
    as_of: dt.date | None = None,
    universe_name: str = DEFAULT_UNIVERSE,
) -> None:
    target = as_of or dt.date.today()

    with SessionLocal() as session:
        rows = generate_candidates(session, target, universe_name=universe_name)
        if not rows:
            logger.warning(
                "generate_stock_candidates: no evaluated assets for {} (universe={})",
                target, universe_name,
            )
            return
        written = upsert_candidates(session, rows)
        # Decision UX: materialize action_item rows from just-written candidates
        try:
            actions_written = materialize_actions_for_day(session, target)
            logger.info(
                "generate_stock_candidates action_items materialized={}",
                actions_written,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "generate_stock_candidates: action materialization failed: {}", exc,
            )

    accepted = sum(1 for r in rows if r.status == "accepted")
    rejected = sum(1 for r in rows if r.status == "rejected")
    buys = sum(1 for r in rows if r.action == "Buy")
    reasons: dict[str, int] = {}
    for r in rows:
        if r.rejection_reason:
            reasons[r.rejection_reason] = reasons.get(r.rejection_reason, 0) + 1

    logger.info(
        "generate_stock_candidates {} written={} accepted={} rejected={} buys={} "
        "reasons={}",
        target, written, accepted, rejected, buys, reasons,
    )
