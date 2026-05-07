"""Base abstractions for the agent-workflow framework.

Every agent inherits from `Agent`, declares its inputs via
`inputs()`, and produces an `AgentOutput` from `run(db, **params)`.
The `validate(output)` hook is a hard gate — it raises if the
output asserts any execution linkage.

NEVER imports from execution / paper-execution / options-execution
modules. Source-level scanned by the test suite.
"""

from __future__ import annotations

import datetime as _dt
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# Canonical banner string for every agent envelope. Frontends
# render this verbatim so the operator never confuses agent
# output with executed actions.
AGENT_BANNER: str = (
    "Agent-generated insights — read-only research, not execution "
    "logic."
)


class AgentMode(str, Enum):
    """How the agent computed its output. Phase F6 ships only
    deterministic agents; an LLM-augmented mode would be an
    additional value (gated by AGENT_INSIGHTS_ENABLED, separate
    layer)."""

    DETERMINISTIC = "deterministic"


class AgentOutput(BaseModel):
    """Standard envelope returned by every agent. Pydantic-validated
    so a misbehaving agent cannot smuggle freeform fields past the
    framework's contract."""

    agent: str
    mode: AgentMode
    generated_at: str
    inputs_summary: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    banner: str = AGENT_BANNER
    execution_linked: bool = False


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class Agent(ABC):
    """Base class for every agent. Subclasses must override:
      * `name`: stable identifier used by the dispatch layer.
      * `description`: one-line human summary.
      * `inputs()`: declarative source description.
      * `run(db, **params)`: deterministic computation that
        returns an `AgentOutput`.

    The default `validate()` enforces the read-only invariant
    (`execution_linked is False`) and that the banner is the
    canonical string.
    """

    name: str = ""
    description: str = ""
    mode: AgentMode = AgentMode.DETERMINISTIC

    @abstractmethod
    def inputs(self) -> dict[str, str]:
        """Map of input source name → human description. Surfaced
        by the `/api/agent-workflows` listing endpoint so an
        operator can see what each agent reads before invoking."""

    @abstractmethod
    def run(self, *, db: Any, **params: Any) -> AgentOutput:
        """Execute the agent. MUST be deterministic given the same
        DB snapshot and parameters. MUST NOT write to any table.
        MUST NOT call the LLM. MUST NOT touch execution paths."""

    def validate(self, output: AgentOutput) -> None:
        """Hard invariant gate. Raises ValueError on any violation.
        Called by the runner after `run()` returns; agents may
        override to add domain-specific checks but MUST call
        `super().validate(output)` first."""
        if output.execution_linked is not False:
            raise ValueError(
                f"{self.name}: execution_linked must be False, "
                f"got {output.execution_linked!r}"
            )
        if output.banner != AGENT_BANNER:
            raise ValueError(
                f"{self.name}: banner mismatch; got "
                f"{output.banner!r}"
            )
        if output.agent != self.name:
            raise ValueError(
                f"agent name mismatch: envelope says "
                f"{output.agent!r}, expected {self.name!r}"
            )

    def envelope(
        self,
        *,
        output: dict[str, Any],
        inputs_summary: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
    ) -> AgentOutput:
        """Helper: build the standard envelope with sensible
        defaults. Subclasses use this from `run()` instead of
        constructing `AgentOutput` directly."""
        return AgentOutput(
            agent=self.name,
            mode=self.mode,
            generated_at=_utc_now_iso(),
            inputs_summary=inputs_summary or {},
            output=output,
            warnings=warnings or [],
        )
