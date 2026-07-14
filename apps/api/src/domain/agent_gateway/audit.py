"""Agent Gateway audit trail — one append-only row per request (spec §5).

Written for EVERY request — success, 4xx, 5xx, rate-limited, auth-failed
(with whatever prefix was presented) — so no route can forget it. Stores
HASHES, not payloads: no market data, draft bodies, or secrets are ever
duplicated here. Append-only by contract — this module offers no UPDATE or
DELETE path (reasoning_audit precedent).
"""

from __future__ import annotations

import hashlib
import uuid

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session


def canonical_request_hash(
    method: str, path: str, query: str | None, body: bytes | None
) -> str:
    """sha256 of canonical(method, path, sorted query, body) — lets us spot
    replay bursts (identical hash) without storing the payload (spec §5)."""
    parts = [
        (method or "").upper(),
        path or "",
        "&".join(sorted((query or "").split("&"))) if query else "",
        hashlib.sha256(body).hexdigest() if body else "",
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def record(
    db: Session, *,
    route: str,
    method: str,
    status_code: int,
    duration_ms: int,
    agent_name: str | None = None,
    token_prefix: str | None = None,
    scope_used: str | None = None,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
) -> None:
    """Append one audit row and commit. Never raises into the request path —
    an audit-write failure is logged, not surfaced (the request outcome is
    already decided). `route` MUST be the templated path, never the raw URL."""
    try:
        db.execute(
            text(
                """
                INSERT INTO agent_audit
                  (id, agent_name, token_prefix, route, method, scope_used,
                   status_code, idempotency_key, duration_ms, request_hash,
                   created_at)
                VALUES
                  (:id, :an, :tp, :route, :method, :scope, :sc, :idem, :dur,
                   :rh, now())
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "an": agent_name,
                "tp": (token_prefix or None),
                "route": route[:128],
                "method": (method or "")[:8],
                "scope": (scope_used or None),
                "sc": int(status_code),
                "idem": (idempotency_key or None),
                "dur": int(duration_ms),
                "rh": (request_hash or None),
            },
        )
        db.commit()
    except Exception as exc:  # audit must never break the request
        db.rollback()
        logger.warning("agent_audit_write_failed route={} err={}", route, exc)
