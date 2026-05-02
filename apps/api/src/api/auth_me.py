"""Phase G — read-only auth introspection endpoints.

GET-only. NEVER mounts a POST/PUT/PATCH/DELETE handler. Returns
the currently-resolved user + effective tier + org memberships so
the frontend can render account-plan badges without ever guessing
the tier.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from apps.api.src.auth.resolver import AuthDecision, get_current_user
from apps.api.src.db import SessionLocal


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def get_me(
    decision: AuthDecision = Depends(get_current_user),
) -> dict[str, Any]:
    user = decision.user
    return {
        "user": (
            {
                "id": user.id, "email": user.email,
                "display_name": user.display_name,
                "auth_provider": user.auth_provider,
                "disabled": user.disabled,
            }
            if user else None
        ),
        "effective_tier": decision.effective_tier,
        "reason": decision.reason,
    }


@router.get("/orgs")
def list_my_orgs(
    decision: AuthDecision = Depends(get_current_user),
) -> dict[str, Any]:
    if decision.user is None:
        return {"orgs": []}
    with SessionLocal() as s:
        rows = s.execute(text(
            """
            SELECT o.id, o.name, m.role, m.status, m.created_at
            FROM public.organization_member m
            JOIN public.organization o ON o.id = m.org_id
            WHERE m.user_id = :uid AND m.status = 'active'
            ORDER BY o.name
            """
        ), {"uid": decision.user.id}).mappings().all()
    return {
        "orgs": [
            {
                "id": r["id"], "name": r["name"],
                "role": r["role"], "status": r["status"],
                "joined_at": (
                    r["created_at"].isoformat() if r["created_at"] else None
                ),
            }
            for r in rows
        ],
    }
