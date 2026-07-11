"""Agent Gateway v0 — DB-backed token lifecycle + authz (Priority 7).

agent_token / agent_audit are migration-only tables (114_agent_gateway); the
ORM create_all harness does not build them, so this module ensures them
idempotently with the migration DDL — the M1C login_attempt precedent. The
migration's own up/down is validated separately on an ephemeral alembic
container (113_lesson precedent), not here.

Locks the security-critical DB behavior: hash-at-rest (the secret never lands
in the DB), constant-time resolve, immediate revocation, expiry enforcement,
and that `list_tokens` never leaks a hash.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.domain.agent_gateway import tokens

pytestmark = pytest.mark.integration

_DDL_TOKEN = """
CREATE TABLE IF NOT EXISTS agent_token (
    id VARCHAR(36) PRIMARY KEY,
    agent_name VARCHAR(64) NOT NULL,
    token_prefix VARCHAR(8) NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    scopes VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    expires_at TIMESTAMPTZ NOT NULL,
    rate_limit_per_min INTEGER NOT NULL DEFAULT 60,
    max_request_bytes INTEGER NOT NULL DEFAULT 65536,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    revoked_reason TEXT,
    CONSTRAINT uq_agent_token_prefix UNIQUE (token_prefix),
    CONSTRAINT uq_agent_token_hash UNIQUE (token_hash),
    CONSTRAINT ck_agent_token_status CHECK (status IN ('active','revoked')),
    CONSTRAINT ck_agent_token_scopes CHECK (scopes ~ '^[RPBD](,[RPBD]){0,3}$'),
    CONSTRAINT ck_agent_token_rate CHECK (rate_limit_per_min BETWEEN 1 AND 240),
    CONSTRAINT ck_agent_token_revoked CHECK
        (status <> 'revoked' OR revoked_at IS NOT NULL)
);
"""
_DDL_AUDIT = """
CREATE TABLE IF NOT EXISTS agent_audit (
    id VARCHAR(36) PRIMARY KEY,
    agent_name VARCHAR(64),
    token_prefix VARCHAR(8),
    route VARCHAR(128) NOT NULL,
    method VARCHAR(8) NOT NULL,
    scope_used VARCHAR(4),
    status_code INTEGER NOT NULL,
    idempotency_key VARCHAR(64),
    duration_ms INTEGER NOT NULL,
    request_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@pytest.fixture
def db(pg_session: Session) -> Session:
    pg_session.execute(text(_DDL_TOKEN))
    pg_session.execute(text(_DDL_AUDIT))
    pg_session.execute(text("TRUNCATE agent_token, agent_audit"))
    pg_session.commit()
    return pg_session


def _mint(db: Session, scopes="R,P", ttl=30):
    return tokens.create_token(
        db, agent_name="research-claude", scopes=scopes,
        created_by="owner-uid", ttl_days=ttl, max_ttl_days=90,
    )


def test_create_then_resolve_roundtrip(db: Session):
    full, meta = _mint(db, scopes="R,P")
    db.commit()
    ident = tokens.resolve_token(db, full)
    assert ident is not None
    assert ident["agent_name"] == "research-claude"
    assert ident["scopes"] == {"R", "P"}
    assert ident["token_prefix"] == meta["token_prefix"]


def test_secret_never_stored_only_hash(db: Session):
    full, meta = _mint(db)
    db.commit()
    row = db.execute(
        text("SELECT token_hash FROM agent_token WHERE token_prefix=:p"),
        {"p": meta["token_prefix"]},
    ).mappings().first()
    assert row["token_hash"] == tokens.hash_token(full)
    assert full not in row["token_hash"]
    # the full secret appears nowhere in the row
    allcols = db.execute(text("SELECT * FROM agent_token")).mappings().first()
    assert full not in " ".join(str(v) for v in allcols.values())


def test_wrong_secret_same_prefix_rejected(db: Session):
    full, meta = _mint(db)
    db.commit()
    forged = tokens.NAMESPACE + meta["token_prefix"] + "0" * 32
    assert tokens.resolve_token(db, forged) is None


def test_revocation_immediate(db: Session):
    full, meta = _mint(db)
    db.commit()
    assert tokens.resolve_token(db, full) is not None
    assert tokens.revoke_token(db, token_id=meta["id"], reason="test") is True
    db.commit()
    assert tokens.resolve_token(db, full) is None
    # idempotent: second revoke is a no-op
    assert tokens.revoke_token(db, token_id=meta["id"]) is False


def test_expired_token_rejected(db: Session):
    full, meta = _mint(db, ttl=30)
    db.execute(
        text("UPDATE agent_token SET expires_at = now() - interval '1 day' WHERE id=:i"),
        {"i": meta["id"]},
    )
    db.commit()
    assert tokens.resolve_token(db, full) is None


def test_list_tokens_never_leaks_hash(db: Session):
    _mint(db)
    db.commit()
    rows = tokens.list_tokens(db)
    assert rows and all("token_hash" not in r for r in rows)
    assert all("token_prefix" in r for r in rows)


def test_dummy_compare_runs_on_prefix_miss(db: Session, monkeypatch):
    """Timing seam: resolve_token must execute exactly one constant-time
    compare on BOTH the prefix-miss and the wrong-secret path, so unknown
    prefixes are not distinguishable from bad secrets by comparison count.
    (Deterministic structural check — wall-clock timing tests are flaky.)"""
    calls: list[int] = []
    real = tokens.hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(tokens.hmac, "compare_digest", spy)
    # unknown prefix (row miss) → exactly one dummy compare
    calls.clear()
    assert tokens.resolve_token(db, tokens.NAMESPACE + "f" * 40) is None
    assert len(calls) == 1
    # known prefix, wrong secret → exactly one real compare
    full, meta = _mint(db)
    db.commit()
    forged = tokens.NAMESPACE + meta["token_prefix"] + "0" * 32
    calls.clear()
    assert tokens.resolve_token(db, forged) is None
    assert len(calls) == 1


def test_duplicate_prefix_rejected_by_unique_constraint(db: Session):
    """Two tokens can never share a prefix — lookup can never be ambiguous,
    so a forged token can never authenticate against the wrong row."""
    import uuid
    full, meta = _mint(db)
    db.commit()
    with pytest.raises(Exception):
        db.execute(
            text(
                "INSERT INTO agent_token (id,agent_name,token_prefix,token_hash,"
                "scopes,expires_at,created_by) VALUES (:i,'dupe',:p,:h,'R',"
                "now()+interval '1 day','o')"
            ),
            {"i": str(uuid.uuid4()), "p": meta["token_prefix"], "h": "e" * 64},
        )
        db.commit()
    db.rollback()


def test_service_layer_rejects_bad_scopes_before_db(db: Session):
    for bad in ("T", "R,T", "", [], ["Z"]):
        with pytest.raises(ValueError):
            tokens.create_token(
                db, agent_name="x", scopes=bad, created_by="o",
                ttl_days=30, max_ttl_days=90,
            )


def test_ttl_capped_at_max(db: Session):
    with pytest.raises(ValueError):
        tokens.create_token(
            db, agent_name="x", scopes="R", created_by="o",
            ttl_days=91, max_ttl_days=90,
        )


def test_scopes_check_constraint_blocks_trade_scope(db: Session):
    # even a raw insert cannot store a 'T' scope — the DB CHECK rejects it
    import uuid
    with pytest.raises(Exception):
        db.execute(
            text(
                "INSERT INTO agent_token (id,agent_name,token_prefix,token_hash,"
                "scopes,expires_at,created_by) VALUES (:i,'x','pfx1234',"
                ":h,'T',now()+interval '1 day','o')"
            ),
            {"i": str(uuid.uuid4()), "h": "h" * 64},
        )
        db.commit()
    db.rollback()
