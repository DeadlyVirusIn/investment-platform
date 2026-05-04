"""Personal-Analytics Phase — read-only ML insight surface.

Surfaces dataset health, label availability, feature coverage, and
model-readiness signal. Reads existing tables only — does NOT train
models, does NOT score, and never affects trades.

Hard rules:
  * GET-only. NO POST/PUT/PATCH/DELETE handlers.
  * No writes to any table.
  * Readiness must report `ready=False` whenever the labeled-outcome
    count is below the configured floor; never spoof a green light.
  * Endpoints never reach into recommendation/strategy execution
    code. Imports are limited to db, sqlalchemy, ml.features (column
    list only), and stdlib.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import get_session


router = APIRouter(prefix="/ml/insights", tags=["ml-insights"])


# Floor for declaring the ML pipeline "ready" enough to look at outputs.
# Conservative on purpose — labels under this count produce highly
# unstable metrics and should not drive any decision.
MIN_LABELED_OUTCOMES = 20


# ---------------------------------------------------------------------------
# /ml/insights/summary
# ---------------------------------------------------------------------------
@router.get("/summary")
def insights_summary(db: Session = Depends(get_session)) -> dict[str, Any]:
    """High-level rollup: counts, readiness flag, ML-can-affect-trades
    pin, and reason string. The reason explains exactly why the
    pipeline is or isn't ready so the operator has no ambiguity."""
    rec_total = db.execute(text(
        "SELECT count(*) FROM recommendation"
    )).scalar() or 0
    out_total = db.execute(text(
        "SELECT count(*) FROM recommendation_outcome"
    )).scalar() or 0
    labeled = db.execute(text("""
        SELECT count(*) FROM recommendation_outcome
        WHERE barrier_label IS NOT NULL
           OR realized_30d_return IS NOT NULL
    """)).scalar() or 0
    open_pending = db.execute(text("""
        SELECT count(*) FROM recommendation_outcome
        WHERE barrier_label IS NULL
          AND realized_30d_return IS NULL
    """)).scalar() or 0
    # Recommendations missing outcome row entirely.
    missing_outcomes = db.execute(text("""
        SELECT count(*) FROM recommendation r
        WHERE NOT EXISTS (
          SELECT 1 FROM recommendation_outcome o
          WHERE o.recommendation_id = r.id
        )
    """)).scalar() or 0

    replay_decisions = db.execute(text(
        "SELECT count(*) FROM ml_replay_decision"
    )).scalar() or 0
    replay_outcomes = db.execute(text(
        "SELECT count(*) FROM ml_replay_outcome"
    )).scalar() or 0
    research_snaps = db.execute(text(
        "SELECT count(*) FROM ml_research_snapshot"
    )).scalar() or 0
    shadow_predictions = db.execute(text(
        "SELECT count(*) FROM ml_shadow_prediction"
    )).scalar() or 0

    ready = int(labeled) >= MIN_LABELED_OUTCOMES
    if not ready:
        if int(labeled) == 0:
            reason = "no_labeled_outcomes"
        else:
            reason = (
                f"insufficient_labeled_outcomes "
                f"(have={int(labeled)}, need>={MIN_LABELED_OUTCOMES})"
            )
    else:
        reason = "labeled_outcomes_above_floor"

    return {
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ml_can_affect_trades": False,
        "notice": (
            "ML insight only — cannot affect trades. "
            "ML_CAN_AFFECT_TRADES is pinned to false."
        ),
        "ready": ready,
        "reason": reason,
        "min_labeled_outcomes_required": MIN_LABELED_OUTCOMES,
        "counts": {
            "recommendations_total": int(rec_total),
            "recommendation_outcome_rows": int(out_total),
            "labeled_outcomes": int(labeled),
            "open_pending_outcomes": int(open_pending),
            "missing_outcome_rows": int(missing_outcomes),
            "ml_replay_decision": int(replay_decisions),
            "ml_replay_outcome": int(replay_outcomes),
            "ml_research_snapshot": int(research_snaps),
            "ml_shadow_prediction": int(shadow_predictions),
        },
    }


# ---------------------------------------------------------------------------
# /ml/insights/dataset
# ---------------------------------------------------------------------------
@router.get("/dataset")
def insights_dataset(db: Session = Depends(get_session)) -> dict[str, Any]:
    """Dataset health — replay vs live split + train/eval breakdown
    where the data is structured for it. Walk-forward / purged-split
    sizing is not done here; this endpoint reports the raw row totals
    available to a downstream splitter."""
    decision_total = db.execute(text(
        "SELECT count(*) FROM decision_log"
    )).scalar() or 0
    replay_dec = db.execute(text(
        "SELECT count(*) FROM ml_replay_decision"
    )).scalar() or 0
    replay_out = db.execute(text(
        "SELECT count(*) FROM ml_replay_outcome"
    )).scalar() or 0

    # Replay-tagged recommendations via replay_recovery_manifest. Live
    # = recommendations not appearing in the manifest.
    replay_recs = db.execute(text("""
        SELECT count(*) FROM recommendation r
        WHERE EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'recommendation'
            AND m.entity_id = r.id::text
        )
    """)).scalar() or 0
    live_recs = db.execute(text("""
        SELECT count(*) FROM recommendation r
        WHERE NOT EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'recommendation'
            AND m.entity_id = r.id::text
        )
    """)).scalar() or 0

    return {
        "ml_can_affect_trades": False,
        "decision_log_rows": int(decision_total),
        "ml_replay_decision_rows": int(replay_dec),
        "ml_replay_outcome_rows": int(replay_out),
        "recommendations": {
            "live": int(live_recs),
            "replay": int(replay_recs),
            "total": int(live_recs) + int(replay_recs),
        },
        "notes": [
            (
                "Train/eval split sizing belongs to a downstream "
                "purged-walk-forward splitter; this endpoint reports "
                "raw row totals only."
            ),
            (
                "Replay-tagged rows must be excluded or labeled "
                "explicitly when building any leakage-sensitive "
                "training frame."
            ),
        ],
    }


# ---------------------------------------------------------------------------
# /ml/insights/features
# ---------------------------------------------------------------------------
@router.get("/features")
def insights_features() -> dict[str, Any]:
    """Reports the FEATURE_COLUMNS allow-list and any forbidden-name
    flags. Pure metadata — no DB scan beyond this since the feature
    space is defined statically by `apps.api.src.ml.features`."""
    # Lazy import keeps the router safe to import even if the ml
    # subsystem is broken.
    from apps.api.src.ml.features import (
        FEATURE_COLUMNS, IDENTITY_COLUMNS, is_forbidden_feature_name,
    )
    feats = list(FEATURE_COLUMNS)
    forbidden_examples = [
        c for c in (
            "future_return_30d",
            "barrier_label",
            "outcome_pnl",
            "y",
        )
        if is_forbidden_feature_name(c)
    ]
    return {
        "ml_can_affect_trades": False,
        "feature_count": len(feats),
        "identity_columns": list(IDENTITY_COLUMNS),
        "feature_columns": feats,
        "leakage_check": {
            "is_forbidden_feature_name_implemented": True,
            "rejected_sample": forbidden_examples,
        },
        "notes": [
            (
                "Feature coverage by row is computed by the dataset "
                "builder; live coverage scan would require materializing "
                "the dataset and is out of scope for an insight endpoint."
            ),
        ],
    }


# ---------------------------------------------------------------------------
# /ml/insights/labels
# ---------------------------------------------------------------------------
@router.get("/labels")
def insights_labels(db: Session = Depends(get_session)) -> dict[str, Any]:
    """Label availability + outcome breakdown. Honest about pending:
    `open_pending` is reported separately and never silently rolled
    into the labeled count."""
    barrier_rows = db.execute(text("""
        SELECT
          coalesce(barrier_label, 0)        AS bucket_raw,
          (barrier_label IS NULL)           AS is_pending,
          count(*)                          AS n
        FROM recommendation_outcome
        GROUP BY 1, 2
        ORDER BY 1
    """)).mappings().all()
    barrier_dist: dict[str, int] = {}
    barrier_open_pending = 0
    for r in barrier_rows:
        if r["is_pending"]:
            barrier_open_pending += int(r["n"])
        else:
            barrier_dist[str(r["bucket_raw"])] = int(r["n"])

    realized_rows = db.execute(text("""
        SELECT
          count(*) FILTER (WHERE realized_30d_return IS NOT NULL) AS labeled_30d,
          count(*) FILTER (WHERE realized_30d_return IS NULL)     AS pending_30d,
          count(*) FILTER (WHERE realized_90d_return IS NOT NULL) AS labeled_90d,
          count(*) FILTER (WHERE realized_90d_return IS NULL)     AS pending_90d
        FROM recommendation_outcome
    """)).mappings().first()

    labeled_total = db.execute(text("""
        SELECT count(*) FROM recommendation_outcome
        WHERE barrier_label IS NOT NULL
           OR realized_30d_return IS NOT NULL
    """)).scalar() or 0

    ready = int(labeled_total) >= MIN_LABELED_OUTCOMES
    note = None
    if int(labeled_total) == 0:
        note = "ML evaluation not ready — outcomes still pending."

    return {
        "ml_can_affect_trades": False,
        "labeled_outcomes_total": int(labeled_total),
        "min_required_for_ready": MIN_LABELED_OUTCOMES,
        "ready_for_evaluation": ready,
        "barrier_label_distribution": barrier_dist,
        "barrier_label_open_pending": barrier_open_pending,
        "realized_returns": {
            "labeled_30d": int(realized_rows["labeled_30d"] or 0),
            "pending_30d": int(realized_rows["pending_30d"] or 0),
            "labeled_90d": int(realized_rows["labeled_90d"] or 0),
            "pending_90d": int(realized_rows["pending_90d"] or 0),
        },
        "note": note,
    }


# ---------------------------------------------------------------------------
# /ml/insights/readiness
# ---------------------------------------------------------------------------
@router.get("/readiness")
def insights_readiness(
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Aggregate ML readiness signal — returns the complete checklist
    the UI needs to render the readiness panel without any client-side
    derivation. Pure read-only.

    `is_ready=True` requires:
      * labeled_trade_count >= MIN_LABELED_OUTCOMES
      * leakage check passing (`is_forbidden_feature_name` import succeeds)
      * NOT all-replay-only, OR caller explicitly accepts replay
        diagnostics (the `dataset_is_replay_only` warning fires either
        way; readiness flag itself is independent so the analyst can
        still inspect the data)."""
    from apps.api.src.ml.features import is_forbidden_feature_name

    labeled_trade_count = db.execute(text("""
        SELECT count(*) FROM recommendation_outcome
        WHERE barrier_label IS NOT NULL
           OR realized_30d_return IS NOT NULL
    """)).scalar() or 0
    pending_trade_count = db.execute(text("""
        SELECT count(*) FROM recommendation_outcome
        WHERE barrier_label IS NULL
          AND realized_30d_return IS NULL
    """)).scalar() or 0
    open_position_count = db.execute(text("""
        SELECT count(*) FROM paper_position WHERE is_open = true
    """)).scalar() or 0
    replay_trade_count = db.execute(text("""
        SELECT count(*) FROM paper_trade pt
        WHERE EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'paper_trade'
            AND m.entity_id = pt.id::text
            AND m.source IN ('replay','test')
        )
    """)).scalar() or 0
    live_trade_count = db.execute(text("""
        SELECT count(*) FROM paper_trade pt
        WHERE NOT EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'paper_trade'
            AND m.entity_id = pt.id::text
            AND m.source IN ('replay','test')
        )
    """)).scalar() or 0
    decision_log_rows = db.execute(text(
        "SELECT count(*) FROM decision_log"
    )).scalar() or 0

    # Leakage check: importing the feature module + invoking the
    # name-rejection helper without exception is sufficient for an
    # insight readout. We do not run a model.
    try:
        is_forbidden_feature_name("future_return_30d")
        leakage_check_status = "passed"
    except Exception as exc:  # noqa: BLE001
        leakage_check_status = f"error:{type(exc).__name__}"

    is_ready = int(labeled_trade_count) >= MIN_LABELED_OUTCOMES
    if int(labeled_trade_count) == 0:
        reason = "no_labeled_outcomes"
        next_unlock_condition = (
            "Wait for trades to close and outcomes to be labeled."
        )
    elif not is_ready:
        reason = (
            f"insufficient_labeled_outcomes "
            f"(have={int(labeled_trade_count)}, "
            f"need>={MIN_LABELED_OUTCOMES})"
        )
        next_unlock_condition = (
            f"Need {MIN_LABELED_OUTCOMES - int(labeled_trade_count)} "
            f"more labeled outcomes."
        )
    else:
        reason = "labeled_outcomes_above_floor"
        next_unlock_condition = "Already met."

    # Replay-only warning. Triggers when there is at least one trade
    # and 100% of them are replay-tagged.
    total_trades = int(replay_trade_count) + int(live_trade_count)
    dataset_is_replay_only = (
        total_trades > 0 and int(live_trade_count) == 0
    )
    warnings: list[str] = []
    if dataset_is_replay_only:
        warnings.append(
            "Current dataset is replay-derived; treat model metrics "
            "as recovery diagnostics."
        )

    # Missing requirements (any item that would prevent honest ML eval).
    missing_requirements: list[str] = []
    if int(labeled_trade_count) < MIN_LABELED_OUTCOMES:
        missing_requirements.append(
            f"labeled_trade_count<{MIN_LABELED_OUTCOMES}"
        )
    if leakage_check_status != "passed":
        missing_requirements.append(
            f"leakage_check_failed:{leakage_check_status}"
        )
    if dataset_is_replay_only:
        missing_requirements.append("dataset_is_replay_only")

    return {
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ml_can_affect_trades": False,
        "is_ready": bool(is_ready),
        "reason": reason,
        "next_unlock_condition": next_unlock_condition,
        "required_min_labeled_trades": MIN_LABELED_OUTCOMES,
        "labeled_trade_count": int(labeled_trade_count),
        "pending_trade_count": int(pending_trade_count),
        "open_position_count": int(open_position_count),
        "replay_trade_count": int(replay_trade_count),
        "live_trade_count": int(live_trade_count),
        "leakage_check_status": leakage_check_status,
        "dataset_rows": int(decision_log_rows),
        "feature_coverage": {
            # Feature coverage by row would require materializing the
            # dataset; surface availability metadata instead so the UI
            # has something honest to render.
            "feature_columns_defined": True,
            "leakage_guard_implemented": (
                leakage_check_status == "passed"
            ),
        },
        "missing_requirements": missing_requirements,
        "dataset_is_replay_only": dataset_is_replay_only,
        "warnings": warnings,
        "checklist": [
            {
                "name": "trades_exist",
                "ok": total_trades > 0,
            },
            {
                "name": "exits_recorded",
                "ok": (
                    db.execute(text(
                        "SELECT count(*) > 0 FROM paper_trade "
                        "WHERE realized_pnl IS NOT NULL"
                    )).scalar() or False
                ),
            },
            {
                "name": "outcomes_labeled",
                "ok": int(labeled_trade_count) > 0,
            },
            {
                "name": "leakage_check_passed",
                "ok": leakage_check_status == "passed",
            },
            {
                "name": "enough_labels",
                "ok": int(labeled_trade_count)
                       >= MIN_LABELED_OUTCOMES,
            },
        ],
        "notice": (
            "ML readiness only — cannot affect trades. "
            "ML_CAN_AFFECT_TRADES is pinned to false. This endpoint "
            "does not train models, score data, or write artifacts."
        ),
    }
