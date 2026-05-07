"""Phase F6 — REST surface for the agent-workflow framework.

Hard rules:
  * GET only. The router declares no POST/PUT/PATCH/DELETE handlers.
  * No DB writes. No persistence. No background tasks.
  * Listing endpoint exposes only metadata (name, description,
    inputs map). Run endpoint dispatches to the registered agent
    and returns its `AgentOutput` envelope verbatim.
  * Unknown agent → HTTP 404 with the requested name (no enum
    leak in the body — keeps surface clean).
  * Run-time errors propagate as HTTP 500 only when the underlying
    handler raises; agents themselves never raise on empty data.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.agent_workflows import (
    AGENT_REGISTRY, get_agent,
)
from apps.api.src.domain.agent_workflows.base import AGENT_BANNER


router = APIRouter(
    prefix="/agent-workflows", tags=["agent-workflows"],
)


@router.get("/")
def list_agents() -> dict[str, Any]:
    """List every registered agent. Read-only metadata only."""
    return {
        "banner": AGENT_BANNER,
        "agents": [
            {
                "name": a.name,
                "description": a.description,
                "mode": a.mode.value,
                "inputs": a.inputs(),
            }
            for a in AGENT_REGISTRY.values()
        ],
    }


@router.get("/{name}/run")
def run_agent(
    name: str,
    db: Session = Depends(get_session),
    include_replay: bool = Query(
        False,
        description=(
            "Pass-through to underlying read-only diagnostic. "
            "Default false — replay rows hidden by default."
        ),
    ),
    limit: int = Query(
        500, ge=1, le=2000,
        description="Row cap for table-like agents.",
    ),
) -> dict[str, Any]:
    """Invoke a registered agent and return its structured output.
    Validates the envelope before returning so a misbehaving agent
    cannot leak `execution_linked=True` past the framework."""
    try:
        agent = get_agent(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": f"unknown agent: {name!r}"},
        ) from exc

    output = agent.run(
        db=db, include_replay=include_replay, limit=limit,
    )
    agent.validate(output)
    return output.model_dump()
