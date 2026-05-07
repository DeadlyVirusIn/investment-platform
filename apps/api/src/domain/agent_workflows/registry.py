"""Agent registry. Maps stable name → agent instance for the
dispatcher. The registry is constructed at import time from the
`agents` subpackage; adding a new agent is a one-line change in
`agents/__init__.py`."""

from __future__ import annotations

from typing import Iterable

from .base import Agent
from .agents import ALL_AGENTS


# Single canonical instance per agent. Stateless by construction.
AGENT_REGISTRY: dict[str, Agent] = {a.name: a for a in ALL_AGENTS}


def get_agent(name: str) -> Agent:
    """Return the registered agent or raise KeyError."""
    if name not in AGENT_REGISTRY:
        raise KeyError(f"unknown agent: {name!r}")
    return AGENT_REGISTRY[name]


def list_agent_names() -> Iterable[str]:
    return tuple(AGENT_REGISTRY.keys())
