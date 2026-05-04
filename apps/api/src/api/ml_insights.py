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
