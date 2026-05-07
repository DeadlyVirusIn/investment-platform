"""Phase F4 — read-only insight cache.

Provides:
  * `compute_payload_hash(kind, scrubbed_payload, …)` — deterministic
    SHA-256 fingerprint over (kind, scrubbed_payload, source_endpoint,
    safety_version). Sort-keys + tight JSON separators make the hash
    stable across whitespace and key reordering.
  * `lookup(session, …)` — single-row SELECT. Returns None when
    nothing is cached, when the session is None, or when the DB is
    unavailable (operational error / missing table). Never raises.
  * `store(session, …)` — single-row INSERT. Validates banner,
    non-empty body, and absence of raw UUIDs in the redacted
    payload BEFORE writing. On unique-constraint conflict (race
    between concurrent writers) re-fetches the existing row.

Hard rules:
  * NO writes to trading / paper / options / decision / replay
    tables. Only `agent_insight`.
  * NO caching of unsafe responses. The endpoint MUST call this
    module only after `llm_client.generate_insight` returned
    successfully.
  * NO raw UUIDs in `payload_redacted` — defensive scan rejects
    any row whose payload still carries one. The narrator already
    scrubs upstream; this is belt-and-suspenders.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import (
    IntegrityError, OperationalError, ProgrammingError,
)
from sqlalchemy.orm import Session

from apps.api.src.db.models import AgentInsight
from apps.api.src.domain.agents.registry import AgentKind, BANNER


# Bumped whenever a safety rule materially changes. Forces a cache
# miss for every existing row so old narratives can't surface under
# the new safety contract.
SAFETY_VERSION = "v1"


# UUID detector — matches the canonical 8-4-4-4-12 hex pattern.
# Used to reject any payload that still carries a raw identifier
# after the narrator's scrub.
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


class CacheValidationError(ValueError):
    """Raised when a cache write would violate a hard invariant
    (banner mismatch, empty body, raw UUID in redacted payload).
    The endpoint converts this into a non-cached 200 — the client
    still gets the insight; we just refuse to persist it."""


# ---------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------

def compute_payload_hash(
    kind: AgentKind,
    scrubbed_payload: dict,
    *,
    source_endpoint: str,
    safety_version: str = SAFETY_VERSION,
) -> str:
    """Deterministic fingerprint for cache lookup. Inputs:
      * kind                — namespace; different kinds never collide.
      * scrubbed_payload    — the redacted payload (UUIDs already
                              replaced) so the hash is stable across
                              UUID-only changes.
      * source_endpoint     — narrator template fingerprint by proxy.
      * safety_version      — forces miss on safety contract change.

    JSON serialization uses sort_keys=True + separators=(",", ":") so
    whitespace / key-order differences produce the same hash.
    `default=str` accepts Decimal / datetime / Enum without raising.
    """
    body = {
        "kind": kind.value,
        "source_endpoint": source_endpoint,
        "safety_version": safety_version,
        "payload": scrubbed_payload,
    }
    blob = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------

def lookup(
    session: Session | None,
    *,
    kind: AgentKind,
    payload_hash: str,
    model: str,
    safety_version: str = SAFETY_VERSION,
) -> AgentInsight | None:
    """Return the cached row if present. Returns None when:
      * session is None (cache disabled / dependency override),
      * the DB connection is unavailable,
      * the table doesn't exist yet (migration pending),
      * no row matches the natural key.

    Never raises. A failing cache lookup MUST degrade to a fresh
    LLM call — the caller proceeds as if the cache did not exist.
    """
    if session is None:
        return None
    try:
        stmt = select(AgentInsight).where(
            AgentInsight.kind == kind.value,
            AgentInsight.payload_hash == payload_hash,
            AgentInsight.model == model,
            AgentInsight.safety_version == safety_version,
        )
        return session.execute(stmt).scalar_one_or_none()
    except (OperationalError, ProgrammingError):
        return None


# ---------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------

def _scan_for_uuids(payload: Any) -> bool:
    """Recursive search for raw UUIDs anywhere in the payload tree.
    Booleans / numbers / None are skipped; only strings can match."""
    if isinstance(payload, dict):
        return any(_scan_for_uuids(v) for v in payload.values())
    if isinstance(payload, (list, tuple)):
        return any(_scan_for_uuids(x) for x in payload)
    if isinstance(payload, str):
        return bool(_UUID_RE.search(payload))
    return False


def validate_cacheable(
    *,
    payload_redacted: dict,
    content_markdown: str,
    banner: str,
) -> None:
    """Pre-write invariants. Raises `CacheValidationError` on any
    violation. Exposed so unit tests can assert each rule
    independently of an open DB session."""
    if banner != BANNER:
        raise CacheValidationError(
            f"banner mismatch: got {banner!r}"
        )
    if not content_markdown or not content_markdown.strip():
        raise CacheValidationError("content_markdown is empty")
    if BANNER not in content_markdown:
        raise CacheValidationError(
            "content_markdown is missing the canonical banner"
        )
    if _scan_for_uuids(payload_redacted):
        raise CacheValidationError(
            "payload_redacted still contains a raw UUID-like string"
        )


def store(
    session: Session | None,
    *,
    kind: AgentKind,
    payload_hash: str,
    payload_redacted: dict,
    content_markdown: str,
    model: str,
    source_endpoint: str,
    banner: str,
    safety_version: str = SAFETY_VERSION,
) -> AgentInsight | None:
    """Insert a single cache row. Returns the row on success. Returns
    None when the session is None (cache disabled / dependency
    override) or the DB is unavailable. Re-fetches and returns the
    existing row on unique-constraint conflict (concurrent-writer
    race). Raises `CacheValidationError` when a pre-write invariant
    fails — the caller MUST convert that into a non-cached 200."""
    # Validation runs unconditionally so unit tests can assert the
    # invariants even without a session.
    validate_cacheable(
        payload_redacted=payload_redacted,
        content_markdown=content_markdown,
        banner=banner,
    )
    if session is None:
        return None

    row = AgentInsight(
        kind=kind.value,
        payload_hash=payload_hash,
        payload_redacted=payload_redacted,
        content_markdown=content_markdown,
        model=model,
        source_endpoint=source_endpoint,
        banner=banner,
        safety_version=safety_version,
    )
    try:
        session.add(row)
        session.commit()
        return row
    except IntegrityError:
        session.rollback()
        return lookup(
            session, kind=kind, payload_hash=payload_hash,
            model=model, safety_version=safety_version,
        )
    except (OperationalError, ProgrammingError):
        session.rollback()
        return None
