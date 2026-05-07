"""Integration: F4 agent_insight cache against a real Postgres.

Uses the integration harness's `pg_engine` fixture (testcontainer
spun up per-session). Overrides the `get_session` dependency to
yield sessions bound to that engine, monkey-patches the LLM SDK,
and asserts:

  * Disabled flag → 503 + `cache: "disabled"`, zero rows written.
  * First request → LLM called once, `cache: "miss"`, exactly one
    row inserted.
  * Identical second request → LLM NOT called, `cache: "hit"`,
    no additional row.
  * Different payload → LLM called again, second row inserted.
  * Unsafe LLM body → 502, zero rows written.
  * Cache row stores ONLY the redacted payload (no raw UUIDs).
  * Unique constraint refuses duplicate (kind, hash, model, version).
  * No writes leak to paper / options / decision / replay tables
    (sampled subset).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.db.models import AgentInsight
from apps.api.src.domain.agents import llm_client
from apps.api.src.domain.agents.registry import AgentKind, BANNER
from apps.api.src.main import app


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------
# Mock SDK
# ---------------------------------------------------------------------

@dataclass
class _Block:
    text: str


@dataclass
class _Resp:
    content: list


class _Messages:
    def __init__(self, body: str, counter: dict):
        self._body = body
        self._counter = counter

    def create(self, **kwargs):
        self._counter["calls"] = self._counter.get("calls", 0) + 1
        return _Resp(content=[_Block(text=self._body)])


class _Client:
    def __init__(self, body: str, counter: dict):
        self.messages = _Messages(body, counter)


class _SDK:
    def __init__(self, body: str):
        self._body = body
        self.counter: dict = {}

    def Anthropic(self, **kwargs):
        return _Client(self._body, self.counter)


# ---------------------------------------------------------------------
# Fixture: engine-bound TestClient with cache overrides
# ---------------------------------------------------------------------

@pytest.fixture
def pg_client(pg_engine, monkeypatch):
    """Wires the FastAPI app to the testcontainer engine."""
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )

    def _override():
        s = SessionCls()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app), SessionCls
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture(autouse=True)
def _truncate_cache(pg_engine):
    """Clear `agent_insight` between tests so unique constraints
    do not bleed across cases."""
    from sqlalchemy import text as _text
    with pg_engine.begin() as conn:
        conn.execute(_text(
            "TRUNCATE TABLE agent_insight RESTART IDENTITY CASCADE",
        ))
    yield


# ---------------------------------------------------------------------
# Common payload + body
# ---------------------------------------------------------------------

_PAYLOAD = {
    "score": 72,
    "grade": "B",
    "thesis": "winner_trim",
    "completeness": "full",
    "components": {
        "entry": 18, "return": 22,
        "hold": 12, "exit_or_status": 10,
        "completeness": 10,
    },
    "reasons": ["Entry: favorable.", "Return: 4 percent."],
}

_SAFE_BODY = (
    f"{BANNER}\n"
    "Score is 72. Solid B-grade trade — entry component "
    "contributed the most at 18 of 20."
)


def _enable_flag(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_MODEL", "claude-test")


def _disable_flag(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")


def _count_rows(SessionCls) -> int:
    with SessionCls() as s:
        return s.execute(
            select(AgentInsight),
        ).scalars().all().__len__()


# ---------------------------------------------------------------------
# Disabled path: 503, no read/write
# ---------------------------------------------------------------------

def test_disabled_returns_503_and_writes_no_rows(
    pg_client, monkeypatch,
):
    client, SessionCls = pg_client
    _disable_flag(monkeypatch)

    sdk = _SDK(_SAFE_BODY)
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: sdk)

    r = client.get("/api/insights/trade_quality")
    assert r.status_code == 503
    body = r.json()
    assert body["error"] == "agent insights disabled"
    assert body["cache"] == "disabled"
    assert sdk.counter.get("calls", 0) == 0  # SDK never touched
    assert _count_rows(SessionCls) == 0


# ---------------------------------------------------------------------
# Enabled path: miss writes one row, repeat is a hit
# ---------------------------------------------------------------------

def test_first_request_misses_then_writes_one_row(
    pg_client, monkeypatch,
):
    client, SessionCls = pg_client
    _enable_flag(monkeypatch)

    sdk = _SDK(_SAFE_BODY)
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: sdk)

    r = client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cache"] == "miss"
    assert body["llm_enabled"] is True
    assert sdk.counter["calls"] == 1
    assert _count_rows(SessionCls) == 1


def test_second_identical_request_hits_cache(pg_client, monkeypatch):
    client, SessionCls = pg_client
    _enable_flag(monkeypatch)

    sdk = _SDK(_SAFE_BODY)
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: sdk)

    r1 = client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    assert r1.status_code == 200
    assert r1.json()["cache"] == "miss"

    r2 = client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["cache"] == "hit"
    # SDK called exactly once across both requests.
    assert sdk.counter["calls"] == 1
    # Still exactly one row.
    assert _count_rows(SessionCls) == 1
    # Hit response carries the same content as the miss.
    assert body2["content_markdown"] == r1.json()["content_markdown"]


def test_different_payload_calls_llm_again_and_writes_new_row(
    pg_client, monkeypatch,
):
    client, SessionCls = pg_client
    _enable_flag(monkeypatch)

    sdk = _SDK(_SAFE_BODY)
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: sdk)

    other = dict(_PAYLOAD)
    other["score"] = 99
    other["reasons"] = ["Entry: clean.", "Return: 5 percent."]

    r1 = client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    assert r1.json()["cache"] == "miss"

    # Swap body so the new response carries numbers traceable to the
    # new payload (otherwise the post-call hallucination gate fires).
    sdk._body = (
        f"{BANNER}\n"
        "Score is 99. A-grade trade — return component scored 30."
    )
    other["components"] = {
        "entry": 20, "return": 30,
        "hold": 15, "exit_or_status": 25,
        "completeness": 10,
    }
    other["grade"] = "A"

    r2 = client.request(
        "GET", "/api/insights/trade_quality", json=other,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["cache"] == "miss"
    assert sdk.counter["calls"] == 2
    assert _count_rows(SessionCls) == 2


# ---------------------------------------------------------------------
# Unsafe response: 502, no row written
# ---------------------------------------------------------------------

def test_unsafe_response_returns_502_and_caches_nothing(
    pg_client, monkeypatch,
):
    client, SessionCls = pg_client
    _enable_flag(monkeypatch)

    bad = _SDK(f"{BANNER}\nOperator should buy now.")
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: bad)

    r = client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    assert r.status_code == 502
    assert r.json()["error"] == "insight rejected by safety layer"
    assert _count_rows(SessionCls) == 0


# ---------------------------------------------------------------------
# Cache row content invariants
# ---------------------------------------------------------------------

def test_cache_row_contains_only_redacted_payload(
    pg_client, monkeypatch,
):
    """A payload carrying a UUID must round-trip into the cache row
    with the UUID replaced. The row's `payload_redacted` JSON should
    NEVER contain the raw UUID."""
    client, SessionCls = pg_client
    _enable_flag(monkeypatch)

    sdk = _SDK(_SAFE_BODY)
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: sdk)

    raw_uuid = "fdc48224-fb64-4883-973c-206a924bd7a5"
    payload_with_uuid = {**_PAYLOAD, "trade_id": raw_uuid}

    r = client.request(
        "GET", "/api/insights/trade_quality", json=payload_with_uuid,
    )
    assert r.status_code == 200, r.text

    with SessionCls() as s:
        row = s.execute(select(AgentInsight)).scalar_one()
        # `trade_id` MUST be redacted.
        assert row.payload_redacted["trade_id"] == "[redacted]"
        # The raw UUID MUST NOT appear anywhere in the redacted blob.
        import json as _json
        blob = _json.dumps(row.payload_redacted)
        assert raw_uuid not in blob
        # Banner stored verbatim.
        assert row.banner == BANNER
        # Content body still carries the banner.
        assert BANNER in row.content_markdown


# ---------------------------------------------------------------------
# Unique constraint
# ---------------------------------------------------------------------

def test_unique_constraint_rejects_duplicate_natural_key(pg_engine):
    """Direct DB-level proof: two rows with the same (kind,
    payload_hash, model, safety_version) are forbidden."""
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    with SessionCls() as s:
        a = AgentInsight(
            kind="trade_quality",
            payload_hash="h" * 64,
            payload_redacted={"score": 72},
            content_markdown=f"{BANNER}\nbody",
            model="claude-test",
            source_endpoint="/api/x",
            banner=BANNER,
            safety_version="v1",
        )
        s.add(a)
        s.commit()

    with SessionCls() as s:
        b = AgentInsight(
            kind="trade_quality",
            payload_hash="h" * 64,
            payload_redacted={"score": 72},
            content_markdown=f"{BANNER}\nother body",
            model="claude-test",
            source_endpoint="/api/x",
            banner=BANNER,
            safety_version="v1",
        )
        s.add(b)
        with pytest.raises(IntegrityError):
            s.commit()


# ---------------------------------------------------------------------
# No execution-table writes
# ---------------------------------------------------------------------

_EXECUTION_TABLES_TO_CHECK = (
    "paper_trade",
    "paper_position",
    "paper_equity_snapshot",
    "decision_log",
    "recommendation",
)


def test_no_writes_to_execution_tables(pg_client, pg_engine, monkeypatch):
    """Capture row counts for a sample of execution tables before
    and after a successful insight call. Counts MUST match — the
    F4 endpoint is allowed to write `agent_insight` and nothing
    else."""
    client, _ = pg_client
    _enable_flag(monkeypatch)
    sdk = _SDK(_SAFE_BODY)
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: sdk)

    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text as _text

    insp = sa_inspect(pg_engine)
    existing_tables = set(insp.get_table_names())
    tables_to_check = [
        t for t in _EXECUTION_TABLES_TO_CHECK if t in existing_tables
    ]
    # Sanity: at least one execution table should exist in the
    # testcontainer schema, else the assertion is meaningless.
    assert tables_to_check, (
        "no execution tables present in testcontainer — invariant "
        "check is a no-op; integration harness needs review"
    )

    def _counts() -> dict[str, int]:
        out: dict[str, int] = {}
        with pg_engine.begin() as conn:
            for tbl in tables_to_check:
                row = conn.execute(_text(
                    f'SELECT count(*) FROM "{tbl}"',
                )).scalar()
                out[tbl] = int(row or 0)
        return out

    before = _counts()
    r = client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    assert r.status_code == 200
    after = _counts()
    assert before == after, (
        f"execution-table counts changed: before={before} after={after}"
    )
