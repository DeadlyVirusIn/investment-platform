"""Agent Gateway owner console — token management (spec §2, §10 v0).

Owner-only (`require_owner`, 404 posture): the ONLY way tokens are minted,
listed, or revoked. There is no self-service or API-driven token creation
(spec §2). Mounted in the same fail-closed block as the gateway router, so
when AGENT_GATEWAY_ENABLED is False these routes 404 and no token can exist.

The full token secret is returned EXACTLY ONCE from create; list never
returns a hash or secret (only prefix + metadata).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.src.api.admin_guard import require_owner
from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.domain.agent_gateway import tokens

router = APIRouter(prefix="/admin/agent-tokens", tags=["agent-gateway-admin"])


class CreateTokenBody(BaseModel):
    agent_name: str = Field(min_length=1, max_length=64)
    scopes: list[str] = Field(min_length=1, max_length=4)
    ttl_days: int | None = Field(default=None, ge=1)
    rate_limit_per_min: int = Field(default=60, ge=1, le=240)
    max_request_bytes: int = Field(default=65536, ge=1024, le=1_048_576)


class RevokeBody(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


@router.post("")
def create_agent_token(
    body: CreateTokenBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict:
    """Mint a token. `token` is shown ONCE — it is never retrievable again."""
    ttl = body.ttl_days or int(settings.AGENT_TOKEN_DEFAULT_TTL_DAYS)
    try:
        full, meta = tokens.create_token(
            db,
            agent_name=body.agent_name,
            scopes=body.scopes,
            created_by=owner["id"],
            ttl_days=ttl,
            max_ttl_days=int(settings.AGENT_TOKEN_MAX_TTL_DAYS),
            rate_limit_per_min=body.rate_limit_per_min,
            max_request_bytes=body.max_request_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    logger.info("agent_token_created prefix={} by={}", meta["token_prefix"], owner["email"])
    # secret shown exactly once — never logged, never stored in plaintext
    return {"token": full, **meta, "ttl_days": ttl}


@router.get("")
def list_agent_tokens(
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict:
    return {"tokens": tokens.list_tokens(db)}


@router.post("/{token_id}/revoke")
def revoke_agent_token(
    token_id: str,
    body: RevokeBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict:
    ok = tokens.revoke_token(db, token_id=token_id, reason=body.reason)
    db.commit()
    if not ok:
        # already revoked or unknown — indistinguishable (no existence oracle)
        raise HTTPException(status_code=404)
    logger.info("agent_token_revoked id={} by={}", token_id, owner["email"])
    return {"revoked": True, "id": token_id}
