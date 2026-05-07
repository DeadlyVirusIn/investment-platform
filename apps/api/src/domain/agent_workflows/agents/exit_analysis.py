"""Exit Analysis Agent.

Delegates to the existing `/performance/paper/exit-analytics`
endpoint logic (Phase D). Preserves the small-sample-size caveat
verbatim and never fabricates a denominator.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..base import Agent, AgentOutput


class ExitAnalysisAgent(Agent):
    name = "exit_analysis"
    description = (
        "Read-only closed-trade analytics: TP/SL/max-hold split, "
        "win rate, avg win/loss, best/worst exit. Honors small-"
        "sample warning verbatim."
    )

    def inputs(self) -> dict[str, str]:
        return {
            "paper_trade": "SELL rows with realized_pnl",
            "paper_position": "matched lifetimes for hold-days",
            "replay_recovery_manifest": (
                "read-only exclusion source"
            ),
        }

    def run(
        self,
        *,
        db: Session,
        include_replay: bool = False,
        limit: int = 500,
        **_: Any,
    ) -> AgentOutput:
        from apps.api.src.api.performance_paper import (
            paper_exit_analytics,
        )
        report = paper_exit_analytics(
            db=db, include_replay=include_replay, limit=limit,
        )

        warnings: list[str] = []
        n_closed = int(report.get("n_closed", 0) or 0)
        if n_closed == 0:
            warnings.append(
                "no_closed_outcomes_yet: win_rate is null — "
                "do NOT interpret as 0%",
            )
        sample_warning = report.get("small_sample_warning")
        if sample_warning:
            # Verbatim — preserves the "directional, not reliable"
            # phrasing from the Phase D endpoint.
            warnings.append(str(sample_warning))

        return self.envelope(
            output=report,
            inputs_summary={
                "include_replay": include_replay,
                "limit": limit,
                "n_closed": n_closed,
            },
            warnings=warnings,
        )
