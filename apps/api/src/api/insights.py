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

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from apps.api.src.domain.agents import llm_client
from apps.api.src.domain.agents.registry import AgentKind, BANNER


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
    `error` key."""
    return JSONResponse(
        status_code=503,
        content={"error": "agent insights disabled"},
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


@router.get("/{kind}")
async def get_insight(
    kind: str,
    payload: dict[str, Any] | None = Body(default=None),
    payload_b64: str | None = _PAYLOAD_QUERY,
) -> Any:
    # Feature-flag guard runs FIRST so a disabled deployment never
    # touches the SDK or even resolves the kind.
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

    try:
        result = llm_client.generate_insight(agent_kind, use_payload)
    except llm_client.InsightsDisabled:
        # Race: flag flipped off mid-request, or SDK import failed.
        return _disabled_response()
    except llm_client.UnsafeResponseError as exc:
        return _unsafe_response(str(exc))

    return {
        "kind": result.kind.value,
        "model": result.model,
        "generated_at": result.generated_at,
        "banner": BANNER,
        "content_markdown": result.content_markdown,
        "source_endpoint": result.source_endpoint,
        "llm_enabled": True,
    }
