"""Active rule loader — reads alpha_rule_active, validates, caches briefly.

Fail-closed: any validation/load error returns an empty list plus warning
log. Paper pipeline never crashes because of a malformed rule row.
"""

from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

# Runtime-allowed rule types — same as executor ALLOWED_AUTO_TYPES
ALLOWED_RUNTIME_TYPES = {
    "reduce_weight",
    "tighten_filters",
    "execution_guardrail",
    "restrict_concentrated_trades",
    "tighten_threshold",
}

FORBIDDEN_RUNTIME_TYPES = {
    "increase_weight",
    "increase_position_size",
    "remove_guardrail",
    "disable_filter",
    "add_new_trade",
    "override_engine",
}


@dataclass(frozen=True)
class ActiveRule:
    rule_id: str
    rule_type: str
    parameters: dict[str, Any]
    applied_at: dt.datetime
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "parameters": dict(self.parameters),
            "applied_at": self.applied_at.isoformat(),
            "status": self.status,
        }


# --- in-process cache (thread-safe, short TTL) ---
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[dt.datetime, list[ActiveRule]]] = {}


def load_active_rules(
    session: Session,
    *,
    cache_seconds: int = 60,
    force_refresh: bool = False,
) -> list[ActiveRule]:
    """Load validated active rules, fail-closed on error."""
    key = "default"
    now = dt.datetime.now(dt.timezone.utc)
    if not force_refresh:
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
            if cached and (now - cached[0]).total_seconds() < cache_seconds:
                return list(cached[1])
    try:
        rows = session.execute(text("""
            SELECT rule_id, rule_type, parameters, applied_at, status
            FROM alpha_rule_active
            WHERE status = 'active'
        """)).mappings().all()
    except Exception as e:
        logger.warning("rule_runtime: load failed: {}", e)
        return []

    out: list[ActiveRule] = []
    for r in rows:
        if not _validate_row(r):
            continue
        out.append(ActiveRule(
            rule_id=str(r["rule_id"]),
            rule_type=str(r["rule_type"]),
            parameters=dict(r["parameters"] or {}),
            applied_at=r["applied_at"],
            status=str(r["status"]),
        ))
    with _CACHE_LOCK:
        _CACHE[key] = (now, list(out))
    return out


def invalidate_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _validate_row(r: dict[str, Any]) -> bool:
    rt = str(r.get("rule_type") or "")
    if rt in FORBIDDEN_RUNTIME_TYPES:
        logger.warning(
            "rule_runtime: rejecting FORBIDDEN rule_type={} rule_id={}",
            rt, r.get("rule_id"),
        )
        return False
    if rt not in ALLOWED_RUNTIME_TYPES:
        logger.warning(
            "rule_runtime: rejecting unknown rule_type={} rule_id={}",
            rt, r.get("rule_id"),
        )
        return False
    params = r.get("parameters")
    if params is not None and not isinstance(params, dict):
        logger.warning(
            "rule_runtime: invalid parameters for rule_id={}", r.get("rule_id"),
        )
        return False
    return True
