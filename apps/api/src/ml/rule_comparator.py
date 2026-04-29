"""Phase 11T.3 - rule comparator (pure-fn).

Compares deterministic outcome (`outcome_class` from
`paper_observation_label`) against the model's bucket assignment.
Emits counts and rates only. NEVER ranks one against the other.
Output uses neutral "agreement" / "disagreement" framing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence


SHADOW_LOW = "SHADOW_LOW"
SHADOW_MID = "SHADOW_MID"
SHADOW_HIGH = "SHADOW_HIGH"

# Frozen comparison categories.
CAT_AGREEMENT_HIGH = "agreement_high"
CAT_AGREEMENT_LOW = "agreement_low"
CAT_AGREEMENT_MID = "agreement_mid"
CAT_DIS_DET_POS_MODEL_LOW = "disagreement_det_pos_model_low"
CAT_DIS_DET_NEG_MODEL_HIGH = "disagreement_det_neg_model_high"
CAT_DIS_OTHER = "disagreement_other"

ALL_CATEGORIES: tuple[str, ...] = (
    CAT_AGREEMENT_HIGH, CAT_AGREEMENT_LOW, CAT_AGREEMENT_MID,
    CAT_DIS_DET_POS_MODEL_LOW, CAT_DIS_DET_NEG_MODEL_HIGH,
    CAT_DIS_OTHER,
)


@dataclass(frozen=True)
class RuleComparison:
    n_total: int
    n_agreement: int
    n_disagreement: int
    by_category: dict[str, int]
    by_qualified_axis: dict[str, int]
    agreement_rate: float
    deterministic_accepted_model_low: int
    deterministic_rejected_model_high: int


def categorize(
    deterministic_outcome: str | None,
    model_bucket: str | None,
) -> str:
    """Return one of `ALL_CATEGORIES`. Pure-fn."""
    if deterministic_outcome == "positive" and model_bucket == SHADOW_HIGH:
        return CAT_AGREEMENT_HIGH
    if deterministic_outcome == "negative" and model_bucket == SHADOW_LOW:
        return CAT_AGREEMENT_LOW
    if deterministic_outcome == "neutral" and model_bucket == SHADOW_MID:
        return CAT_AGREEMENT_MID
    if deterministic_outcome == "positive" and model_bucket == SHADOW_LOW:
        return CAT_DIS_DET_POS_MODEL_LOW
    if deterministic_outcome == "negative" and model_bucket == SHADOW_HIGH:
        return CAT_DIS_DET_NEG_MODEL_HIGH
    return CAT_DIS_OTHER


def compare_model_vs_rule(
    rows: Sequence[dict[str, Any]],
) -> RuleComparison:
    """Take an iterable of scored row dicts. Each must include
    `deterministic_outcome` and `model_bucket`. May include
    `deterministic_qualified` (boolean). Returns frozen counts."""
    by_cat: dict[str, int] = {c: 0 for c in ALL_CATEGORIES}
    qualified_axis: dict[str, int] = {
        "qualified_high": 0, "qualified_mid": 0, "qualified_low": 0,
        "rejected_high": 0, "rejected_mid": 0, "rejected_low": 0,
    }
    n_agree = 0
    n_dis = 0
    det_acc_model_low = 0
    det_rej_model_high = 0
    n_total = 0

    for r in rows:
        n_total += 1
        det = r.get("deterministic_outcome")
        bucket = r.get("model_bucket")
        cat = categorize(det, bucket)
        by_cat[cat] = by_cat.get(cat, 0) + 1
        if cat in (
            CAT_AGREEMENT_HIGH,
            CAT_AGREEMENT_LOW,
            CAT_AGREEMENT_MID,
        ):
            n_agree += 1
        else:
            n_dis += 1

        qualified = bool(r.get("deterministic_qualified", False))
        b_short = (
            "high" if bucket == SHADOW_HIGH
            else "low" if bucket == SHADOW_LOW
            else "mid"
        )
        key = ("qualified_" if qualified else "rejected_") + b_short
        qualified_axis[key] = qualified_axis.get(key, 0) + 1

        if qualified and bucket == SHADOW_LOW:
            det_acc_model_low += 1
        if (not qualified) and bucket == SHADOW_HIGH:
            det_rej_model_high += 1

    rate = (n_agree / n_total) if n_total > 0 else 0.0
    return RuleComparison(
        n_total=n_total,
        n_agreement=n_agree,
        n_disagreement=n_dis,
        by_category=by_cat,
        by_qualified_axis=qualified_axis,
        agreement_rate=round(rate, 4),
        deterministic_accepted_model_low=det_acc_model_low,
        deterministic_rejected_model_high=det_rej_model_high,
    )
