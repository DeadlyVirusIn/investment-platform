"""Phase 11W (Phase F.1) — server-side tier stripping integration."""

from __future__ import annotations

import datetime as dt
import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def f1_schema(pg_engine):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    with pg_engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS context_daily (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                as_of_date date NOT NULL,
                context_name text NOT NULL,
                status text NOT NULL,
                value_bool boolean,
                source_features text[] NOT NULL,
                logic_version text NOT NULL,
                logic_hash text NOT NULL,
                computed_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT ux_context_daily_name_ver_date
                  UNIQUE (as_of_date, context_name, logic_version)
            )
            """
        ))
    for revision in (
        "052_research_ro_init",
        "053_research_ro_provider_idempotency",
        "057_research_manual_run_audit",
        "058_research_alerts_operator_control",
        "059_research_operator_cooldown_history",
    ):
        mod = importlib.import_module(f"infra.alembic.versions.{revision}")
        with pg_engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                try:
                    mod.upgrade()
                except Exception as exc:  # noqa: BLE001
                    if "already exists" not in str(exc).lower():
                        raise
    yield pg_engine


@pytest.fixture
def session(f1_schema, pg_session):
    pg_session.execute(text(
        "TRUNCATE research_ro.research_alert, "
        "         research_ro.research_operator_control, "
        "         research_ro.research_manual_run_audit, "
        "         research_ro.research_run CASCADE"
    ))
    pg_session.commit()
    yield pg_session


@pytest.fixture
def client(monkeypatch, pg_engine):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "RESEARCH_RO_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_MANUAL_RUN_ENABLED", False)
    monkeypatch.setattr(settings, "RESEARCH_ADMIN_TOKEN", "")
    monkeypatch.setattr(settings, "RESEARCH_PREMIUM_TIER", "enterprise")
    # Phase G — pre-G tests rely on env-tier + X-Research-Tier.
    # Local-dev mode keeps that contract working.
    monkeypatch.setattr(settings, "AUTH_DISABLED_LOCAL", True)
    from sqlalchemy.orm import Session, sessionmaker
    test_session = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    import apps.api.src.db as db_mod
    monkeypatch.setattr(db_mod, "SessionLocal", test_session)
    import apps.api.src.api.research as research_mod
    monkeypatch.setattr(research_mod, "SessionLocal", test_session)
    import apps.api.src.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def _seed_run_and_output(s, *, body="Narrative analysis only.") -> str:
    rid = s.execute(text(
        """
        INSERT INTO research_ro.research_run
          (symbol, as_of, schema_version, prompt_bundle_hash,
           input_snapshot_hash, provider, model_id, model_version,
           prompt_template_id, prompt_template_version, prompt_hash,
           temperature, seed, tokens_in, tokens_out, cost_usd,
           status, triggered_by, operator_id, started_at, finished_at)
        VALUES ('UNH', '2026-04-29', 'v1', 'h', 'h',
                'mock', 'm1', 'v1', 'tpl', 1, 'h',
                0.0, 1, 100, 200, 0.001,
                'succeeded', 'manual', 'op-f1', now(), now())
        RETURNING id::text
        """
    )).scalar()
    s.execute(text(
        """
        INSERT INTO research_ro.research_agent_output
          (run_id, agent_role, sequence_no, body, body_hash,
           provider, model_id, model_version, prompt_hash,
           tokens_in, tokens_out, cost_usd, status)
        VALUES (CAST(:rid AS uuid), 'bull_researcher', 0,
                :body, 'h', 'mock', 'm1', 'v1', 'h',
                10, 20, 0.0001, 'succeeded')
        """
    ), {"rid": rid, "body": body})
    s.commit()
    return rid


# ===========================================================================
# Free tier
# ===========================================================================


def test_free_tier_hides_body(session, client):
    rid = _seed_run_and_output(session)
    r = client.get(
        f"/api/research/runs/{rid}",
        headers={"X-Research-Tier": "free"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["tier"] == "free"
    # Free → outputs stripped to empty list.
    assert j["outputs"] == []
    # Free run shape: no body, no cost, no operator_id, no prompt_hash.
    run = j["run"]
    assert "body" not in run
    assert "cost_usd" not in run
    assert "prompt_hash" not in run
    assert "operator_id" not in run
    # has_full_note + safety_status are present.
    assert run["has_full_note"] is True
    assert run["safety_status"] == "safe"


def test_free_tier_hides_evidence_refs(session, client):
    _seed_run_and_output(session)
    r = client.get(
        "/api/research/runs",
        headers={"X-Research-Tier": "free"},
    )
    j = r.json()
    assert j["tier"] == "free"
    for run in j["runs"]:
        assert "evidence_refs" not in run
        assert "structured_output" not in run


# ===========================================================================
# Pro tier
# ===========================================================================


def test_pro_tier_shows_safe_body_only(session, client):
    rid = _seed_run_and_output(
        session, body="Context summary, no actions.",
    )
    r = client.get(
        f"/api/research/runs/{rid}",
        headers={"X-Research-Tier": "pro"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["tier"] == "pro"
    assert len(j["outputs"]) == 1
    out = j["outputs"][0]
    assert out["body"] is not None
    assert out["safety_status"] == "safe"
    # Pro hides cost.
    assert "cost_usd" not in out
    assert "cost_usd" not in j["run"]


def test_pro_tier_hides_audit_and_operator_controls(session, client):
    r = client.get(
        "/api/research/audit",
        headers={"X-Research-Tier": "pro"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["audit_table"] == "tier_below_enterprise"
    assert j["rows"] == []

    r = client.get(
        "/api/research/operators",
        headers={"X-Research-Tier": "pro"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["operators"] == []


def test_pro_tier_operator_detail_404(session, client):
    """Pro tier never sees operator detail; 404 by design."""
    session.execute(text(
        """
        INSERT INTO research_ro.research_operator_control
          (operator_id, state, updated_by)
        VALUES ('alice', 'clear', 'test')
        """
    ))
    session.commit()
    r = client.get(
        "/api/research/operators/alice",
        headers={"X-Research-Tier": "pro"},
    )
    assert r.status_code == 404


# ===========================================================================
# Enterprise tier
# ===========================================================================


def test_enterprise_tier_shows_audit_read_only(session, client):
    session.execute(text(
        """
        INSERT INTO research_ro.research_manual_run_audit
          (operator_id, symbol, as_of, provider, request_source, status)
        VALUES ('alice', 'UNH', '2026-04-29', 'mock', 'cli', 'accepted')
        """
    ))
    session.commit()
    r = client.get(
        "/api/research/audit",
        headers={"X-Research-Tier": "enterprise"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["audit_table"] == "present"
    assert len(j["rows"]) >= 1
    for row in j["rows"]:
        for forbidden in ("body", "raw_body", "prompt"):
            assert forbidden not in row


def test_enterprise_tier_sees_usage_summary(session, client):
    r = client.get(
        "/api/research/usage/summary",
        headers={"X-Research-Tier": "enterprise"},
    )
    assert r.status_code == 200
    j = r.json()
    assert "audit_today" in j and "alerts" in j and "operators" in j
    assert "tier_visibility" not in j  # only added for sub-enterprise


def test_lower_tier_usage_summary_is_empty(session, client):
    r = client.get(
        "/api/research/usage/summary",
        headers={"X-Research-Tier": "free"},
    )
    j = r.json()
    assert j["tier_visibility"] == "tier_below_enterprise"
    assert j["audit_today"]["accepted"] == 0


# ===========================================================================
# Universal: unsafe note hidden, no raw output, no POST
# ===========================================================================


def test_unsafe_note_hidden_all_tiers(session, client):
    """When safety_status is unsafe, body is null regardless of tier."""
    rid = _seed_run_and_output(session)
    # Force one output's safety_status by overwriting.
    session.execute(text(
        """
        UPDATE research_ro.research_agent_output
        SET status = 'token_violation'
        WHERE run_id = CAST(:rid AS uuid)
        """
    ), {"rid": rid})
    session.commit()
    for tier in ("free", "pro", "enterprise"):
        r = client.get(
            f"/api/research/runs/{rid}",
            headers={"X-Research-Tier": tier},
        )
        j = r.json()
        if tier == "free":
            assert j["outputs"] == []
        else:
            for o in j["outputs"]:
                if o.get("safety_status") != "safe":
                    assert o["body"] is None


def test_no_raw_output_in_any_tier(session, client):
    rid = _seed_run_and_output(session)
    for tier in ("free", "pro", "enterprise"):
        r = client.get(
            f"/api/research/runs/{rid}",
            headers={"X-Research-Tier": tier},
        )
        j = r.json()
        for run_or_out in [j["run"]] + list(j.get("outputs") or []):
            for forbidden in (
                "raw_body", "raw_response", "structured_output",
                "agent_output", "evidence_refs", "prompt",
                "prompt_text", "prompt_template",
            ):
                assert forbidden not in run_or_out, (
                    f"{tier} payload exposed {forbidden}"
                )


def test_server_side_tier_stripping_not_frontend_only(
    session, client, monkeypatch,
):
    """Even when the X-Research-Tier header asks for enterprise,
    the server-side cap (RESEARCH_PREMIUM_TIER) governs."""
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "RESEARCH_PREMIUM_TIER", "free")
    rid = _seed_run_and_output(session)
    r = client.get(
        f"/api/research/runs/{rid}",
        headers={"X-Research-Tier": "enterprise"},
    )
    j = r.json()
    # Server caps at free — outputs stripped to empty.
    assert j["tier"] == "free"
    assert j["outputs"] == []


def test_no_post_routes_phase_f1(client):
    """Confirm Phase F.1 added zero new POST routes."""
    paths = [
        "/api/research/runs",
        "/api/research/runs/00000000-0000-0000-0000-000000000000",
        "/api/research/ticker/UNH/latest",
        "/api/research/decision/dec-1",
        "/api/research/usage",
        "/api/research/usage/summary",
        "/api/research/alerts",
        "/api/research/operators",
        "/api/research/operators/alice",
        "/api/research/audit",
    ]
    for p in paths:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            r = client.request(method, p, headers={"X-Research-Tier": "enterprise"})
            assert r.status_code in (404, 405), f"{method} {p} → {r.status_code}"
