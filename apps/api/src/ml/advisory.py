"""Advisory output + Engine C status.

ML outputs here are ADVISORY. They do not change paper trading unless
`ML_CAN_AFFECT_TRADES` is explicitly toggled in config. This module is the
single boundary between model scores and engine logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd

from apps.api.src.ml.models import TrainedModel


class AdvisoryAction(str, Enum):
    ACCEPT           = "accept"
    REDUCE           = "reduce"
    AVOID            = "avoid"
    NEEDS_MORE_DATA  = "needs_more_data"


@dataclass
class Advisory:
    decision_id: str | None
    ml_score: float                            # 0..1 probability trade profitable
    ml_confidence: float                       # 0..1 heuristic confidence
    suggested_action: AdvisoryAction
    ml_reason_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "ml_score": round(self.ml_score, 4),
            "ml_confidence": round(self.ml_confidence, 4),
            "suggested_action": self.suggested_action.value,
            "ml_reason_codes": list(self.ml_reason_codes),
        }


def build_advisory(
    *,
    decision_id: str | None,
    ml_score: float,
    data_confidence: float,
    catalyst_blocks: bool,
    catalyst_reduces: bool,
    n_training_rows: int,
    min_training_rows: int,
) -> Advisory:
    """Combine raw ml score + reliability + catalyst into advisory action."""
    reasons: list[str] = []

    # Gate 1: training size
    if n_training_rows < min_training_rows:
        reasons.append(f"training_rows {n_training_rows} < {min_training_rows}")
        return Advisory(
            decision_id=decision_id,
            ml_score=float(ml_score),
            ml_confidence=0.0,
            suggested_action=AdvisoryAction.NEEDS_MORE_DATA,
            ml_reason_codes=reasons,
        )

    # Gate 2: data reliability
    if data_confidence < 0.3:
        reasons.append(f"data_confidence {data_confidence:.2f} below 0.3")
        return Advisory(
            decision_id=decision_id,
            ml_score=float(ml_score),
            ml_confidence=float(data_confidence),
            suggested_action=AdvisoryAction.AVOID,
            ml_reason_codes=reasons,
        )

    # Gate 3: catalyst overlay
    if catalyst_blocks:
        reasons.append("catalyst blocks new entry")
        return Advisory(
            decision_id=decision_id,
            ml_score=float(ml_score),
            ml_confidence=float(data_confidence),
            suggested_action=AdvisoryAction.AVOID,
            ml_reason_codes=reasons,
        )

    # ML-first decision
    if ml_score >= 0.65:
        action = AdvisoryAction.ACCEPT
        reasons.append(f"ml_score {ml_score:.2f} ≥ 0.65")
    elif ml_score <= 0.35:
        action = AdvisoryAction.AVOID
        reasons.append(f"ml_score {ml_score:.2f} ≤ 0.35")
    else:
        action = AdvisoryAction.REDUCE
        reasons.append(f"ml_score {ml_score:.2f} in middle band")

    if catalyst_reduces and action == AdvisoryAction.ACCEPT:
        action = AdvisoryAction.REDUCE
        reasons.append("catalyst reduces size")

    # Heuristic confidence = data_confidence * (how far from 0.5)
    margin = abs(ml_score - 0.5) * 2.0
    conf = max(0.0, min(1.0, data_confidence * margin))

    return Advisory(
        decision_id=decision_id,
        ml_score=float(ml_score),
        ml_confidence=float(conf),
        suggested_action=action,
        ml_reason_codes=reasons,
    )


def build_advisories_from_model(
    df: pd.DataFrame, model: TrainedModel,
    *,
    decision_id_col: str = "decision_id",
    data_conf_col: str = "feature_confidence",
    trade_policy_block_col: str = "trade_policy_block",
    trade_policy_reduce_col: str = "trade_policy_reduce",
    n_training_rows: int,
    min_training_rows: int,
) -> list[Advisory]:
    """Batch-build advisories for a set of decisions."""
    scores = model.predict_proba(df)
    out: list[Advisory] = []
    for i in range(len(df)):
        row = df.iloc[i]
        out.append(build_advisory(
            decision_id=str(row.get(decision_id_col) or ""),
            ml_score=float(scores[i]),
            data_confidence=float(row.get(data_conf_col) or 0.0),
            catalyst_blocks=bool(row.get(trade_policy_block_col) or False),
            catalyst_reduces=bool(row.get(trade_policy_reduce_col) or False),
            n_training_rows=n_training_rows,
            min_training_rows=min_training_rows,
        ))
    return out


# -------------------------------------------------------------------------
# Engine C status
# -------------------------------------------------------------------------

class EngineCStatus(str, Enum):
    DISABLED_INSUFFICIENT_DATA = "disabled_insufficient_data"
    DISABLED_LEAKAGE           = "disabled_leakage_detected"
    ADVISORY_ONLY              = "advisory_only"
    ACTIVE_CANDIDATE           = "active_candidate"
    DISABLED_BASELINE_BEATS_ML = "disabled_baseline_beats_ml"


@dataclass
class EngineCStatusReport:
    status: EngineCStatus
    reason: str
    training_rows: int
    latest_eval_score: float | None
    min_rows_required: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_c_ml_status": self.status.value,
            "engine_c_ml_reason": self.reason,
            "engine_c_training_rows": self.training_rows,
            "engine_c_latest_eval_score": self.latest_eval_score,
            "min_rows_required": self.min_rows_required,
        }


def engine_c_status(
    *,
    n_rows: int,
    leakage_ok: bool,
    baseline_best_sharpe: float,
    ml_test_sharpe: float | None,
    min_training_rows: int,
) -> EngineCStatusReport:
    """Determine where Engine C sits in its rollout lifecycle."""
    if not leakage_ok:
        return EngineCStatusReport(
            status=EngineCStatus.DISABLED_LEAKAGE,
            reason="leakage validation failed",
            training_rows=n_rows,
            latest_eval_score=None,
            min_rows_required=min_training_rows,
        )
    if n_rows < min_training_rows:
        return EngineCStatusReport(
            status=EngineCStatus.DISABLED_INSUFFICIENT_DATA,
            reason=f"{n_rows} < {min_training_rows} labelled decisions",
            training_rows=n_rows,
            latest_eval_score=None,
            min_rows_required=min_training_rows,
        )
    if ml_test_sharpe is None:
        return EngineCStatusReport(
            status=EngineCStatus.ADVISORY_ONLY,
            reason="no ML evaluation recorded yet — advisory only",
            training_rows=n_rows,
            latest_eval_score=None,
            min_rows_required=min_training_rows,
        )
    if ml_test_sharpe <= baseline_best_sharpe:
        return EngineCStatusReport(
            status=EngineCStatus.DISABLED_BASELINE_BEATS_ML,
            reason=(
                f"ml test sharpe {ml_test_sharpe:.3f} ≤ "
                f"baseline {baseline_best_sharpe:.3f}"
            ),
            training_rows=n_rows,
            latest_eval_score=ml_test_sharpe,
            min_rows_required=min_training_rows,
        )
    return EngineCStatusReport(
        status=EngineCStatus.ACTIVE_CANDIDATE,
        reason=(
            f"ml test sharpe {ml_test_sharpe:.3f} > "
            f"baseline {baseline_best_sharpe:.3f}"
        ),
        training_rows=n_rows,
        latest_eval_score=ml_test_sharpe,
        min_rows_required=min_training_rows,
    )
