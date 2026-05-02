"""Phase 11W (Phase E) — admin-only manual research run HTTP route.

ONLY mounted by main.py when BOTH:
  * `RESEARCH_RO_ENABLED` is True
  * `RESEARCH_MANUAL_RUN_ENABLED` is True
  * `RESEARCH_ADMIN_TOKEN` is non-empty

When any condition fails, the route is not registered — every
`/api/research/runs/manual` request returns FastAPI's default 404.
Even when mounted, the handler enforces the admin token check and
all Phase E gates via `manual_run_safe.run_manual_safely`.

NEVER returns the raw provider body. The response payload contains
only run metadata (id, status, counts, cost, safety_status).
Operators retrieve the body separately via the existing GET-only
research API once it is exposed in a future phase.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.research.manual_run_safe import (
    PhaseECostExceededError,
    PhaseEDisabledError,
    PhaseENotAllowedError,
    PhaseEQuotaExceededError,
    PhaseEValidationError,
    PhaseEError,
    run_manual_safely,
)


router = APIRouter(prefix="/research/runs", tags=["research"])


class ManualRunRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)
    as_of: dt.date
    provider: str = Field(default="mock", min_length=1)
    operator_id: str = Field(..., min_length=1, max_length=128)
    candidate_idea_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


def _require_admin_token(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> None:
    """Header-based admin auth. The route is only mounted when the
    admin token env is non-empty (see main.py), so reaching this
    handler means a token *should* be configured."""
    expected = (settings.RESEARCH_ADMIN_TOKEN or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="admin_token_unset")
    if (x_admin_token or "").strip() != expected:
        raise HTTPException(status_code=403, detail="invalid_admin_token")


@router.post("/manual")
def post_manual_run(
    body: ManualRunRequest,
    _: None = Depends(_require_admin_token),
) -> dict[str, Any]:
    """Phase E admin-only manual trigger. Always returns sanitized
    metadata only (never the raw provider body)."""
    try:
        with SessionLocal() as session:
            payload = run_manual_safely(
                session,
                symbol=body.symbol,
                as_of=body.as_of,
                provider_name=body.provider,
                operator_id=body.operator_id,
                candidate_idea_id=body.candidate_idea_id,
                idempotency_key=body.idempotency_key,
                triggered_by="manual",
                request_source="http",
            )
    except PhaseEDisabledError as exc:
        # Surface as 404 — never confirm the route exists when off.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PhaseECostExceededError as exc:
        raise HTTPException(status_code=402, detail={
            "code": exc.code, "message": str(exc),
        }) from exc
    except PhaseEQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail={
            "code": exc.code, "message": str(exc),
        }) from exc
    except PhaseENotAllowedError as exc:
        raise HTTPException(status_code=403, detail={
            "code": exc.code, "message": str(exc),
        }) from exc
    except PhaseEValidationError as exc:
        raise HTTPException(status_code=422, detail={
            "code": exc.code, "message": str(exc),
        }) from exc
    except PhaseEError as exc:
        raise HTTPException(status_code=400, detail={
            "code": exc.code, "message": str(exc),
        }) from exc

    # Sanitized payload — never includes raw model body.
    return payload.as_dict()
