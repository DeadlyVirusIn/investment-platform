"""Agent Gateway token model — generation, hashing, resolution (spec §2/§3).

Design mirrors `auth/identity.py`: the core functions take a SQLAlchemy
Session so they are unit-testable without a TestClient or the dev DB, and
the pure helpers (generation, scope grammar, bearer parsing) need no DB at
all.

Security invariants enforced here (not merely documented):
  * the DB stores only sha256(full_token); the secret is returned once from
    `create_token` and never persisted or logged (spec §2).
  * `resolve_token` compares hashes in CONSTANT time (hmac.compare_digest)
    and performs a dummy compare on a prefix miss, so neither a wrong secret
    nor an unknown prefix is distinguishable by timing.
  * expired / revoked / non-active tokens resolve to None (checked in SQL);
    revocation is effective immediately (no cache — spec §2).
  * scopes are validated against {R,P,B,D} at write time; there is no T /
    live-trading scope and none can be minted (spec §3).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

# arthos_at_<prefix(8)><secret(32)>  — 40 hex chars after the namespace.
NAMESPACE = "arthos_at_"
PREFIX_LEN = 8
BODY_LEN = 40  # prefix(8) + secret(32)

# The four scopes and nothing else. Canonical serialization order.
VALID_SCOPES = ("R", "P", "B", "D")
_VALID_SET = set(VALID_SCOPES)

# constant fed to the dummy compare on a prefix miss (timing flattening)
_DUMMY_HASH = "0" * 64


# ---------------------------------------------------------------------------
# Pure helpers (no DB)
# ---------------------------------------------------------------------------
def hash_token(full_token: str) -> str:
    """sha256 hex of the full token string. (sha256 not bcrypt: the secret
    carries 160 bits of server entropy — a password KDF solves a problem this
    design does not have; constant lookup cost matters — spec §2.)"""
    return hashlib.sha256(full_token.encode("utf-8")).hexdigest()


def generate_token() -> tuple[str, str, str]:
    """Return (full_token, token_prefix, token_hash). The full token is shown
    to the owner exactly once; only prefix + hash are ever stored."""
    body = secrets.token_hex(BODY_LEN // 2)  # 40 hex chars
    full = NAMESPACE + body
    return full, body[:PREFIX_LEN], hash_token(full)


def normalize_scopes(scopes: str | list[str] | tuple[str, ...]) -> str:
    """Validate + canonicalize a scope request into the DB string form
    'R,P,B,D' (subset, deduped, fixed order). Raises ValueError on an empty
    set or any letter outside {R,P,B,D} — including 'T'."""
    if isinstance(scopes, str):
        raw = [s.strip().upper() for s in scopes.split(",")]
    else:
        raw = [str(s).strip().upper() for s in scopes]
    wanted = {s for s in raw if s}
    if not wanted:
        raise ValueError("at least one scope required")
    bad = wanted - _VALID_SET
    if bad:
        raise ValueError(f"invalid scope(s): {','.join(sorted(bad))}")
    return ",".join(s for s in VALID_SCOPES if s in wanted)


def scopes_to_set(scopes: str) -> set[str]:
    return {s for s in scopes.split(",") if s}


def has_scope(token_scopes: set[str] | str, required: str) -> bool:
    if isinstance(token_scopes, str):
        token_scopes = scopes_to_set(token_scopes)
    return required in token_scopes


def parse_bearer(authorization: str | None) -> str | None:
    """Extract a gateway token from an `Authorization: Bearer arthos_at_…`
    header. Returns the full token, or None if the header is missing,
    malformed, not a Bearer, or not in the arthos gateway namespace. Cookie
    sessions are never accepted here (spec §4: agent auth is Bearer-only)."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    tok = parts[1].strip()
    if not tok.startswith(NAMESPACE) or len(tok) != len(NAMESPACE) + BODY_LEN:
        return None
    return tok


def prefix_of(full_token: str) -> str | None:
    if not full_token or not full_token.startswith(NAMESPACE):
        return None
    body = full_token[len(NAMESPACE):]
    if len(body) != BODY_LEN:
        return None
    return body[:PREFIX_LEN]


# ---------------------------------------------------------------------------
# DB operations (owner-only management; resolution on every gateway request)
# ---------------------------------------------------------------------------
def create_token(
    db: Session, *,
    agent_name: str,
    scopes: str | list[str],
    created_by: str,
    ttl_days: int,
    max_ttl_days: int,
    rate_limit_per_min: int = 60,
    max_request_bytes: int = 65536,
) -> tuple[str, dict]:
    """Mint a token. Returns (full_token_SHOWN_ONCE, metadata). The secret is
    never persisted — only prefix + hash. Owner-only per spec §2; the caller
    (owner console router) enforces require_owner."""
    name = (agent_name or "").strip()
    if not name or len(name) > 64:
        raise ValueError("agent_name required (1-64 chars)")
    scope_str = normalize_scopes(scopes)
    ttl = int(ttl_days)
    if ttl < 1 or ttl > int(max_ttl_days):
        raise ValueError(f"ttl_days must be 1..{max_ttl_days}")
    rl = int(rate_limit_per_min)
    if rl < 1 or rl > 240:
        raise ValueError("rate_limit_per_min must be 1..240")
    full, prefix, thash = generate_token()
    tid = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO agent_token
              (id, agent_name, token_prefix, token_hash, scopes, status,
               expires_at, rate_limit_per_min, max_request_bytes, created_by,
               created_at)
            VALUES
              (:id, :name, :prefix, :hash, :scopes, 'active',
               now() + (:ttl || ' days')::interval, :rl, :mrb, :cb, now())
            """
        ),
        {
            "id": tid, "name": name, "prefix": prefix, "hash": thash,
            "scopes": scope_str, "ttl": str(ttl), "rl": rl,
            "mrb": int(max_request_bytes), "cb": created_by,
        },
    )
    meta = {
        "id": tid, "agent_name": name, "token_prefix": prefix,
        "scopes": scope_str, "rate_limit_per_min": rl,
        "max_request_bytes": int(max_request_bytes),
    }
    return full, meta


def list_tokens(db: Session) -> list[dict]:
    """Metadata + prefix only — NEVER the hash or any secret (spec §2)."""
    rows = db.execute(
        text(
            """
            SELECT id, agent_name, token_prefix, scopes, status, expires_at,
                   rate_limit_per_min, created_at, last_used_at,
                   revoked_at, revoked_reason
            FROM agent_token
            ORDER BY created_at DESC
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def revoke_token(db: Session, *, token_id: str, reason: str | None = None) -> bool:
    """Revoke by id. Effective immediately (resolve_token filters on status).
    Idempotent: revoking an already-revoked token returns False."""
    res = db.execute(
        text(
            """
            UPDATE agent_token
               SET status = 'revoked', revoked_at = now(),
                   revoked_reason = :r
             WHERE id = :id AND status = 'active'
            """
        ),
        {"id": token_id, "r": (reason or "").strip() or None},
    )
    return (res.rowcount or 0) > 0


def resolve_token(db: Session, full_token: str | None, *, touch: bool = True) -> dict | None:
    """Resolve a presented token to its identity, or None. Returns
    {id, agent_name, scopes(set), token_prefix, rate_limit_per_min,
    max_request_bytes} for an ACTIVE, non-expired, non-revoked token whose
    hash matches. Constant-time hash compare; dummy compare on prefix miss so
    existence is not a timing oracle. `touch` updates last_used_at."""
    prefix = prefix_of(full_token or "")
    if prefix is None:
        hmac.compare_digest(_DUMMY_HASH, _DUMMY_HASH)  # flatten timing
        return None
    row = db.execute(
        text(
            """
            SELECT id, agent_name, token_hash, scopes, rate_limit_per_min,
                   max_request_bytes, created_by
            FROM agent_token
            WHERE token_prefix = :p
              AND status = 'active'
              AND revoked_at IS NULL
              AND expires_at > now()
            """
        ),
        {"p": prefix},
    ).mappings().first()
    presented = hash_token(full_token)  # type: ignore[arg-type]
    if row is None:
        hmac.compare_digest(presented, _DUMMY_HASH)  # timing flatten
        return None
    if not hmac.compare_digest(row["token_hash"], presented):
        return None
    if touch:
        db.execute(
            text("UPDATE agent_token SET last_used_at = now() WHERE id = :id"),
            {"id": row["id"]},
        )
    return {
        "id": row["id"],
        "agent_name": row["agent_name"],
        "scopes": scopes_to_set(row["scopes"]),
        "token_prefix": prefix,
        "rate_limit_per_min": row["rate_limit_per_min"],
        "max_request_bytes": row["max_request_bytes"],
        # owner identity for P-scope ownership resolution (spec §7.4:
        # identity is server-resolved from the token, never client-supplied)
        "created_by": row["created_by"],
    }


def token_expiry_utc(days: int) -> dt.datetime:
    """Helper for callers/tests that need the computed expiry in Python."""
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=int(days))
