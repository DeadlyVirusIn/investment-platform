"""Agent kind registry. Frozen metadata only — no behaviour.

The banner string is the single canonical disclaimer; every
emitted prompt MUST contain it verbatim. The list is a hard
allow-list — adding new kinds requires a code review.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# Single source of truth for the disclaimer string. Tests assert
# verbatim presence; do not edit casually.
BANNER = "AI research insight — not execution logic."


class AgentKind(str, Enum):
    TRADE_QUALITY = "trade_quality"
    RISK_COMMENTARY = "risk_commentary"
    EXIT_REVIEW = "exit_review"
    OPTIONS_THESIS = "options_thesis"


@dataclass(frozen=True)
class AgentMeta:
    kind: AgentKind
    label: str
    source_endpoint: str
    required_payload_fields: tuple[str, ...]
    template_path: str          # filename inside agents/prompts/
    extra_disclaimer: str = ""


REGISTRY: dict[AgentKind, AgentMeta] = {
    AgentKind.TRADE_QUALITY: AgentMeta(
        kind=AgentKind.TRADE_QUALITY,
        label="Trade Quality",
        source_endpoint="/api/performance/paper/trade-quality",
        required_payload_fields=(
            "score", "grade", "thesis", "completeness",
            "components", "reasons",
        ),
        template_path="trade_quality.md",
    ),
    AgentKind.RISK_COMMENTARY: AgentMeta(
        kind=AgentKind.RISK_COMMENTARY,
        label="Risk Commentary",
        source_endpoint="/api/performance/paper/risk-dashboard",
        required_payload_fields=(
            "nav", "cash", "exposure_value", "exposure_pct",
            "open_positions_count", "mark_unavailable",
        ),
        template_path="risk_commentary.md",
    ),
    AgentKind.EXIT_REVIEW: AgentMeta(
        kind=AgentKind.EXIT_REVIEW,
        label="Exit Review",
        source_endpoint="/api/performance/paper/exit-analytics",
        required_payload_fields=(
            "n_closed", "n_winners", "n_losers", "win_rate",
            "realized_pnl_total", "tp_sl_effectiveness",
            "small_sample_warning",
        ),
        template_path="exit_review.md",
    ),
    AgentKind.OPTIONS_THESIS: AgentMeta(
        kind=AgentKind.OPTIONS_THESIS,
        label="Options Thesis",
        source_endpoint="/api/options/evaluation/scores",
        required_payload_fields=(
            "rule_id", "underlying", "total_score", "qualified",
        ),
        template_path="options_thesis.md",
        extra_disclaimer=(
            "Options insights are paper / research only — "
            "execution_allowed=false."
        ),
    ),
}


def get_meta(kind: AgentKind) -> AgentMeta:
    if kind not in REGISTRY:
        raise KeyError(f"unknown agent kind: {kind!r}")
    return REGISTRY[kind]
