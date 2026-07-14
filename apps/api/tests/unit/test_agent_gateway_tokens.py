"""Agent Gateway v0 — pure token-core unit tests (no DB).

Locks the security-critical logic that needs no database: token generation +
hash-at-rest, scope grammar (no 'T' can ever be minted), bearer parsing
(cookie sessions rejected), and the fail-closed config default. The DB-backed
paths (resolve/create/revoke, authz matrix, migration up/down) live in
apps/api/tests/integration/test_agent_gateway_pg.py.
"""

import hashlib

import pytest

from apps.api.src.config import settings
from apps.api.src.domain.agent_gateway import audit, tokens


# --- generation + hash-at-rest --------------------------------------------
def test_generate_token_shape_and_prefix():
    full, prefix, thash = tokens.generate_token()
    assert full.startswith("arthos_at_")
    body = full[len("arthos_at_"):]
    assert len(body) == tokens.BODY_LEN
    assert prefix == body[: tokens.PREFIX_LEN]
    assert len(prefix) == 8
    assert len(thash) == 64  # sha256 hex


def test_hash_is_sha256_of_full_and_not_the_secret():
    full, _prefix, thash = tokens.generate_token()
    assert thash == hashlib.sha256(full.encode()).hexdigest()
    # the stored hash must never equal or contain the token secret
    assert thash != full
    assert full[len("arthos_at_"):] not in thash


def test_generate_token_is_unique():
    seen = {tokens.generate_token()[0] for _ in range(50)}
    assert len(seen) == 50


def test_hash_token_deterministic():
    assert tokens.hash_token("arthos_at_abc") == tokens.hash_token("arthos_at_abc")


# --- scope grammar: exactly R,P,B,D, canonical, no T ----------------------
def test_normalize_scopes_canonical_order_and_dedupe():
    assert tokens.normalize_scopes(["D", "R", "R", "B"]) == "R,B,D"
    assert tokens.normalize_scopes("p, r") == "R,P"


def test_normalize_scopes_rejects_trade_and_unknown():
    with pytest.raises(ValueError):
        tokens.normalize_scopes(["R", "T"])          # no live-trading scope
    with pytest.raises(ValueError):
        tokens.normalize_scopes("X")
    with pytest.raises(ValueError):
        tokens.normalize_scopes([])                   # empty rejected
    with pytest.raises(ValueError):
        tokens.normalize_scopes("")


def test_has_scope():
    assert tokens.has_scope({"R", "P"}, "R") is True
    assert tokens.has_scope({"R", "P"}, "B") is False
    assert tokens.has_scope("R,D", "D") is True


# --- bearer parsing: Bearer only, arthos namespace only -------------------
def test_parse_bearer_accepts_valid():
    full, _p, _h = tokens.generate_token()
    assert tokens.parse_bearer(f"Bearer {full}") == full
    assert tokens.parse_bearer(f"bearer {full}") == full  # case-insensitive scheme


def test_parse_bearer_rejects_bad_inputs():
    full, _p, _h = tokens.generate_token()
    assert tokens.parse_bearer(None) is None
    assert tokens.parse_bearer("") is None
    assert tokens.parse_bearer(full) is None                       # no scheme
    assert tokens.parse_bearer(f"Basic {full}") is None            # wrong scheme
    assert tokens.parse_bearer("Bearer arthos_session_xyz") is None  # wrong namespace
    assert tokens.parse_bearer("Bearer arthos_at_short") is None   # wrong length


def test_prefix_of():
    full, prefix, _h = tokens.generate_token()
    assert tokens.prefix_of(full) == prefix
    assert tokens.prefix_of("nope") is None
    assert tokens.prefix_of("arthos_at_short") is None


# --- audit request-hash: replay-detectable, payload-free ------------------
def test_canonical_request_hash_stable_and_query_order_invariant():
    a = audit.canonical_request_hash("GET", "/agent/x", "b=2&a=1", None)
    b = audit.canonical_request_hash("get", "/agent/x", "a=1&b=2", None)
    assert a == b == audit.canonical_request_hash("GET", "/agent/x", "a=1&b=2", None)
    # body changes the hash, but the body itself is never stored
    assert a != audit.canonical_request_hash("GET", "/agent/x", "a=1&b=2", b"payload")


# --- fail-closed default ---------------------------------------------------
def test_gateway_disabled_by_default():
    assert settings.AGENT_GATEWAY_ENABLED is False
    assert settings.AGENT_TOKEN_MAX_TTL_DAYS == 90
