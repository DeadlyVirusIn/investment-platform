"""Persistence for Engine B decision snapshots.

Idempotent UPSERT on (as_of_date, current_state). Pure DB writer; the
DecisionResult is computed elsewhere and passed in.
"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.research.engine_b_decision import DecisionResult


UPSERT_SQL = text("""
INSERT INTO engine_b_decision_snapshot (
    as_of_date, current_state, recommended_state, action, label, score,
    operator_approval, kill_switch_triggered, kill_switch_reason,
    n_observations, gates, failed_gates, score_breakdown,
    stability_windows, note, promotion_pause
)
VALUES (
    :as_of_date, :current_state, :recommended_state, :action, :label, :score,
    :operator_approval, :kill_switch_triggered, :kill_switch_reason,
    :n_observations,
    CAST(:gates AS jsonb), CAST(:failed_gates AS jsonb),
    CAST(:score_breakdown AS jsonb),
    CAST(:stability_windows AS jsonb), :note,
    CAST(:promotion_pause AS jsonb)
)
ON CONFLICT (as_of_date, current_state) DO UPDATE SET
    recommended_state    = EXCLUDED.recommended_state,
    action               = EXCLUDED.action,
    label                = EXCLUDED.label,
    score                = EXCLUDED.score,
    operator_approval    = EXCLUDED.operator_approval,
    kill_switch_triggered = EXCLUDED.kill_switch_triggered,
    kill_switch_reason   = EXCLUDED.kill_switch_reason,
    n_observations       = EXCLUDED.n_observations,
    gates                = EXCLUDED.gates,
    failed_gates         = EXCLUDED.failed_gates,
    score_breakdown      = EXCLUDED.score_breakdown,
    stability_windows    = EXCLUDED.stability_windows,
    note                 = EXCLUDED.note,
    promotion_pause      = EXCLUDED.promotion_pause
""")


def upsert_decision_snapshot(
    session: Session,
    *,
    as_of_date: date,
    decision: DecisionResult,
) -> None:
    payload = decision.to_dict()
    session.execute(UPSERT_SQL, {
        "as_of_date":            as_of_date,
        "current_state":         decision.current_state,
        "recommended_state":     decision.recommended_state,
        "action":                decision.action,
        "label":                 decision.label,
        "score":                 int(decision.score),
        "operator_approval":     bool(decision.operator_approval),
        "kill_switch_triggered": bool(decision.kill_switch_triggered),
        "kill_switch_reason":    decision.kill_switch_reason,
        "n_observations":        int(decision.n_observations),
        "gates":                 json.dumps(payload["gates"]),
        "failed_gates":          json.dumps(payload["failed_gates"]),
        "score_breakdown":       json.dumps(payload["score_breakdown"]),
        "stability_windows":     json.dumps(payload["stability_windows"]),
        "note":                  decision.note[:1000] if decision.note else None,
        "promotion_pause":       json.dumps(payload.get(
            "promotion_pause", {})),
    })
