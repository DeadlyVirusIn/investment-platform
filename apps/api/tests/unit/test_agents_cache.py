"""Unit tests for agents.cache.

Pure-function coverage for `compute_payload_hash` and the
`validate_cacheable` invariants. The session-bound `lookup` and
`store` paths are exercised by `test_insights_cache_pg.py` against
a real testcontainer Postgres.
"""

from __future__ import annotations

import pytest

from apps.api.src.domain.agents import cache
from apps.api.src.domain.agents.registry import AgentKind, BANNER


# ---------------------------------------------------------------------
# compute_payload_hash — determinism + sensitivity
# ---------------------------------------------------------------------

def test_hash_deterministic_for_same_payload():
    p = {"score": 72, "grade": "B", "reasons": ["a", "b"]}
    h1 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, p,
        source_endpoint="/api/x",
    )
    h2 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, p,
        source_endpoint="/api/x",
    )
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_hash_invariant_to_key_order():
    a = {"score": 72, "grade": "B"}
    b = {"grade": "B", "score": 72}
    h1 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, a, source_endpoint="/api/x",
    )
    h2 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, b, source_endpoint="/api/x",
    )
    assert h1 == h2


def test_hash_changes_when_numeric_value_changes():
    base = {"score": 72, "grade": "B"}
    drift = {"score": 73, "grade": "B"}
    h1 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, base, source_endpoint="/api/x",
    )
    h2 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, drift, source_endpoint="/api/x",
    )
    assert h1 != h2


def test_hash_changes_when_kind_changes():
    p = {"score": 72}
    h1 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, p, source_endpoint="/api/x",
    )
    h2 = cache.compute_payload_hash(
        AgentKind.RISK_COMMENTARY, p, source_endpoint="/api/x",
    )
    assert h1 != h2


def test_hash_changes_when_source_endpoint_changes():
    p = {"score": 72}
    h1 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, p, source_endpoint="/api/v1",
    )
    h2 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, p, source_endpoint="/api/v2",
    )
    assert h1 != h2


def test_hash_changes_when_safety_version_changes():
    p = {"score": 72}
    h1 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, p,
        source_endpoint="/api/x", safety_version="v1",
    )
    h2 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, p,
        source_endpoint="/api/x", safety_version="v2",
    )
    assert h1 != h2


def test_redacted_uuid_payload_matches_clean_payload():
    """The narrator scrubs UUID values to '[redacted]'. Two payloads
    that differ only in UUIDs (after scrubbing) must produce the
    same hash — that's the whole point of the redacted-first flow."""
    scrubbed_a = {
        "trade_id": "[redacted]",
        "portfolio_id": "[redacted]",
        "score": 72,
    }
    scrubbed_b = dict(scrubbed_a)
    h1 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, scrubbed_a,
        source_endpoint="/api/x",
    )
    h2 = cache.compute_payload_hash(
        AgentKind.TRADE_QUALITY, scrubbed_b,
        source_endpoint="/api/x",
    )
    assert h1 == h2


# ---------------------------------------------------------------------
# validate_cacheable — banner / non-empty / no raw UUID
# ---------------------------------------------------------------------

def test_validate_passes_for_clean_payload():
    cache.validate_cacheable(
        payload_redacted={"score": 72, "grade": "B"},
        content_markdown=f"{BANNER}\nScore is 72.",
        banner=BANNER,
    )


def test_validate_rejects_banner_mismatch():
    with pytest.raises(cache.CacheValidationError):
        cache.validate_cacheable(
            payload_redacted={"score": 72},
            content_markdown=f"{BANNER}\nbody",
            banner="Wrong banner",
        )


def test_validate_rejects_empty_content():
    with pytest.raises(cache.CacheValidationError):
        cache.validate_cacheable(
            payload_redacted={"score": 72},
            content_markdown="",
            banner=BANNER,
        )


def test_validate_rejects_whitespace_only_content():
    with pytest.raises(cache.CacheValidationError):
        cache.validate_cacheable(
            payload_redacted={"score": 72},
            content_markdown="   \n   ",
            banner=BANNER,
        )


def test_validate_rejects_content_missing_banner():
    """Hard rule: cached body MUST contain the canonical banner.
    A body that omits it cannot be cached even if everything else
    is clean."""
    with pytest.raises(cache.CacheValidationError):
        cache.validate_cacheable(
            payload_redacted={"score": 72},
            content_markdown="No banner here.",
            banner=BANNER,
        )


def test_validate_rejects_raw_uuid_in_payload_top_level():
    payload = {
        "trade_id": "fdc48224-fb64-4883-973c-206a924bd7a5",
        "score": 72,
    }
    with pytest.raises(cache.CacheValidationError):
        cache.validate_cacheable(
            payload_redacted=payload,
            content_markdown=f"{BANNER}\nbody",
            banner=BANNER,
        )


def test_validate_rejects_raw_uuid_nested_in_payload():
    payload = {
        "rows": [
            {"id": "[redacted]"},
            {"reason": "fdc48224-fb64-4883-973c-206a924bd7a5"},
        ],
    }
    with pytest.raises(cache.CacheValidationError):
        cache.validate_cacheable(
            payload_redacted=payload,
            content_markdown=f"{BANNER}\nbody",
            banner=BANNER,
        )


def test_validate_accepts_redacted_uuid_marker():
    """`[redacted-uuid]` is the post-scrub marker — it must NOT
    trip the raw-UUID check."""
    payload = {
        "reason": "trade [redacted-uuid] fired at 15:00 UTC",
    }
    cache.validate_cacheable(
        payload_redacted=payload,
        content_markdown=f"{BANNER}\nbody",
        banner=BANNER,
    )


# ---------------------------------------------------------------------
# Session-None paths — cache silently disabled
# ---------------------------------------------------------------------

def test_lookup_with_none_session_returns_none():
    assert cache.lookup(
        None,
        kind=AgentKind.TRADE_QUALITY,
        payload_hash="x" * 64,
        model="claude-test",
    ) is None


def test_store_with_none_session_validates_then_returns_none():
    """Validation still runs (so a buggy caller surfaces the
    invariant immediately), but the absence of a session means no
    DB write attempt."""
    out = cache.store(
        None,
        kind=AgentKind.TRADE_QUALITY,
        payload_hash="x" * 64,
        payload_redacted={"score": 72},
        content_markdown=f"{BANNER}\nbody",
        model="claude-test",
        source_endpoint="/api/x",
        banner=BANNER,
    )
    assert out is None


def test_store_with_none_session_still_rejects_unsafe_input():
    """Even without a session, `store` must refuse to silently
    accept a banner-mismatched / UUID-leaking payload."""
    with pytest.raises(cache.CacheValidationError):
        cache.store(
            None,
            kind=AgentKind.TRADE_QUALITY,
            payload_hash="x" * 64,
            payload_redacted={"trade_id":
                              "fdc48224-fb64-4883-973c-206a924bd7a5"},
            content_markdown=f"{BANNER}\nbody",
            model="claude-test",
            source_endpoint="/api/x",
            banner=BANNER,
        )
