"""Phase F2 — read-only AI insight HTTP endpoint.

Hard rules:
  * GET only. The router declares no POST/PUT/PATCH/DELETE handlers.
  * No DB writes. No persistence. No caching. No background tasks.
  * No `Session` dependency, no `apps.api.src.db` import — enforced
    by `test_insights_feature_flag.py` source-level scan.
  * Returns HTTP 503 with `{"error": "agent insights disabled"}`
    whenever the feature flag is off OR the API key is missing.
    NEVER attempts the LLM call in that state.
  * Built-in fixture payloads exist solely so an offline TestClient
    request can hit the path without a body. Any real caller is
    expected to POST a JSON body matching the kind's source-endpoint
    response shape.
  * If the safety layer rejects the LLM response, returns HTTP 502
    with a redacted reason — the unsafe content is NEVER surfaced.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from fastapi.exceptions import HTTPException as _HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.db.models import AgentInsight
from apps.api.src.domain.agents import cache as insight_cache
from apps.api.src.domain.agents import llm_client
from apps.api.src.domain.agents.registry import AgentKind, BANNER, REGISTRY
from apps.api.src.domain.agents.safety import scrub_sensitive_ids


router = APIRouter(prefix="/insights", tags=["insights"])


# Browser fetch() rejects a request body on GET, so the F3 frontend
# transports the row-specific payload via a base64url-encoded query
# parameter. The route still accepts a JSON body when the client can
# send one (TestClient, server-to-server). Behavior is unchanged when
# neither is provided — the per-kind fixture is used.
_PAYLOAD_QUERY = Query(
    default=None,
    description=(
        "Optional base64url-encoded JSON object. Used when the "
        "client cannot send a request body (e.g., browser GET)."
    ),
)


def _decode_payload_b64(raw: str) -> dict[str, Any]:
    """Decode a base64url string into a JSON object. Raises
    ValueError on any failure — caller maps that to HTTP 400."""
    pad = "=" * (-len(raw) % 4)
    try:
        decoded_bytes = base64.urlsafe_b64decode(raw + pad)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"base64url decode failed: {exc}") from exc
    try:
        text = decoded_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"utf-8 decode failed: {exc}") from exc
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON decode failed: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("payload_b64 must encode a JSON object")
    return obj


# Built-in fixture payloads — used only when the request body is
# omitted. Keys mirror each kind's `required_payload_fields` so the
# narrator's "Missing payload fields" line stays empty in the
# offline path.
_FIXTURES: dict[AgentKind, dict[str, Any]] = {
    AgentKind.TRADE_QUALITY: {
        "score": 72,
        "grade": "B",
        "thesis": "winner_trim",
        "completeness": "full",
        "components": {
            "entry": 18, "return": 22,
            "hold": 12, "exit_or_status": 10,
            "completeness": 10,
        },
        "reasons": [
            "Entry: favorable fill.",
            "Return: 4 percent realized.",
        ],
    },
    AgentKind.RISK_COMMENTARY: {
        "nav": 100000,
        "cash": 5000,
        "exposure_value": 95000,
        "exposure_pct": 0.95,
        "open_positions_count": 12,
        "mark_unavailable": False,
    },
    AgentKind.EXIT_REVIEW: {
        "n_closed": 0,
        "n_winners": 0,
        "n_losers": 0,
        "win_rate": None,
        "realized_pnl_total": 0,
        "tp_sl_effectiveness": {
            "tp_count": 0, "sl_count": 0,
            "tp_total_pnl": 0, "sl_total_pnl": 0,
        },
        "small_sample_warning": (
            "No closed trades yet — directional only."
        ),
    },
    AgentKind.OPTIONS_THESIS: {
        "rule_id": "long_call_atm",
        "underlying": "AMZN",
        "total_score": 71,
        "qualified": True,
    },
}


def _disabled_response() -> JSONResponse:
    """Flat error shape per spec — NOT FastAPI's default `{"detail":
    ...}` wrapper. Returned as-is so clients can pattern-match on the
    `error` key. The `cache` field is included so the F3 frontend can
    surface the same chip semantics on every response."""
    return JSONResponse(
        status_code=503,
        content={
            "error": "agent insights disabled",
            "cache": "disabled",
        },
    )


def _unsafe_response(reason: str) -> JSONResponse:
    """502 when post-call safety rejects the model body. The
    `reason` field summarizes which gate fired; it never echoes
    the unsafe content."""
    return JSONResponse(
        status_code=502,
        content={
            "error": "insight rejected by safety layer",
            "reason": reason,
        },
    )


# ---------------------------------------------------------------------
# F5 — operational status endpoint (read-only, no LLM, no exec reads)
# Declared BEFORE the `/{kind}` catch-all so FastAPI's registration-
# order routing matches `/status` exactly rather than treating
# "status" as a `kind` parameter.
# ---------------------------------------------------------------------

def _count_cache_rows(db: Session | None) -> int:
    """Best-effort row count over `agent_insight` only. Returns 0
    when DB unavailable or the table doesn't exist yet. NEVER
    queries any other table."""
    if db is None:
        return 0
    try:
        return int(db.execute(
            select(func.count()).select_from(AgentInsight),
        ).scalar() or 0)
    except (OperationalError, ProgrammingError):
        return 0


@router.get("/status")
def get_status(
    db: Session | None = Depends(get_session),
) -> dict[str, Any]:
    """Read-only health/visibility endpoint. Surfaces the feature
    flag, configured model, and a count of cache rows so an
    operator can verify the layer is dormant by default. NEVER
    calls the LLM. NEVER reads from any table other than
    `agent_insight`. NEVER returns the API key value — the
    `llm_configured` boolean reports presence only."""
    enabled = bool(getattr(settings, "AGENT_INSIGHTS_ENABLED", False))
    api_key = (
        getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    ).strip()
    return {
        "enabled": enabled,
        "model": settings.AGENT_INSIGHTS_MODEL,
        "cache_enabled": True,
        "cache_rows": _count_cache_rows(db),
        "banner": BANNER,
        "execution_linked": False,
        "llm_configured": bool(api_key),
    }


@router.get("/{kind}")
async def get_insight(
    kind: str,
    payload: dict[str, Any] | None = Body(default=None),
    payload_b64: str | None = _PAYLOAD_QUERY,
    db: Session | None = Depends(get_session),
) -> Any:
    # Feature-flag guard runs FIRST so a disabled deployment never
    # touches the SDK or the cache. NEVER read or write `agent_insight`
    # while the flag is off.
    if not llm_client.is_enabled():
        return _disabled_response()

    # Resolve the agent kind. 404 (not 422) so a typo'd path does
    # not leak the enum members in a validation-error body.
    try:
        agent_kind = AgentKind(kind)
    except ValueError:
        return JSONResponse(
            status_code=404,
            content={"error": f"unknown kind: {kind!r}"},
        )

    # Resolution order: explicit body → query-param payload →
    # built-in per-kind fixture. The fixture path is what the spec
    # refers to as "test fixture payload only".
    use_payload: dict[str, Any] | None = payload if payload else None
    if use_payload is None and payload_b64:
        try:
            use_payload = _decode_payload_b64(payload_b64)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid payload_b64", "reason": str(exc)},
            )
    if use_payload is None:
        use_payload = _FIXTURES[agent_kind]

    meta = REGISTRY[agent_kind]
    model = settings.AGENT_INSIGHTS_MODEL

    # Compute the hash over the SCRUBBED payload so two requests that
    # differ only in UUID values produce the same key. This is also
    # the safety guard: even if the caller smuggled a UUID through
    # `payload_b64`, the cache row stores only the redacted form.
    scrubbed = scrub_sensitive_ids(use_payload)
    payload_hash = insight_cache.compute_payload_hash(
        agent_kind, scrubbed,
        source_endpoint=meta.source_endpoint,
    )

    # Cache lookup (graceful no-op if DB unavailable).
    hit = insight_cache.lookup(
        db,
        kind=agent_kind, payload_hash=payload_hash,
        model=model,
    )
    if hit is not None:
        return {
            "kind": hit.kind,
            "model": hit.model,
            "generated_at": hit.created_at.isoformat(),
            "banner": hit.banner,
            "content_markdown": hit.content_markdown,
            "source_endpoint": hit.source_endpoint,
            "llm_enabled": True,
            "cache": "hit",
        }

    # Miss → call the LLM. Unsafe responses NEVER reach the cache.
    try:
        result = llm_client.generate_insight(agent_kind, use_payload)
    except llm_client.InsightsDisabled:
        # Race: flag flipped off mid-request, or SDK import failed.
        return _disabled_response()
    except llm_client.UnsafeResponseError as exc:
        return _unsafe_response(str(exc))

    # Safe response — attempt to cache. A validation error on the
    # write path means the response is still safe enough to return
    # (pre/post safety gates already passed) but we refuse to
    # persist; client gets the body without `cache: "hit"` semantics
    # on a future request. DB unavailability silently degrades to
    # uncached responses.
    try:
        insight_cache.store(
            db,
            kind=agent_kind,
            payload_hash=payload_hash,
            payload_redacted=scrubbed,
            content_markdown=result.content_markdown,
            model=result.model,
            source_endpoint=result.source_endpoint,
            banner=BANNER,
        )
    except insight_cache.CacheValidationError:
        pass

    return {
        "kind": result.kind.value,
        "model": result.model,
        "generated_at": result.generated_at,
        "banner": BANNER,
        "content_markdown": result.content_markdown,
        "source_endpoint": result.source_endpoint,
        "llm_enabled": True,
        "cache": "miss",
    }


# ---------------------------------------------------------------------
# F5 — admin-only cache maintenance (DELETE)
# ---------------------------------------------------------------------

def _require_admin_token(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> None:
    """Same header-based auth pattern as research_manual. The route
    is only mounted when `AGENT_INSIGHTS_ADMIN_MAINTENANCE_ENABLED`
    is true AND `RESEARCH_ADMIN_TOKEN` is non-empty (see main.py),
    so reaching this handler means a token is configured."""
    expected = (settings.RESEARCH_ADMIN_TOKEN or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="admin_token_unset")
    if (x_admin_token or "").strip() != expected:
        raise HTTPException(status_code=403, detail="invalid_admin_token")


# Separate router for the admin-only DELETE so main.py can mount
# it conditionally without affecting the public `insights` router.
admin_router = APIRouter(prefix="/insights", tags=["insights-admin"])


@admin_router.delete("/cache")
def delete_cache(
    db: Session = Depends(get_session),
    _: None = Depends(_require_admin_token),
) -> dict[str, Any]:
    """Truncate ONLY the `agent_insight` table. Returns a count of
    rows removed. Does NOT touch any other table; does NOT cascade
    anywhere. Mounting is gated by
    `AGENT_INSIGHTS_ADMIN_MAINTENANCE_ENABLED=true` so a default
    deployment cannot expose this surface."""
    try:
        n = int(db.execute(
            select(func.count()).select_from(AgentInsight),
        ).scalar() or 0)
        db.query(AgentInsight).delete()
        db.commit()
    except (OperationalError, ProgrammingError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=503, detail=f"cache table unavailable: {exc}",
        ) from exc
    return {"deleted_rows": n, "table": "agent_insight"}
