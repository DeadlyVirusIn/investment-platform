"""Agent Gateway v0 — /agent router + Bearer auth dependency (spec §4).

Mounted ONLY when settings.AGENT_GATEWAY_ENABLED is True (fail-closed); when
False the router and its audit middleware are never added, so every /agent
path 404s and no token surface exists.

Security boundary (spec §1): every guarantee is enforced server-side here.
Auth is `Authorization: Bearer arthos_at_…` resolved by `require_agent_scope`
— never the `arthos_session` cookie (agent tokens and browser sessions are
non-interchangeable in both directions). A token missing the route's scope
gets 403; a bad/expired/revoked token gets 401; and both — like every other
request — are written to `agent_audit` by the middleware, which no route can
bypass (spec §5).

v0 scope of THIS slice: the full security machinery (mint → resolve → scope →
audit → revoke → expiry) is wired end-to-end and `GET /agent/whoami` proves an
authenticated round-trip. The data/job/draft routes are scope-gated and
audited but return 501 until their data-contract slices land (spec §4 routes
exist; their bodies are the next approval-gated changes) — this keeps the
trust boundary real without inventing data contracts.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from apps.api.src.config import settings
from apps.api.src.domain.agent_gateway import audit, tokens

router = APIRouter(prefix="/agent", tags=["agent-gateway"])


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------
def _resolve_session_identity(authorization: str | None) -> dict | None:
    """Open a short-lived session, resolve the bearer token. Isolated so the
    dependency stays thin and testable."""
    from apps.api.src.db import SessionLocal

    full = tokens.parse_bearer(authorization)
    with SessionLocal() as s:
        ident = tokens.resolve_token(s, full)
        if ident is not None:
            s.commit()  # persist last_used_at touch
        return ident


def require_agent_scope(scope: str):
    """Dependency factory: require an active token carrying `scope`. Stashes
    audit context on request.state for the middleware, then raises 401 (no/bad
    token) or 403 (valid token, missing scope). Cookie auth is ignored."""

    def _dep(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict:
        # record the presented prefix even on failure (auditable auth attempts)
        presented_prefix = tokens.prefix_of(tokens.parse_bearer(authorization) or "")
        request.state.agent_prefix = presented_prefix
        request.state.agent_name = None
        request.state.agent_scope_used = None

        ident = _resolve_session_identity(authorization)
        if ident is None:
            raise HTTPException(status_code=401, detail="invalid or expired token")
        if not tokens.has_scope(ident["scopes"], scope):
            # valid token, wrong scope — 403, audited with the token identity
            request.state.agent_prefix = ident["token_prefix"]
            request.state.agent_name = ident["agent_name"]
            raise HTTPException(status_code=403, detail=f"scope '{scope}' required")

        request.state.agent_prefix = ident["token_prefix"]
        request.state.agent_name = ident["agent_name"]
        request.state.agent_scope_used = scope
        return ident

    return _dep


# ---------------------------------------------------------------------------
# Audit middleware — one row per /agent request, success or failure (spec §5)
# ---------------------------------------------------------------------------
class AgentAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/agent"):
            return await call_next(request)
        started = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - started) * 1000)
        try:
            st = request.state
            route_obj = request.scope.get("route")
            route_tmpl = getattr(route_obj, "path", request.url.path)
            from apps.api.src.db import SessionLocal

            with SessionLocal() as s:
                audit.record(
                    s,
                    route=route_tmpl,
                    method=request.method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    agent_name=getattr(st, "agent_name", None),
                    token_prefix=getattr(st, "agent_prefix", None),
                    scope_used=getattr(st, "agent_scope_used", None),
                    idempotency_key=request.headers.get("Idempotency-Key"),
                )
        except Exception as exc:  # audit must never break the response
            logger.warning("agent_audit_middleware_failed err={}", exc)
        return response


# ---------------------------------------------------------------------------
# Routes (spec §4). whoami is real; data/job/draft bodies are the next slice.
# ---------------------------------------------------------------------------
@router.get("/whoami")
def whoami(ident: dict = Depends(require_agent_scope("R"))) -> dict:
    """Token introspection — no hash, no secret (spec §4). Requires any valid
    token; R is the minimum scope every token can hold in practice, and whoami
    is the authenticated-round-trip smoke check for the prototype."""
    return {
        "agent_name": ident["agent_name"],
        "token_prefix": ident["token_prefix"],
        "scopes": sorted(ident["scopes"]),
        "rate_limit_per_min": ident["rate_limit_per_min"],
    }


def _not_yet(what: str):
    raise HTTPException(status_code=501, detail=f"{what} not implemented in gateway v0")


@router.get("/recommendations")
def list_recommendations(_: dict = Depends(require_agent_scope("R"))):
    _not_yet("recommendations read")


@router.get("/portfolio")
def get_portfolio(_: dict = Depends(require_agent_scope("P"))):
    _not_yet("portfolio read")


@router.post("/jobs")
def submit_job(_: dict = Depends(require_agent_scope("B"))):
    _not_yet("offline job submission")


@router.post("/drafts")
def create_draft(_: dict = Depends(require_agent_scope("D"))):
    _not_yet("draft report creation")
