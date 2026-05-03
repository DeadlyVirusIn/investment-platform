"""SYSTEM-ALPHA coverage report — which tables are populated + drift."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class CoverageReport:
    decisions_total: int
    decisions_with_attribution: int
    decisions_attribution_pct: float
    trades_closed_total: int
    trades_with_execution_quality: int
    trades_exec_quality_pct: float
    losing_trades_total: int
    losing_trades_with_failure_analysis: int
    losing_trades_failure_pct: float
    latest_health_score_date: str | None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions_total": self.decisions_total,
            "decisions_with_attribution": self.decisions_with_attribution,
            "decisions_attribution_pct": round(
                self.decisions_attribution_pct, 4,
            ),
            "trades_closed_total": self.trades_closed_total,
            "trades_with_execution_quality":
                self.trades_with_execution_quality,
            "trades_exec_quality_pct": round(
                self.trades_exec_quality_pct, 4,
            ),
            "losing_trades_total": self.losing_trades_total,
            "losing_trades_with_failure_analysis":
                self.losing_trades_with_failure_analysis,
            "losing_trades_failure_pct": round(
                self.losing_trades_failure_pct, 4,
            ),
            "latest_health_score_date": self.latest_health_score_date,
            "warnings": list(self.warnings),
        }


def build_coverage_report(session: Session) -> CoverageReport:
    warnings: list[str] = []
    # Decisions
    row = session.execute(text("""
        SELECT COUNT(*) FILTER (WHERE factor_attribution IS NOT NULL) AS wa,
               COUNT(*) AS total
        FROM decision_log
    """)).mappings().first() or {}
    d_total = int(row.get("total") or 0)
    d_wa    = int(row.get("wa")    or 0)
    d_pct   = (d_wa / d_total) if d_total else 0.0
    if d_total > 0 and d_pct < 0.80:
        warnings.append(
            f"factor_attribution coverage {d_pct:.0%} < 80%"
        )

    # Trades
    row = session.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE execution_quality IS NOT NULL) AS we
        FROM paper_trade_log
        WHERE status = 'closed'
    """)).mappings().first() or {}
    t_total = int(row.get("total") or 0)
    t_we    = int(row.get("we")    or 0)
    t_pct   = (t_we / t_total) if t_total else 0.0
    if t_total > 0 and t_pct < 0.80:
        warnings.append(
            f"execution_quality coverage {t_pct:.0%} < 80%"
        )

    # Losing trades
    row = session.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE failure_analysis IS NOT NULL) AS wf
        FROM paper_trade_log
        WHERE status = 'closed' AND net_ret_pct < 0
    """)).mappings().first() or {}
    l_total = int(row.get("total") or 0)
    l_wf    = int(row.get("wf")    or 0)
    l_pct   = (l_wf / l_total) if l_total else 0.0
    if l_total > 0 and l_pct < 0.80:
        warnings.append(
            f"failure_analysis coverage {l_pct:.0%} < 80%"
        )

    # Health score freshness
    row = session.execute(text("""
        SELECT as_of_date FROM system_health_score
        ORDER BY created_at DESC LIMIT 1
    """)).mappings().first()
    latest_health: str | None = None
    if row:
        latest_health = row["as_of_date"].isoformat()
        age_days = (dt.date.today() - row["as_of_date"]).days
        if age_days > 2:
            warnings.append(
                f"system_health_score stale by {age_days} days"
            )
    else:
        warnings.append("system_health_score empty — run alpha_nightly")

    return CoverageReport(
        decisions_total=d_total,
        decisions_with_attribution=d_wa,
        decisions_attribution_pct=d_pct,
        trades_closed_total=t_total,
        trades_with_execution_quality=t_we,
        trades_exec_quality_pct=t_pct,
        losing_trades_total=l_total,
        losing_trades_with_failure_analysis=l_wf,
        losing_trades_failure_pct=l_pct,
        latest_health_score_date=latest_health,
        warnings=warnings,
    )
