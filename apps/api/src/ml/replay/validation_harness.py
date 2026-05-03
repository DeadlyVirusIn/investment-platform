"""Replay validation harness — readiness gate + coverage-aware verdict.

Returns a single readiness status + blockers + recommendation. Never
mutates ML_DATASET_INCLUDE_REPLAY or ML_REPLAY_WEIGHT. Advisory only.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.data.catalysts.backfill.coverage import (
    build_coverage_report,
)
from apps.api.src.ml.replay.comparator import (
    ComparisonResult, compare_replay_to_real,
)
from apps.api.src.ml.replay.leakage import (
    ReplayLeakageReport, validate_replay_leakage,
)


class ReplayReadiness(str, Enum):
    NOT_READY_NO_CATALYST_HISTORY = "NOT_READY_NO_CATALYST_HISTORY"
    NOT_READY_LOW_COVERAGE        = "NOT_READY_LOW_COVERAGE"
    NOT_READY_LEAKAGE_RISK        = "NOT_READY_LEAKAGE_RISK"
    NOT_READY_LOW_AGREEMENT       = "NOT_READY_LOW_AGREEMENT"
    CALIBRATION_ONLY              = "CALIBRATION_ONLY"
    READY_FOR_WEIGHTED_TEST       = "READY_FOR_WEIGHTED_TEST"


@dataclass
class ReplayReadinessReport:
    status: ReplayReadiness
    blockers: list[str] = field(default_factory=list)
    recommended_next_action: str = ""
    coverage_summary: dict[str, Any] = field(default_factory=dict)
    validation_summary: dict[str, Any] = field(default_factory=dict)
    leakage_summary: dict[str, Any] = field(default_factory=dict)
    safe_config_recommendation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "blockers": list(self.blockers),
            "recommended_next_action": self.recommended_next_action,
            "coverage_summary": self.coverage_summary,
            "validation_summary": self.validation_summary,
            "leakage_summary": self.leakage_summary,
            "safe_config_recommendation": self.safe_config_recommendation,
        }


# ---------------------------------------------------------------------------
def replay_training_readiness(
    session: Session, *,
    replay_run_id: str | None = None,
    coverage_symbols: list[str] | None = None,
    coverage_start: dt.date | None = None,
    coverage_end: dt.date | None = None,
    min_comparable: int = 100,
    min_action_agreement: float = 0.85,
    max_confidence_delta: float = 0.15,
    min_catalyst_coverage: float = 0.5,
) -> ReplayReadinessReport:
    # --- resolve run ---
    if replay_run_id is None:
        row = session.execute(text("""
            SELECT id::text AS id FROM ml_replay_run
             WHERE status = 'completed'
             ORDER BY created_at DESC
             LIMIT 1
        """)).mappings().first()
        replay_run_id = str(row["id"]) if row else None

    # --- coverage ---
    cov: dict[str, Any] = {}
    cov_tier = "weak"
    cov_ratio = 0.0
    known_ratio = 0.0
    if coverage_symbols and coverage_start and coverage_end:
        rep = build_coverage_report(
            session, coverage_symbols,
            window_start=coverage_start, window_end=coverage_end,
        )
        cov = rep.to_dict()
        cov_tier = rep.global_quality_tier
        cov_ratio = rep.pct_symbol_month_coverage
        known_ratio = rep.pct_known_at_coverage

    # --- leakage + comparison (only if run_id present) ---
    leakage: ReplayLeakageReport | None = None
    comp: ComparisonResult | None = None
    if replay_run_id and not replay_run_id.startswith("dryrun-"):
        leakage = validate_replay_leakage(
            session, replay_run_id, strict=False,
        )
        comp = compare_replay_to_real(session, replay_run_id)

    blockers: list[str] = []
    status = ReplayReadiness.CALIBRATION_ONLY

    # Order matters — leakage first (hard stop)
    if leakage and not leakage.ok:
        status = ReplayReadiness.NOT_READY_LEAKAGE_RISK
        blockers.extend(leakage.violations)
    elif not cov or cov.get("total_news", 0) == 0:
        status = ReplayReadiness.NOT_READY_NO_CATALYST_HISTORY
        blockers.append(
            "no news rows in requested coverage window — backfill required"
        )
    elif cov_ratio < min_catalyst_coverage:
        status = ReplayReadiness.NOT_READY_LOW_COVERAGE
        blockers.append(
            f"symbol-month coverage {cov_ratio:.0%} < "
            f"{min_catalyst_coverage:.0%} gate"
        )
    elif comp is None:
        status = ReplayReadiness.CALIBRATION_ONLY
        blockers.append("no replay run selected — cannot compare")
    else:
        if comp.comparable_decisions < min_comparable:
            status = ReplayReadiness.CALIBRATION_ONLY
            blockers.append(
                f"only {comp.comparable_decisions} comparable decisions "
                f"< {min_comparable} preferred"
            )
        elif comp.action_agreement_rate < min_action_agreement:
            status = ReplayReadiness.NOT_READY_LOW_AGREEMENT
            blockers.append(
                f"action agreement "
                f"{comp.action_agreement_rate:.0%} < "
                f"{min_action_agreement:.0%}"
            )
        elif comp.avg_confidence_delta > max_confidence_delta:
            status = ReplayReadiness.NOT_READY_LOW_AGREEMENT
            blockers.append(
                f"avg confidence delta "
                f"{comp.avg_confidence_delta:.3f} > "
                f"{max_confidence_delta:.2f}"
            )
        else:
            # Need both solid coverage AND agreement for WEIGHTED_TEST
            if cov_tier == "excellent" and known_ratio >= 0.5:
                status = ReplayReadiness.READY_FOR_WEIGHTED_TEST
            else:
                status = ReplayReadiness.CALIBRATION_ONLY
                blockers.append(
                    "coverage not 'excellent' with known_at ≥ 50% — "
                    "run additional backfill before training weight > 0"
                )

    recommendation, safe_cfg = _recommendation_and_cfg(status)

    return ReplayReadinessReport(
        status=status,
        blockers=blockers,
        recommended_next_action=recommendation,
        coverage_summary=cov,
        validation_summary=(comp.to_dict() if comp else {}),
        leakage_summary=(leakage.to_dict() if leakage else {}),
        safe_config_recommendation=safe_cfg,
    )


def _recommendation_and_cfg(
    status: ReplayReadiness,
) -> tuple[str, dict[str, Any]]:
    default_cfg = {
        "ML_DATASET_INCLUDE_REPLAY": False,
        "ML_REPLAY_WEIGHT": 0.0,
    }
    if status == ReplayReadiness.NOT_READY_LEAKAGE_RISK:
        return (
            "fix leakage before anything else — replay must stay excluded",
            default_cfg,
        )
    if status == ReplayReadiness.NOT_READY_NO_CATALYST_HISTORY:
        return (
            "run catalyst backfill job for the target date window; "
            "keep replay excluded from ML",
            default_cfg,
        )
    if status == ReplayReadiness.NOT_READY_LOW_COVERAGE:
        return (
            "increase backfill depth or widen providers; symbol-month "
            "coverage must reach 50% before reassessment",
            default_cfg,
        )
    if status == ReplayReadiness.NOT_READY_LOW_AGREEMENT:
        return (
            "selector parity insufficient — audit replayer engine "
            "logic against production selector, then re-run comparison",
            default_cfg,
        )
    if status == ReplayReadiness.CALIBRATION_ONLY:
        return (
            "replay is safe for CALIBRATION ONLY — use for sanity checks "
            "and pattern directionality; keep ML_DATASET_INCLUDE_REPLAY=false",
            default_cfg,
        )
    # READY
    return (
        "one-off weighted combined dataset experiment allowed: set "
        "ML_DATASET_INCLUDE_REPLAY=true and ML_REPLAY_WEIGHT=0.25 for "
        "a SINGLE research run; compare real-only vs combined diagnostics",
        {"ML_DATASET_INCLUDE_REPLAY": True, "ML_REPLAY_WEIGHT": 0.25},
    )
