"""Integration tests for /api/agent-workflows.

Spins up the testcontainer Postgres, seeds minimal fixture data,
and dispatches each of the four agents end-to-end. Asserts:

  * `/api/agent-workflows` returns the four registered agents
    with their declared inputs.
  * Each agent's `/run` endpoint returns a valid envelope
    (banner verbatim, execution_linked=False).
  * Empty-DB invocations return zero-state outputs without
    raising.
  * SignalValidationAgent flags rule violations on a seeded
    pathological row.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import get_session
from apps.api.src.db.models import Asset, Signal
from apps.api.src.domain.agent_workflows.base import AGENT_BANNER
from apps.api.src.main import app


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _truncate_signal_table(pg_engine):
    """Ensure each test starts with empty signal/asset state so
    parametrized cases don't bleed across each other via the
    session-scoped engine."""
    from sqlalchemy import text as _text
    with pg_engine.begin() as conn:
        conn.execute(_text(
            "TRUNCATE TABLE signal, asset RESTART IDENTITY CASCADE",
        ))
    yield


@pytest.fixture
def client(pg_engine):
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )

    def _override():
        s = SessionCls()
        try:
            yield s
        finally:
            s.close()

    # Bootstrap replay_recovery_manifest (mirrors risk-dashboard
    # integration test pattern).
    from sqlalchemy import text as _text
    with pg_engine.begin() as conn:
        conn.execute(_text(
            "CREATE TABLE IF NOT EXISTS replay_recovery_manifest ("
            "  id SERIAL PRIMARY KEY,"
            "  replay_run_id TEXT, source TEXT,"
            "  entity_type TEXT, entity_id TEXT"
            ")"
        ))

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app), SessionCls
    finally:
        app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------
# Listing endpoint
# ---------------------------------------------------------------------

def test_list_agents_returns_all_four(client):
    test_client, _ = client
    r = test_client.get("/api/agent-workflows/")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["banner"] == AGENT_BANNER
    names = {a["name"] for a in body["agents"]}
    assert names == {
        "trade_quality", "risk", "exit_analysis", "signal_validation",
    }
    # Every agent declares at least one input.
    for a in body["agents"]:
        assert a["mode"] == "deterministic"
        assert a["inputs"]


def test_unknown_agent_returns_404(client):
    test_client, _ = client
    r = test_client.get("/api/agent-workflows/no_such/run")
    assert r.status_code == 404


# ---------------------------------------------------------------------
# Empty-DB runs (each agent must handle zero state)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "trade_quality", "risk", "exit_analysis", "signal_validation",
])
def test_each_agent_runs_on_empty_db(client, name):
    test_client, _ = client
    r = test_client.get(f"/api/agent-workflows/{name}/run")
    assert r.status_code == 200, r.text
    env = r.json()
    assert env["agent"] == name
    assert env["banner"] == AGENT_BANNER
    assert env["execution_linked"] is False
    assert env["mode"] == "deterministic"
    assert "output" in env


# ---------------------------------------------------------------------
# Signal Validation agent — seeded data
# ---------------------------------------------------------------------

def _seed_one_signal(SessionCls, **overrides):
    base = dict(
        signal_id="sig-clean-1",
        as_of_date=dt.date(2026, 5, 1),
        symbol="NVDA",
        timeframe="1d",
        strategy_id="strategy-A",
        model_family="lgbm",
        model_version="v1",
        features_version="f1",
        signal_direction="long",
        signal_strength=Decimal("0.7"),
        confidence=Decimal("0.8"),
        holding_period_bars=5,
        regime_tag="bull",
        generated_at=dt.datetime(2026, 5, 1, 12,
                                 tzinfo=dt.timezone.utc),
    )
    base.update(overrides)
    with SessionCls() as s:
        a = Asset(symbol=base["symbol"], asset_class="equity",
                  currency="USD")
        s.add(a)
        s.flush()
        base["asset_id"] = a.id
        s.add(Signal(**base))
        s.commit()


def test_signal_validation_clean_signal_aligns(client):
    test_client, SessionCls = client
    _seed_one_signal(SessionCls)
    r = test_client.get(
        "/api/agent-workflows/signal_validation/run",
    )
    assert r.status_code == 200, r.text
    out = r.json()["output"]
    assert out["n_signals"] == 1
    assert out["aligned_count"] == 1
    assert out["alignment_rate"] == 1.0
    assert out["per_signal"][0]["aligned"] is True
    assert out["per_signal"][0]["warnings"] == []


def test_signal_validation_pathological_signal_flags(client):
    test_client, SessionCls = client
    # All five rules violated in one row.
    _seed_one_signal(
        SessionCls,
        signal_id="sig-bad-1", symbol="BADSYM",
        confidence=Decimal("0.10"),
        signal_direction="long",
        signal_strength=Decimal("-0.5"),
        holding_period_bars=0,
        regime_tag=None,
        generated_at=dt.datetime(2026, 1, 1, 12,
                                 tzinfo=dt.timezone.utc),
    )
    r = test_client.get(
        "/api/agent-workflows/signal_validation/run",
    )
    assert r.status_code == 200
    out = r.json()["output"]
    assert out["n_signals"] == 1
    assert out["aligned_count"] == 0
    assert out["alignment_rate"] == 0.0
    rule_counts = out["rule_counts"]
    # Each rule fired at least once.
    assert rule_counts.get("low_confidence", 0) >= 1
    assert (
        rule_counts.get("strength_direction_mismatch", 0) >= 1
    )
    assert rule_counts.get("holding_period_nonpositive", 0) >= 1
    assert rule_counts.get("regime_tag_missing", 0) >= 1
    assert rule_counts.get("stale", 0) >= 1


# ---------------------------------------------------------------------
# Read-only invariant — no rows added to execution tables
# ---------------------------------------------------------------------

def test_running_all_agents_writes_no_execution_rows(
    client, pg_engine,
):
    test_client, _ = client
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text as _text

    insp = sa_inspect(pg_engine)
    existing = set(insp.get_table_names())
    sample = [t for t in (
        "paper_trade", "paper_position", "paper_equity_snapshot",
        "decision_log", "recommendation",
    ) if t in existing]
    assert sample, "no execution tables in testcontainer"

    def _counts() -> dict[str, int]:
        with pg_engine.begin() as conn:
            return {
                t: int(conn.execute(_text(
                    f'SELECT count(*) FROM "{t}"',
                )).scalar() or 0)
                for t in sample
            }

    before = _counts()
    for name in (
        "trade_quality", "risk", "exit_analysis", "signal_validation",
    ):
        r = test_client.get(f"/api/agent-workflows/{name}/run")
        assert r.status_code == 200, (name, r.text)
    after = _counts()
    assert before == after, (
        f"agents wrote to execution tables: before={before} "
        f"after={after}"
    )
