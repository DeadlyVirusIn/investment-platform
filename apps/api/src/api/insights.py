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

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from apps.api.src.domain.agents import llm_client
from apps.api.src.domain.agents.registry import AgentKind, BANNER


router = APIRouter(prefix="/insights", tags=["insights"])


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

    use_payload = payload if payload else _FIXTURES[agent_kind]

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
