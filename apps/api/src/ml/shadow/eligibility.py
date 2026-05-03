"""Shadow training eligibility gate — runs BEFORE any fit() call.

Any failed gate → `SKIPPED_*` status + exact blockers. Training code must
short-circuit on eligibility.ok=False.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd

from apps.api.src.ml.report import build_feature_health
from apps.api.src.ml.splits import enough_data_for_ml
from apps.api.src.ml.validation import validate_no_leakage


class EligibilityStatus(str, Enum):
    ELIGIBLE                        = "ELIGIBLE"
    SKIPPED_INSUFFICIENT_DATA       = "SKIPPED_INSUFFICIENT_DATA"
    SKIPPED_LEAKAGE_RISK            = "SKIPPED_LEAKAGE_RISK"
    SKIPPED_LOW_FEATURE_HEALTH      = "SKIPPED_LOW_FEATURE_HEALTH"
    SKIPPED_REPLAY_NOT_READY        = "SKIPPED_REPLAY_NOT_READY"
    SKIPPED_NO_LABELS               = "SKIPPED_NO_LABELS"


@dataclass
class EligibilityReport:
    ok: bool
    status: EligibilityStatus
    blockers: list[str] = field(default_factory=list)
    row_count: int = 0
    labeled_row_count: int = 0
    tier: str = "diagnostics_only"
    leakage_summary: dict[str, Any] = field(default_factory=dict)
    feature_health_summary: dict[str, Any] = field(default_factory=dict)
    replay_readiness_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status.value,
            "blockers": list(self.blockers),
            "row_count": self.row_count,
            "labeled_row_count": self.labeled_row_count,
            "tier": self.tier,
            "leakage_summary": self.leakage_summary,
            "feature_health_summary": self.feature_health_summary,
            "replay_readiness_status": self.replay_readiness_status,
        }


def evaluate_eligibility(
    df: pd.DataFrame,
    *,
    min_training_rows: int,
    label_col: str = "label_win_5d",
    replay_readiness_status: str | None = None,
    dataset_source: str = "real",
) -> EligibilityReport:
    """Evaluate every gate. Returns report; never raises."""
    blockers: list[str] = []
    status = EligibilityStatus.ELIGIBLE

    # --- Replay safety gate ---
    if dataset_source == "combined":
        allowed = replay_readiness_status == "READY_FOR_WEIGHTED_TEST"
        if not allowed:
            status = EligibilityStatus.SKIPPED_REPLAY_NOT_READY
            blockers.append(
                f"dataset_source=combined but replay readiness status "
                f"is '{replay_readiness_status or 'unknown'}' "
                f"(need READY_FOR_WEIGHTED_TEST)"
            )

    # --- Basic counts ---
    n_rows = int(len(df))
    if label_col in df.columns:
        n_labeled = int(df[label_col].notna().sum())
    else:
        n_labeled = 0

    # --- Labels present? ---
    if n_labeled == 0 and status == EligibilityStatus.ELIGIBLE:
        status = EligibilityStatus.SKIPPED_NO_LABELS
        blockers.append(
            f"no non-null labels in '{label_col}' — attach outcomes first"
        )

    # --- Leakage ---
    leakage = validate_no_leakage(df, strict=False) if n_rows else None
    leakage_dict = leakage.to_dict() if leakage else {}
    if leakage is not None and not leakage.ok \
       and status == EligibilityStatus.ELIGIBLE:
        status = EligibilityStatus.SKIPPED_LEAKAGE_RISK
        blockers.extend(leakage.violations)

    # --- Tier / row-count gate ---
    gate = enough_data_for_ml(n_labeled, min_for_models=min_training_rows)
    tier = gate["tier"]
    if not gate["can_train"] and status == EligibilityStatus.ELIGIBLE:
        status = EligibilityStatus.SKIPPED_INSUFFICIENT_DATA
        blockers.append(
            f"labeled rows {n_labeled} < min {min_training_rows} "
            f"(tier={tier})"
        )

    # --- Feature health ---
    fh = build_feature_health(df).to_dict() if n_rows else {}
    if fh and status == EligibilityStatus.ELIGIBLE:
        cat_cov = float(fh.get("catalyst_coverage", 0.0) or 0.0)
        if cat_cov < 0.1:
            # Advisory only — don't hard-block for MVP on catalyst weakness
            blockers.append(
                f"catalyst coverage {cat_cov:.0%} — features may be weak"
            )
        health_warnings = fh.get("warnings") or []
        # Soft check: if EVERY bucket of feature_confidence is zero it's bad
        buckets = fh.get("feature_confidence_bucket_counts") or {}
        total_bucket = sum(int(v) for v in buckets.values())
        if total_bucket == 0 and n_labeled > 0:
            status = EligibilityStatus.SKIPPED_LOW_FEATURE_HEALTH
            blockers.append("feature_confidence column empty — pipeline bug?")
        blockers.extend([f"feature_health: {w}" for w in health_warnings])

    ok = (status == EligibilityStatus.ELIGIBLE)
    return EligibilityReport(
        ok=ok, status=status, blockers=blockers,
        row_count=n_rows, labeled_row_count=n_labeled,
        tier=tier, leakage_summary=leakage_dict,
        feature_health_summary={
            # Keep snapshot compact — don't dump giant missing_rate map
            "catalyst_coverage": fh.get("catalyst_coverage"),
            "earnings_coverage": fh.get("earnings_coverage"),
            "label_availability": fh.get("label_availability"),
            "warnings": fh.get("warnings"),
        } if fh else {},
        replay_readiness_status=replay_readiness_status,
    )
