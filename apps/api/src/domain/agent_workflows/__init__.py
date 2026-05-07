"""Phase F6 — agent-style workflows.

Read-only orchestration layer over the existing diagnostic
endpoints. NO execution side effects, NO DB writes outside what
the underlying read-only services already do (which is nothing
beyond SELECT). Agents are deterministic Python wrappers; LLM
narration remains gated behind the F2 feature flag in a separate
module.

Modeled on the orchestrated-pipeline pattern from Anthropic's
finance-agents announcement: each agent declares its inputs,
runs a deterministic computation, and returns a structured
output envelope with a banner asserting read-only intent.
"""

from .base import Agent, AgentMode, AgentOutput  # noqa: F401
from .registry import (  # noqa: F401
    AGENT_REGISTRY,
    get_agent,
    list_agent_names,
)
