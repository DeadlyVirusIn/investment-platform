"""DB glue — joins signal + signal_outcome, calls computer, upserts.

Phase 2 write-only. Nothing downstream reads from model_scorecard.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apps.api.src.db.models import ModelScorecard, Signal, SignalOutcome
from apps.api.src.domain.model_scorecard.computer import (
    ScorecardMetrics,
    compute_scorecard,
)

DEFAULT_WINDOW_DAYS = 30


def _load_joined_rows(
    session: Session,
    model_name: str,
    window_start: dt.date,
    window_end: dt.date,
) -> list[dict[str, Any]]:
    """Fetch signals with outcomes for a model within the window.

    Filters by Signal.strategy_id == model_name.
    Window boundary: Signal.as_of_date BETWEEN window_start AND window_end.
    Only includes signals with a materialized signal_outcome row.
    """
    stmt = (
        select(Signal, SignalOutcome)
        .join(SignalOutcome, SignalOutcome.signal_id == Signal.signal_id)
        .where(
            Signal.strategy_id == model_name,
            Signal.as_of_date >= window_start,
            Signal.as_of_date <= window_end,
        )
    )
    rows: list[dict[str, Any]] = []
    for sig, out in session.execute(stmt).all():
        rows.append({
            "signal_id": sig.signal_id,
            "strategy_id": sig.strategy_id,
            "signal_as_of_date": sig.as_of_date,
            "holding_period_bars": sig.holding_period_bars,
            "confidence": float(sig.confidence) if sig.confidence is not None else None,
            "factor_top": None,     # current Signal schema has no factor_top;
                                    # populate when adapters write it.
            "outcome_label": out.outcome_label,
            "realized_return": float(out.realized_return)
                if out.realized_return is not None else None,
            "max_drawdown": float(out.max_drawdown)
                if out.max_drawdown is not None else None,
            "evaluation_timestamp": out.evaluation_timestamp,
        })
    return rows


def _upsert(
    session: Session,
    model_name: str,
    window_start: dt.date,
    window_end: dt.date,
    m: ScorecardMetrics,
) -> None:
    import uuid
    now = dt.datetime.now(dt.timezone.utc)
    payload = asdict(m)
    row = {
        "id": str(uuid.uuid4()),
        "model_name": model_name,
        "window_start": window_start,
        "window_end": window_end,
        "total_signals": payload["total_signals"],
        "win_rate": Decimal(str(payload["win_rate"])) if payload["win_rate"] is not None else None,
        "avg_return": Decimal(str(payload["avg_return"])) if payload["avg_return"] is not None else None,
        "avg_drawdown": Decimal(str(payload["avg_drawdown"])) if payload["avg_drawdown"] is not None else None,
        "sharpe_like_metric": Decimal(str(payload["sharpe_like_metric"])) if payload["sharpe_like_metric"] is not None else None,
        "avg_days_to_evaluation": Decimal(str(payload["avg_days_to_evaluation"])) if payload["avg_days_to_evaluation"] is not None else None,
        "max_days_to_evaluation": payload["max_days_to_evaluation"],
        "pct_within_horizon": Decimal(str(payload["pct_within_horizon"])) if payload["pct_within_horizon"] is not None else None,
        "calibration": payload["calibration"],
        "factor_effectiveness": payload["factor_effectiveness"],
        "updated_at": now,
    }
    stmt = pg_insert(ModelScorecard).values(**row)
    stmt = stmt.on_conflict_do_update(
        index_elements=["model_name", "window_start", "window_end"],
        set_={k: v for k, v in row.items() if k not in ("id", "created_at")},
    )
    session.execute(stmt)


def compute_and_persist(
    session: Session, *,
    model_name: str,
    today: dt.date | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> ScorecardMetrics:
    today = today or dt.date.today()
    window_end = today
    window_start = window_end - dt.timedelta(days=window_days)

    rows = _load_joined_rows(session, model_name, window_start, window_end)
    metrics = compute_scorecard(rows)
    _upsert(session, model_name, window_start, window_end, metrics)
    session.commit()
    logger.info(
        "[scorecard] model={} window={}..{} total={} win_rate={} avg_ret={} sharpe={} avg_days={}",
        model_name, window_start, window_end,
        metrics.total_signals, metrics.win_rate, metrics.avg_return,
        metrics.sharpe_like_metric, metrics.avg_days_to_evaluation,
    )
    return metrics


def list_distinct_models(session: Session) -> list[str]:
    return [
        r[0] for r in session.execute(
            select(Signal.strategy_id).distinct()
        ).all()
    ]
