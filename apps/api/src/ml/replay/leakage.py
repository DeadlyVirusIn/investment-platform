"""Replay leakage validator — hard stop if any future information leaks
into a decision row or if any label resolves on/before its decision date.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


FORBIDDEN_KEYS_IN_FEATURES = (
    "forward_return", "fwd_ret_", "exit_price",
    "realized_", "win_label", "max_adverse", "max_favorable",
    "outcome", "label_", "pnl",
)


class ReplayLeakageError(AssertionError):
    """Raised when replay rows contain leakage."""


@dataclass
class ReplayLeakageReport:
    ok: bool
    run_id: str
    n_decisions: int
    n_outcomes: int
    violations: list[str] = field(default_factory=list)
    suspicious_feature_keys: list[str] = field(default_factory=list)
    feature_ts_after_decision: int = 0
    catalyst_published_after_decision: int = 0
    label_start_on_or_before_decision: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "run_id": self.run_id,
            "n_decisions": self.n_decisions,
            "n_outcomes": self.n_outcomes,
            "violations": list(self.violations),
            "suspicious_feature_keys": list(self.suspicious_feature_keys),
            "feature_ts_after_decision": self.feature_ts_after_decision,
            "catalyst_published_after_decision":
                self.catalyst_published_after_decision,
            "label_start_on_or_before_decision":
                self.label_start_on_or_before_decision,
        }


def validate_replay_leakage(
    session: Session, run_id: str, *, strict: bool = False,
) -> ReplayLeakageReport:
    """Run all replay-specific leakage checks for a single run."""
    n_decisions = int(session.execute(text("""
        SELECT COUNT(*) FROM ml_replay_decision WHERE replay_run_id = :r
    """), {"r": run_id}).scalar() or 0)
    n_outcomes = int(session.execute(text("""
        SELECT COUNT(*)
        FROM ml_replay_outcome o
        JOIN ml_replay_decision d ON d.id = o.replay_decision_id
        WHERE d.replay_run_id = :r
    """), {"r": run_id}).scalar() or 0)

    violations: list[str] = []
    suspicious: list[str] = []
    feat_ts_after = 0
    cat_after = 0
    label_overlap = 0

    # --- 1. Forbidden keys in feature blobs ---
    rows = session.execute(text("""
        SELECT features
        FROM ml_replay_decision
        WHERE replay_run_id = :r
        LIMIT 100
    """), {"r": run_id}).mappings().all()
    for r in rows:
        feats = r.get("features") or {}
        if not isinstance(feats, dict):
            continue
        for k in feats.keys():
            low = str(k).lower()
            if any(p in low for p in FORBIDDEN_KEYS_IN_FEATURES):
                suspicious.append(k)
    suspicious = sorted(set(suspicious))
    if suspicious:
        violations.append(
            f"forbidden keys in features blob: {suspicious[:5]}"
        )

    # --- 2. Feature-timestamp checks — provenance.price_bar_last ---
    bad = session.execute(text("""
        SELECT COUNT(*)
        FROM ml_replay_decision
        WHERE replay_run_id = :r
          AND (provenance ->> 'feature_timestamps') IS NOT NULL
          AND (
            (provenance -> 'feature_timestamps' ->> 'price_bar_last')::date
            > as_of_date
          )
    """), {"r": run_id}).scalar()
    feat_ts_after = int(bad or 0)
    if feat_ts_after > 0:
        violations.append(
            f"{feat_ts_after} rows have price_bar_last > as_of_date"
        )

    # --- 3. Catalyst headlines published after decision_ts ---
    # Look into catalyst.headlines[].published_at
    overshoot = session.execute(text("""
        WITH x AS (
          SELECT d.id,
                 d.decision_ts,
                 (jsonb_array_elements(d.catalyst -> 'headlines')
                   ->> 'published_at')::timestamptz AS ts
          FROM ml_replay_decision d
          WHERE d.replay_run_id = :r
            AND jsonb_typeof(d.catalyst -> 'headlines') = 'array'
        )
        SELECT COUNT(*) FROM x WHERE ts > decision_ts
    """), {"r": run_id}).scalar()
    cat_after = int(overshoot or 0)
    if cat_after > 0:
        violations.append(
            f"{cat_after} catalyst headlines published after decision_ts"
        )

    # --- 4. Label start date must be AFTER decision date ---
    overlap = session.execute(text("""
        SELECT COUNT(*)
        FROM ml_replay_outcome o
        JOIN ml_replay_decision d ON d.id = o.replay_decision_id
        WHERE d.replay_run_id = :r
          AND o.label_start_date IS NOT NULL
          AND o.label_start_date <= d.as_of_date
    """), {"r": run_id}).scalar()
    label_overlap = int(overlap or 0)
    if label_overlap > 0:
        violations.append(
            f"{label_overlap} outcomes have label_start ≤ as_of_date"
        )

    ok = not violations
    report = ReplayLeakageReport(
        ok=ok, run_id=run_id,
        n_decisions=n_decisions, n_outcomes=n_outcomes,
        violations=violations,
        suspicious_feature_keys=suspicious,
        feature_ts_after_decision=feat_ts_after,
        catalyst_published_after_decision=cat_after,
        label_start_on_or_before_decision=label_overlap,
    )
    if strict and not ok:
        raise ReplayLeakageError("; ".join(violations))
    return report
