"""Alerting — pure rules over governance state.

NEVER mutates trading state, NEVER promotes ML, NEVER changes risk
parameters. Emits structured alert dicts consumed by Ops UI / nightly
job logs / future notification channels.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# Severity ranks
SEV_INFO = "INFO"
SEV_WARN = "WARN"
SEV_CRIT = "CRITICAL"
_RANK = {SEV_INFO: 0, SEV_WARN: 1, SEV_CRIT: 2}


# Trigger thresholds — keep aligned with engine_b_policy + drift_monitor
ENGINE_B_SHARPE_WARN = -0.30
ENGINE_B_SHARPE_CRIT = -0.60
ML_DELTA_SHARPE_WARN = 0.0           # ML failing to add edge
ML_DELTA_SHARPE_CRIT = -0.5          # ML actively hurting
ECE_WARN = 0.10
ECE_CRIT = 0.20


@dataclass
class Alert:
    code: str
    severity: str
    title: str
    detail: str
    advisory: bool = True
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code, "severity": self.severity,
            "title": self.title, "detail": self.detail,
            "advisory": True,
            "extras": self.extras,
        }


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def engine_b_alert(verdict: dict | None) -> list[Alert]:
    """Alert when Engine B Sharpe crosses warn/crit thresholds."""
    if not verdict:
        return []
    sharpe = _f(verdict.get("rolling_sharpe"))
    if sharpe is None:
        sharpe = _f(verdict.get("full_sharpe"))
    if sharpe is None:
        return []
    if sharpe <= ENGINE_B_SHARPE_CRIT:
        return [Alert(
            code="ENGINE_B_SHARPE_CRITICAL",
            severity=SEV_CRIT,
            title="Engine B Sharpe in critical range",
            detail=f"Engine B Sharpe={sharpe:.2f} ≤ {ENGINE_B_SHARPE_CRIT}. "
                   f"Operator should consider DISABLED state. "
                   f"No automatic action taken.",
            extras={"sharpe": round(sharpe, 4),
                    "state": verdict.get("state")})]
    if sharpe <= ENGINE_B_SHARPE_WARN:
        return [Alert(
            code="ENGINE_B_SHARPE_DEGRADED",
            severity=SEV_WARN,
            title="Engine B Sharpe degraded",
            detail=f"Engine B Sharpe={sharpe:.2f} ≤ {ENGINE_B_SHARPE_WARN}. "
                   f"Monitor — no action required.",
            extras={"sharpe": round(sharpe, 4),
                    "state": verdict.get("state")})]
    return []


def baseline_alert(snapshot: dict | None) -> list[Alert]:
    """Alert when system underperforms its best static baseline."""
    if not snapshot:
        return []
    underperform = bool(snapshot.get("system_underperforming_baseline"))
    if not underperform:
        return []
    delta = _f(snapshot.get("delta_sharpe_vs_baseline"))
    best = snapshot.get("best_baseline_name") or "?"
    return [Alert(
        code="SYSTEM_UNDERPERFORMS_BASELINE",
        severity=SEV_CRIT,
        title="System underperforms best baseline",
        detail=(f"System Sharpe is below '{best}' "
                f"(delta={delta:+.2f})" if delta is not None
                else f"System Sharpe is below '{best}'.")
                + " Hard blocker for ML promotion.",
        extras={"delta_sharpe_vs_baseline":
                None if delta is None else round(delta, 4),
                "best_baseline_name": best})]


def ml_alpha_alert(promotion_inputs: dict | None) -> list[Alert]:
    """Alert when ML delta Sharpe < 0 (ML failing to add edge)."""
    if not promotion_inputs:
        return []
    out: list[Alert] = []
    d_det = _f(promotion_inputs.get("delta_sharpe_vs_deterministic"))
    if d_det is not None:
        if d_det <= ML_DELTA_SHARPE_CRIT:
            out.append(Alert(
                code="ML_DELTA_SHARPE_CRITICAL",
                severity=SEV_CRIT,
                title="ML strongly underperforms deterministic engine",
                detail=f"delta_sharpe_vs_deterministic={d_det:+.2f}. "
                       f"Hard blocker for promotion.",
                extras={"delta_sharpe_vs_deterministic": round(d_det, 4)}))
        elif d_det <= ML_DELTA_SHARPE_WARN:
            out.append(Alert(
                code="ML_DELTA_SHARPE_DEGRADED",
                severity=SEV_WARN,
                title="ML not adding edge over deterministic engine",
                detail=f"delta_sharpe_vs_deterministic={d_det:+.2f}. "
                       f"Continue advisory accumulation; promotion gated.",
                extras={"delta_sharpe_vs_deterministic": round(d_det, 4)}))
    return out


def calibration_alert(promotion_inputs: dict | None) -> list[Alert]:
    """Alert when ECE crosses thresholds."""
    if not promotion_inputs:
        return []
    ece = _f(promotion_inputs.get("ece"))
    if ece is None:
        return []
    if ece >= ECE_CRIT:
        return [Alert(
            code="ML_CALIBRATION_CRITICAL",
            severity=SEV_CRIT,
            title="ML calibration severely degraded",
            detail=f"ECE={ece:.3f} ≥ {ECE_CRIT}. "
                   f"Hard blocker for promotion.",
            extras={"ece": round(ece, 4)})]
    if ece >= ECE_WARN:
        return [Alert(
            code="ML_CALIBRATION_DEGRADED",
            severity=SEV_WARN,
            title="ML calibration degraded",
            detail=f"ECE={ece:.3f} ≥ {ECE_WARN}. "
                   f"Promotion gated until calibration improves.",
            extras={"ece": round(ece, 4)})]
    return []


def drift_alerts(drift_aggregate: dict | None) -> list[Alert]:
    """Map drift_monitor.aggregate() output → Alert list."""
    if not drift_aggregate:
        return []
    out: list[Alert] = []
    for r in drift_aggregate.get("results", []):
        sev = r.get("severity")
        if sev == "CRITICAL":
            out.append(Alert(
                code=f"DRIFT_CRITICAL:{r.get('name')}",
                severity=SEV_CRIT,
                title=f"Drift critical — {r.get('name')}",
                detail=r.get("detail", ""),
                extras={"statistic": r.get("statistic")}))
        elif sev == "WARN":
            out.append(Alert(
                code=f"DRIFT_WARN:{r.get('name')}",
                severity=SEV_WARN,
                title=f"Drift warning — {r.get('name')}",
                detail=r.get("detail", ""),
                extras={"statistic": r.get("statistic")}))
    return out


def evaluate(
    *,
    engine_b_verdict: dict | None = None,
    baseline_snapshot: dict | None = None,
    promotion_inputs: dict | None = None,
    drift_aggregate: dict | None = None,
) -> dict:
    """Run all alert rules; return aggregated dict.

    NEVER triggers any execution / mutation. Output is consumed by
    UI + logs only.
    """
    alerts: list[Alert] = []
    alerts += engine_b_alert(engine_b_verdict)
    alerts += baseline_alert(baseline_snapshot)
    alerts += ml_alpha_alert(promotion_inputs)
    alerts += calibration_alert(promotion_inputs)
    alerts += drift_alerts(drift_aggregate)

    worst = SEV_INFO
    for a in alerts:
        if _RANK.get(a.severity, 0) > _RANK[worst]:
            worst = a.severity

    return {
        "overall_severity": worst,
        "alerts": [a.to_dict() for a in alerts],
        "n_critical": sum(1 for a in alerts if a.severity == SEV_CRIT),
        "n_warn": sum(1 for a in alerts if a.severity == SEV_WARN),
        "advisory_only": True,
        "auto_action_taken": False,
    }
