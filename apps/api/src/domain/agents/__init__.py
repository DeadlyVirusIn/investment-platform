"""Pre-LLM scaffolding for agent insights (Phase F1).

This package builds deterministic prompt strings from existing
read-only payloads. It does NOT call any LLM, write to any
table, or import from execution / paper-trading / options
execution / replay-recovery modules.

When/if Phase F2 wires an LLM client, that integration must
remain feature-flagged (`AGENT_INSIGHTS_ENABLED`) and gated
behind the same hard NO list documented in the FinRobot audit:
no autonomous trading, no execution decisions, no portfolio
rebalancing, no threshold changes, no DB writes outside an
`agent_insight` cache table.

This phase introduces NO endpoint, NO env flag, NO new
dependency.
"""

from .registry import AgentKind, BANNER, REGISTRY  # noqa: F401
from .narrator import build_prompt  # noqa: F401
