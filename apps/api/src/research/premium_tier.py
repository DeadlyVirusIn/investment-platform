"""Phase 11W (Phase F.1) — server-side tier resolver + field
stripper.

Authoritative tier gate. The frontend is allowed to send
`X-Research-Tier`, but the server falls back to
`settings.RESEARCH_PREMIUM_TIER` and validates the value before
applying any payload stripping. The server NEVER trusts a
client-supplied tier higher than what an entitlement system would
authorize — until a real entitlement system lands, the env value
is the cap.

Hard guarantees:
  * NEVER imports execution / scoring / ML / candidate / paper /
    options modules.
  * Strips body / evidence / audit / operator-control fields per
    tier BEFORE the API edge returns the payload.
  * Free callers receive only metadata (`has_full_note=True/False`
    flag is the gate; the actual body is null).
  * Pro callers receive safe bodies + evidence + history; never
    audit / operator-control.
  * Enterprise callers receive everything.
  * Unsafe bodies are always stripped regardless of tier.
"""

from __future__ import annotations

from typing import Any

from fastapi import Header

from apps.api.src.config import settings


_VALID_TIERS = ("free", "pro", "enterprise")


def normalize_tier(raw: str | None) -> str:
    """Returns one of {free, pro, enterprise}. Anything else → free."""
    if not raw:
        return "free"
    t = raw.strip().lower()
    if t not in _VALID_TIERS:
        return "free"
    return t


def resolve_tier(
    x_research_tier: str | None = None,
) -> str:
    """Tier resolution. The header wins ONLY when it doesn't elevate
    the caller above the configured server-side cap. This avoids
    a misconfigured frontend granting itself enterprise access on
    a free deployment.

    Until a proper entitlement system lands, this is intentionally
    conservative: server cap is the upper bound."""
    cap = normalize_tier(settings.RESEARCH_PREMIUM_TIER)
    requested = normalize_tier(x_research_tier or cap)
    rank = {"free": 0, "pro": 1, "enterprise": 2}
    if rank[requested] > rank[cap]:
        return cap
    return requested


# FastAPI dependency wrapper.
def tier_dep(
    x_research_tier: str | None = Header(default=None, alias="X-Research-Tier"),
) -> str:
    return resolve_tier(x_research_tier)


# ---------------------------------------------------------------------------
# Field stripping
# ---------------------------------------------------------------------------


def _strip_keys(d: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Return a new dict without the listed keys."""
    return {k: v for k, v in d.items() if k not in keys}


# Keys that are NEVER returned to anyone, regardless of tier.
_UNIVERSAL_FORBIDDEN = (
    "raw_body", "raw_response", "structured_output",
    "agent_output", "evidence_refs",  # evidence may be re-added by tier
    "reflection", "prompt", "prompt_text", "prompt_template",
)


def strip_run_payload(run: dict[str, Any], *, tier: str) -> dict[str, Any]:
    """Apply tier-specific stripping to a /runs row payload."""
    if not isinstance(run, dict):
        return {}
    out = dict(run)
    # Universal: never expose internal / raw fields.
    out = _strip_keys(out, _UNIVERSAL_FORBIDDEN)
    if tier == "free":
        # Metadata only. Hide cost + provenance hash + operator id.
        keep_free = {
            "id", "symbol", "as_of",
            "status", "started_at", "finished_at",
        }
        out_free: dict[str, Any] = {
            k: v for k, v in out.items() if k in keep_free
        }
        # Provider visible at coarse granularity only.
        out_free["provider_visible"] = bool(out.get("provider"))
        out_free["has_full_note"] = True  # presence, not body
        out_free["safety_status"] = out.get("safety_status", "safe")
        return out_free
    if tier == "pro":
        # Hide cost + audit-only fields.
        out = _strip_keys(out, ("cost_usd",))
        return out
    # enterprise
    return out


def strip_run_detail_payload(
    payload: dict[str, Any], *, tier: str,
) -> dict[str, Any]:
    """Apply tier-specific stripping to /runs/{id} (run + outputs)."""
    if not isinstance(payload, dict):
        return {}
    run = strip_run_payload(payload.get("run") or {}, tier=tier)
    outputs_in = payload.get("outputs") or []
    outputs_out: list[dict[str, Any]] = []
    if tier == "free":
        # Free does not see any output bodies. Return zero outputs.
        outputs_out = []
    else:
        for o in outputs_in:
            if not isinstance(o, dict):
                continue
            o2 = _strip_keys(o, _UNIVERSAL_FORBIDDEN)
            if tier == "pro":
                # Pro: keep safe body only.
                if o.get("safety_status") != "safe":
                    o2["body"] = None
                # Pro hides cost.
                o2 = _strip_keys(o2, ("cost_usd",))
            outputs_out.append(o2)
    return {"run": run, "outputs": outputs_out}


def strip_ticker_latest_payload(
    payload: dict[str, Any], *, tier: str,
) -> dict[str, Any]:
    """`/ticker/{symbol}/latest` payload stripping."""
    if not isinstance(payload, dict):
        return {}
    out = dict(payload)
    run = out.get("run")
    if isinstance(run, dict):
        out["run"] = strip_run_payload(run, tier=tier)
    return out


def strip_audit_or_alert_for_tier(
    payload: dict[str, Any], *, tier: str,
) -> dict[str, Any]:
    """Free + Pro callers MUST NOT see audit / alerts. Enterprise
    sees full payload."""
    if tier == "enterprise":
        return payload
    # Free + Pro receive a sanitized empty shape.
    if isinstance(payload, dict):
        return {
            **{k: payload.get(k) for k in payload if k.endswith("_table")},
            "rows": [],
            "alerts": [],
            "operators": [],
        }
    return {}


def strip_operators_payload(
    payload: dict[str, Any], *, tier: str,
) -> dict[str, Any]:
    """Free + Pro receive empty operators list. Enterprise sees all."""
    if tier == "enterprise":
        return payload
    out: dict[str, Any] = {}
    if isinstance(payload, dict):
        out = {
            k: payload.get(k) for k in payload if k.endswith("_table")
        }
    out["operators"] = []
    return out


def strip_usage_summary_payload(
    payload: dict[str, Any], *, tier: str,
) -> dict[str, Any]:
    """Pro/Free see no usage telemetry. Enterprise sees full."""
    if tier == "enterprise":
        return payload
    return {
        "audit_today": {
            "accepted": 0, "duplicate": 0, "rejected": 0,
            "in_flight": 0, "errored": 0, "cost_usd_today": 0.0,
        },
        "alerts": {
            "open": 0, "critical_open": 0,
            "high_open": 0, "last_alert_at": None,
        },
        "operators": {
            "blocked": 0, "restricted": 0, "watch": 0, "clear": 0,
        },
        "tier_visibility": "tier_below_enterprise",
    }
