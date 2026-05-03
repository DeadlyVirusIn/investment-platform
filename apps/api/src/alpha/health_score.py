"""Daily System Health Score."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SystemHealthScore:
    overall: int
    data_quality: int
    signal_quality: int
    catalyst_coverage: int
    execution_quality: int
    risk_control: int
    ml_readiness: int
    paper_feedback: int
    recommendation: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall":            self.overall,
            "data_quality":       self.data_quality,
            "signal_quality":     self.signal_quality,
            "catalyst_coverage":  self.catalyst_coverage,
            "execution_quality":  self.execution_quality,
            "risk_control":       self.risk_control,
            "ml_readiness":       self.ml_readiness,
            "paper_feedback":     self.paper_feedback,
            "recommendation":     self.recommendation,
            "warnings":           list(self.warnings),
        }


def compute_system_health(
    *,
    data_quality: float = 0.0,
    signal_quality: float = 0.0,
    catalyst_coverage: float = 0.0,
    execution_quality: float = 0.0,
    risk_control: float = 0.0,
    ml_readiness: float = 0.0,
    paper_feedback: float = 0.0,
) -> SystemHealthScore:
    """All inputs 0..1. Output ints 0..100."""
    dq  = _pct(data_quality)
    sq  = _pct(signal_quality)
    cc  = _pct(catalyst_coverage)
    eq  = _pct(execution_quality)
    rc  = _pct(risk_control)
    mlr = _pct(ml_readiness)
    pf  = _pct(paper_feedback)

    # Weighted overall — data + signal weigh more
    overall = int(round(
        dq * 0.20 + sq * 0.20 + cc * 0.10 + eq * 0.10
        + rc * 0.15 + mlr * 0.15 + pf * 0.10,
    ))

    warnings: list[str] = []
    if cc < 50:
        warnings.append("catalyst coverage weak — backfill required")
    if mlr < 30:
        warnings.append("ml not ready — keep advisory only")
    if dq < 60:
        warnings.append("data quality below 60 — audit providers")
    if sq < 50:
        warnings.append("signal stability low — review recommendations")

    rec = _recommendation(overall, cc, mlr, dq)

    return SystemHealthScore(
        overall=overall, data_quality=dq, signal_quality=sq,
        catalyst_coverage=cc, execution_quality=eq, risk_control=rc,
        ml_readiness=mlr, paper_feedback=pf,
        recommendation=rec, warnings=warnings,
    )


def _pct(v: float) -> int:
    try:
        x = float(v)
    except (TypeError, ValueError):
        x = 0.0
    x = max(0.0, min(1.0, x))
    return int(round(x * 100))


def _recommendation(
    overall: int, cc: int, mlr: int, dq: int,
) -> str:
    if dq < 40:
        return ("Data quality below 40 — do not run ML or expand scope. "
                "Audit providers first.")
    if cc < 40:
        return ("Continue paper trading; improve catalyst coverage before "
                "ML influence.")
    if mlr < 50:
        return "Continue shadow ML only; not ready for influence."
    if overall < 60:
        return "Keep advisory only; address top warnings."
    return "System healthy for continued paper-trade research; keep ML passive."
