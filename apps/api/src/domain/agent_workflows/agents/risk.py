"""Risk Agent.

Delegates to the existing `/performance/paper/risk-dashboard`
endpoint logic. Reuses `paper_risk_dashboard` directly so the
truth-aligned exposure rules from Phase C apply unchanged. NEVER
recomputes exposure off nullable selector-path fields — the
underlying handler already enforces that invariant.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..base import Agent, AgentOutput


class RiskAgent(Agent):
    name = "risk"
    description = (
        "Read-only NAV / exposure / concentration / drawdown "
        "rollup. Mark-to-market sourced from "
        "paper_equity_snapshot.positions_value."
    )

    def inputs(self) -> dict[str, str]:
        return {
            "paper_equity_snapshot": "latest NAV / positions_value",
            "paper_position": "open quantities per portfolio",
            "paper_portfolio": "active portfolios",
            "price_bar": "latest close per symbol",
            "replay_recovery_manifest": (
                "read-only source-exclusion of replay rows"
            ),
        }

    def run(
        self,
        *,
        db: Session,
        include_replay: bool = False,
        **_: Any,
    ) -> AgentOutput:
        # Reuse the Phase C handler. It is a regular Python function
        # with `db: Session` as the first param + simple defaults
        # for the rest, so direct invocation is safe.
        from apps.api.src.api.performance_paper import (
            paper_risk_dashboard,
        )
        # Pass every Query-defaulted param explicitly so direct
        # invocation does not leak a `Query(...)` sentinel into the
        # SQL bound-parameter dict.
        report = paper_risk_dashboard(
            db=db, include_replay=include_replay, top_n=5,
        )

        warnings: list[str] = []
        if report.get("mark_unavailable"):
            warnings.append(
                "mark_unavailable: positions_value missing — "
                "exposure surfaced as null, not zero",
            )
        n_open = int(report.get("open_positions_count", 0) or 0)
        if n_open == 0:
            warnings.append("no_open_positions")

        return self.envelope(
            output=report,
            inputs_summary={
                "include_replay": include_replay,
                "open_positions_count": n_open,
                "mark_unavailable": bool(report.get("mark_unavailable")),
            },
            warnings=warnings,
        )
