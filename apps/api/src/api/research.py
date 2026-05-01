"""Phase 11W (Phase B) — Research Intelligence read-only API.

GET-only. NO POST/PUT/PATCH/DELETE handlers — Phase B ships safety
scaffolding only. The router is mounted from `apps/api/src/main.py`
ONLY when `settings.RESEARCH_RO_ENABLED` is True (production default
False). When the flag is off, the router is not mounted and every
`/api/research/*` path returns 404 by FastAPI's default handler.

NEVER imports `feature_engine`, `recommendation_engine`,
`shadow_scorer`, `drift_monitor`, `auto_trader`, `paper_execution`,
or any execution-mutating module. Enforced by an architectural CI
test (`test_research_no_execution_imports`).

Phase B route shapes (empty payloads only):
  GET  /api/research/runs
  GET  /api/research/runs/{run_id}
  GET  /api/research/ticker/{symbol}/latest
  GET  /api/research/decision/{decision_id}
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/runs")
def list_runs(
    cursor: str | None = None,
    limit: int = 20,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Phase B: empty-list shape. No data is returned because no
    research orchestration runs in Phase B."""
    return {"runs": [], "next_cursor": None}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    """Phase B: 404 by design (no rows persist in Phase B)."""
    raise HTTPException(status_code=404, detail="research run not found")


@router.get("/ticker/{symbol}/latest")
def latest_run_for_ticker(symbol: str) -> dict[str, Any]:
    """Phase B: returns the symbol echo and `run: null`. Future
    phases will populate."""
    return {"symbol": symbol, "run": None}


@router.get("/decision/{decision_id}")
def runs_for_decision(decision_id: str) -> dict[str, Any]:
    """Phase B: empty-list shape per decision."""
    return {"decision_id": decision_id, "runs": []}
