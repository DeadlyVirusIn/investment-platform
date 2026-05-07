"""Trade Quality Agent.

Wraps the existing `assemble_quality_report` service used by the
Phase B `/performance/paper/trade-quality` endpoint. NO new
computation; this agent exists so the unified `/api/agent-workflows`
surface can produce the same structured envelope for every agent.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..base import Agent, AgentOutput


class TradeQualityAgent(Agent):
    name = "trade_quality"
    description = (
        "Pre-ML diagnostic over closed/open paper trades: 0-100 "
        "score, A-F grade, reason bullets, completeness flag."
    )

    def inputs(self) -> dict[str, str]:
        return {
            "paper_trade": "BUY/SELL paper trade rows",
            "paper_position": "open paper positions",
            "price_bar": "latest close per asset",
            "paper_equity_snapshot": (
                "NAV / cash / positions_value snapshot rows"
            ),
        }

    def run(
        self,
        *,
        db: Session,
        include_replay: bool = False,
        limit: int = 200,
        max_hold_days: int = 10,
        **_: Any,
    ) -> AgentOutput:
        # Lazy import — the service module is heavy and not always
        # needed if the agent is only being introspected.
        from apps.api.src.domain.paper_quality.service import (
            assemble_quality_report,
        )
        report = assemble_quality_report(
            db,
            include_replay=include_replay,
            limit=limit,
            max_hold_days=max_hold_days,
        )

        warnings: list[str] = []
        n_items = int(report.get("n_items", 0) or 0)
        if n_items == 0:
            warnings.append(
                "no_eligible_paper_trades: zero state — "
                "score / grade not surfaced",
            )

        return self.envelope(
            output=report,
            inputs_summary={
                "include_replay": include_replay,
                "limit": limit,
                "max_hold_days": max_hold_days,
                "n_items": n_items,
            },
            warnings=warnings,
        )
