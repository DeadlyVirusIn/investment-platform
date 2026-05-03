"""Shadow scoring — per-decision ML predictions + explanations.

Persists to ml_shadow_prediction. Never mutates decision_log or any
execution path.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.ml.advisory import AdvisoryAction, build_advisory
from apps.api.src.ml.models import TrainedModel


@dataclass
class ShadowScoringResult:
    model_run_id: str
    n_scored: int
    n_persisted: int
    warnings: list[str] = field(default_factory=list)


def score_recent_decisions(
    session: Session,
    df: pd.DataFrame,
    *,
    model: TrainedModel,
    model_run_id: str,
    feature_cols: list[str],
    n_training_rows: int,
    min_training_rows: int,
    persist: bool = True,
) -> ShadowScoringResult:
    """Score each row in `df` and persist ml_shadow_prediction rows."""
    warnings: list[str] = []
    if df.empty:
        return ShadowScoringResult(
            model_run_id=model_run_id, n_scored=0, n_persisted=0,
            warnings=["empty input frame"],
        )
    # Predict probabilities (neutral 0.5 if model skipped)
    for f in feature_cols:
        if f not in df.columns:
            df[f] = 0.0
    scores = model.predict_proba(df)

    top_pos = _top_drivers(model.coefficients or model.feature_importances,
                           positive=True)
    top_neg = _top_drivers(model.coefficients or model.feature_importances,
                           positive=False)

    persisted = 0
    for i, (_, row) in enumerate(df.iterrows()):
        ml_score = float(scores[i])
        data_conf = float(row.get("feature_confidence") or 0.0)
        cat_blocks = bool(row.get("trade_policy_block") or False)
        cat_reduces = bool(row.get("trade_policy_reduce") or False)
        adv = build_advisory(
            decision_id=str(row.get("decision_id") or ""),
            ml_score=ml_score,
            data_confidence=data_conf,
            catalyst_blocks=cat_blocks,
            catalyst_reduces=cat_reduces,
            n_training_rows=n_training_rows,
            min_training_rows=min_training_rows,
        )
        explanation = _build_explanation(
            row=row, ml_score=ml_score,
            top_pos=top_pos, top_neg=top_neg,
            data_conf=data_conf,
            cat_blocks=cat_blocks, cat_reduces=cat_reduces,
        )
        if persist:
            _persist_row(
                session,
                model_run_id=model_run_id,
                row=row, ml_score=ml_score,
                advisory=adv, explanation=explanation,
            )
            persisted += 1
    if persist:
        session.commit()
    return ShadowScoringResult(
        model_run_id=model_run_id,
        n_scored=len(df), n_persisted=persisted,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
def _persist_row(
    session: Session, *,
    model_run_id: str, row: pd.Series,
    ml_score: float, advisory, explanation: dict[str, Any],
) -> None:
    source = str(row.get("source_type") or "real")
    decision_id = row.get("decision_id")
    replay_decision_id = (
        decision_id if source == "replay" else None
    )
    real_decision_id = (
        decision_id if source == "real" else None
    )
    session.execute(text("""
        INSERT INTO ml_shadow_prediction
          (id, model_run_id, decision_id, replay_decision_id, source_type,
           symbol, as_of_date, decision_ts, engine, original_decision,
           engine_confidence, ml_score, ml_confidence, ml_action,
           ml_reason_codes, baseline_action, actual_outcome,
           outcome_available, evaluation)
        VALUES
          (:id, :mrid, :did, :rdid, :src,
           :sym, :asof, :ts, :eng, :orig,
           :econf, :mlscore, :mlconf, :mlact,
           CAST(:rc AS jsonb), :bact, :outcome, :oavail,
           CAST(:ev AS jsonb))
    """), {
        "id":    str(uuid.uuid4()),
        "mrid":  model_run_id,
        "did":   _uuid_or_none(real_decision_id),
        "rdid":  _uuid_or_none(replay_decision_id),
        "src":   source,
        "sym":   str(row.get("symbol") or ""),
        "asof":  pd.to_datetime(row.get("as_of_date")).date()
                 if row.get("as_of_date") is not None else None,
        "ts":    pd.to_datetime(row.get("decision_ts"))
                 if row.get("decision_ts") is not None else None,
        "eng":   str(row.get("engine") or ""),
        "orig":  str(row.get("action") or ""),
        "econf": float(row.get("feature_confidence") or 0.0),
        "mlscore": ml_score,
        "mlconf":  advisory.ml_confidence,
        "mlact":   advisory.suggested_action.value,
        "rc":    json.dumps(advisory.ml_reason_codes, default=str),
        "bact":  None,
        "outcome": _num(row.get("fwd_ret_5d")),
        "oavail":  bool(pd.notna(row.get("fwd_ret_5d"))),
        "ev":    json.dumps(explanation, default=str),
    })


def _build_explanation(
    *, row: pd.Series, ml_score: float,
    top_pos: list[tuple[str, float]],
    top_neg: list[tuple[str, float]],
    data_conf: float,
    cat_blocks: bool, cat_reduces: bool,
) -> dict[str, Any]:
    caveats: list[str] = []
    if data_conf < 0.3:
        caveats.append(f"data_confidence {data_conf:.2f} below 0.3")
    if cat_blocks:
        caveats.append("catalyst policy: block new entry")
    if cat_reduces:
        caveats.append("catalyst policy: reduce size")
    return {
        "ml_score": round(ml_score, 4),
        "top_positive_features": [
            {"feature": f, "coef": round(float(v), 6)} for f, v in top_pos[:5]
        ],
        "top_negative_features": [
            {"feature": f, "coef": round(float(v), 6)} for f, v in top_neg[:5]
        ],
        "caveats": caveats,
        "source_type": str(row.get("source_type") or "real"),
    }


def _top_drivers(
    d: dict[str, float], *, positive: bool, k: int = 5,
) -> list[tuple[str, float]]:
    if not d:
        return []
    items = [(k_, float(v)) for k_, v in d.items()]
    if positive:
        items.sort(key=lambda kv: -kv[1])
    else:
        items.sort(key=lambda kv: kv[1])
    return items[:k]


def _uuid_or_none(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    s = str(v)
    return s if len(s) >= 32 else None


def _num(v: Any) -> float | None:
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None
