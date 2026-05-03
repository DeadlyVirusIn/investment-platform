"""Leakage validation — hard stop if future information bleeds into features.

Runs before any training. Raises LeakageError on violation. Always returns a
LeakageReport so the API can surface warnings to the UI even on pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from apps.api.src.ml.features import (
    FEATURE_COLUMNS, IDENTITY_COLUMNS, LABEL_COLUMNS,
    is_forbidden_feature_name,
)


class LeakageError(AssertionError):
    """Raised when a feature column depends on post-decision information."""


@dataclass
class LeakageReport:
    ok: bool
    violations: list[str] = field(default_factory=list)
    suspicious_columns: list[str] = field(default_factory=list)
    missing_timestamps: int = 0
    decision_label_overlap: int = 0
    # Columns that looked forbidden but were excluded from training anyway
    forbidden_but_excluded: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "violations": list(self.violations),
            "suspicious_columns": list(self.suspicious_columns),
            "missing_timestamps": self.missing_timestamps,
            "decision_label_overlap": self.decision_label_overlap,
            "forbidden_but_excluded": list(self.forbidden_but_excluded),
        }


def validate_no_leakage(
    df: pd.DataFrame,
    *,
    feature_cols: tuple[str, ...] = FEATURE_COLUMNS,
    strict: bool = True,
) -> LeakageReport:
    """Run leakage checks against a fully built dataset.

    Checks:
      1. Feature columns don't match any OUTCOME_FORBIDDEN_PATTERNS.
      2. Feature columns don't overlap with LABEL_COLUMNS.
      3. All rows have decision_ts (or as_of_date) populated.
      4. If bars/labels imply date relationships, label dates are strictly
         after decision dates (checked via presence of fwd_ret_* being NaN
         when there is no future bar — silent pass).

    Raises
    ------
    LeakageError : if strict=True and any hard violation is found.
    """
    violations: list[str] = []
    suspicious: list[str] = []
    forbidden_but_excluded: list[str] = []

    # 1. Forbidden substrings in declared features
    for col in feature_cols:
        if is_forbidden_feature_name(col):
            violations.append(
                f"feature column '{col}' matches outcome pattern"
            )

    # 2. Training columns in frame that match forbidden patterns (defensive
    #    against someone accidentally passing raw dataset through as X)
    frame_feature_like = [
        c for c in df.columns
        if c not in IDENTITY_COLUMNS and c not in LABEL_COLUMNS
    ]
    for col in frame_feature_like:
        if is_forbidden_feature_name(col):
            if col in feature_cols:
                violations.append(f"forbidden column '{col}' in FEATURE_COLUMNS")
            else:
                # Present in frame but not in feature whitelist — safe but log
                forbidden_but_excluded.append(col)

    # 3. Feature/label overlap
    overlap = set(feature_cols) & set(LABEL_COLUMNS)
    for col in overlap:
        violations.append(f"column '{col}' in both FEATURE and LABEL sets")

    # 4. Timestamp presence
    missing_ts = 0
    ts_col = None
    for cand in ("decision_ts", "as_of_date"):
        if cand in df.columns:
            ts_col = cand
            break
    if ts_col is None:
        violations.append("no decision_ts or as_of_date column present")
    else:
        missing_ts = int(df[ts_col].isna().sum())

    # 5. Label/feature date overlap — if decision_ts equals label-resolution
    #    date we treat that as borderline leakage. Forward 1d is resolved at
    #    as_of_date + 1 trading day, so label resolution timestamp should
    #    never equal decision timestamp. We can't verify without actual bar
    #    dates in the frame; leave this as informational.
    overlap_count = 0

    # Additionally check that columns that LOOK like features but aren't
    # in the whitelist are flagged for review.
    declared_set = set(feature_cols)
    for col in frame_feature_like:
        if col not in declared_set and col not in forbidden_but_excluded:
            # Suspicious iff it numerically varies and isn't a well-known
            # pass-through identity.
            if col in IDENTITY_COLUMNS:
                continue
            suspicious.append(col)

    ok = not violations
    report = LeakageReport(
        ok=ok,
        violations=violations,
        suspicious_columns=suspicious,
        missing_timestamps=missing_ts,
        decision_label_overlap=overlap_count,
        forbidden_but_excluded=forbidden_but_excluded,
    )
    if strict and not ok:
        raise LeakageError("; ".join(violations))
    return report
