"""Phase G — auth + subscription + tier resolution integration."""

from __future__ import annotations

import datetime as dt
import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def g_schema(pg_engine):
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
        "060_auth_subscription_org",
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
def session(g_schema, pg_session):
    pg_session.execute(text(
        "TRUNCATE public.subscription, "
        "         public.organization_member, "
        "         public.organization, "
        "         public.app_user CASCADE"
    ))
    pg_session.execute(text("TRUNCATE research_ro.research_run CASCADE"))
    pg_session.commit()
    yield pg_session


@pytest.fixture
def client(monkeypatch, pg_engine):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "RESEARCH_RO_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_MANUAL_RUN_ENABLED", False)
    monkeypatch.setattr(settings, "RESEARCH_ADMIN_TOKEN", "")
    monkeypatch.setattr(settings, "AUTH_DISABLED_LOCAL", False)
    monkeypatch.setattr(settings, "RESEARCH_PREMIUM_TIER", "free")
    monkeypatch.setattr(settings, "RESEARCH_GRACE_ENABLED", False)
    from sqlalchemy.orm import Session, sessionmaker
    test_session = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    import apps.api.src.db as db_mod
    monkeypatch.setattr(db_mod, "SessionLocal", test_session)
    import apps.api.src.api.research as research_mod
    monkeypatch.setattr(research_mod, "SessionLocal", test_session)
    import apps.api.src.api.auth_me as auth_me_mod
    # auth_me uses SessionLocal too via /orgs handler.
    monkeypatch.setattr(auth_me_mod, "SessionLocal", test_session)
    import apps.api.src.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


# Helpers ---------------------------------------------------------------


def _seed_user(s, *, uid: str, email: str = None,
               disabled: bool = False) -> None:
    s.execute(text(
        """
        INSERT INTO public.app_user (id, email, display_name, disabled_at)
        VALUES (:id, :em, :dn,
                CASE WHEN :dis THEN now() ELSE NULL END)
        ON CONFLICT (id) DO UPDATE
          SET disabled_at = EXCLUDED.disabled_at
        """
    ), {
        "id": uid, "em": email or f"{uid}@local",
        "dn": uid, "dis": disabled,
    })
    s.commit()


def _seed_subscription(
    s, *, subject_type: str, subject_id: str,
    tier: str, status: str = "active",
    period_end: dt.datetime | None = None,
    provider: str = "internal",
) -> None:
    s.execute(text(
        """
        INSERT INTO public.subscription
          (subject_type, subject_id, tier, status, provider,
           current_period_end)
        VALUES (:st, :sid, :tier, :stat, :prov, :pe)
        """
    ), {
        "st": subject_type, "sid": subject_id, "tier": tier,
        "stat": status, "prov": provider, "pe": period_end,
    })
    s.commit()


def _seed_org_with_member(
    s, *, org_id: str, owner_id: str, member_id: str,
    member_status: str = "active",
) -> None:
    s.execute(text(
        """
        INSERT INTO public.organization (id, name, owner_user_id)
        VALUES (:oid, :name, :owner)
        ON CONFLICT (id) DO NOTHING
        """
    ), {"oid": org_id, "name": f"org-{org_id}", "owner": owner_id})
    s.execute(text(
        """
        INSERT INTO public.organization_member
          (org_id, user_id, role, status)
        VALUES (:oid, :uid, 'member', :st)
        ON CONFLICT (org_id, user_id) DO UPDATE
          SET status = EXCLUDED.status
        """
    ), {"oid": org_id, "uid": member_id, "st": member_status})
    s.commit()


# ===========================================================================
# Tests
# ===========================================================================


def test_anonymous_user_gets_free(client):
    """No X-Auth-User-Id header → effective_tier='free' (read-only)."""
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    j = r.json()
    assert j["user"] is None
    assert j["effective_tier"] == "free"
    # Research API also serves Free shape.
    r2 = client.get("/api/research/runs")
    assert r2.status_code == 200
    assert r2.json()["tier"] == "free"


def test_disabled_user_no_access(session, client):
    _seed_user(session, uid="alice", disabled=True)
    r = client.get(
        "/api/auth/me",
        headers={"X-Auth-User-Id": "alice"},
    )
    assert r.status_code == 403


def test_user_pro_subscription_gets_pro(session, client):
    _seed_user(session, uid="alice")
    _seed_subscription(
        session, subject_type="user", subject_id="alice",
        tier="pro", status="active",
    )
    r = client.get(
        "/api/auth/me",
        headers={"X-Auth-User-Id": "alice"},
    )
    j = r.json()
    assert j["effective_tier"] == "pro"
    # Research detail endpoint reflects pro tier.
    rid = session.execute(text(
        """
        INSERT INTO research_ro.research_run
          (symbol, as_of, schema_version, prompt_bundle_hash,
           input_snapshot_hash, provider, model_id, model_version,
           prompt_template_id, prompt_template_version, prompt_hash,
           temperature, seed, tokens_in, tokens_out, cost_usd,
           status, triggered_by, operator_id, started_at)
        VALUES ('UNH','2026-04-29','v1','h','h','mock','m1','v1',
                't',1,'h',0.0,1,1,1,0.001,'succeeded','manual','op',
                now())
        RETURNING id::text
        """
    )).scalar()
    session.commit()
    r2 = client.get(
        f"/api/research/runs/{rid}",
        headers={"X-Auth-User-Id": "alice"},
    )
    assert r2.status_code == 200
    assert r2.json()["tier"] == "pro"


def test_org_enterprise_overrides_user_free(session, client):
    _seed_user(session, uid="alice")
    _seed_user(session, uid="owner")
    _seed_org_with_member(
        session, org_id="acme", owner_id="owner", member_id="alice",
    )
    _seed_subscription(
        session, subject_type="org", subject_id="acme",
        tier="enterprise", status="active",
    )
    r = client.get(
        "/api/auth/me",
        headers={"X-Auth-User-Id": "alice"},
    )
    assert r.json()["effective_tier"] == "enterprise"


def test_removed_org_member_loses_enterprise(session, client):
    _seed_user(session, uid="alice")
    _seed_user(session, uid="owner")
    _seed_org_with_member(
        session, org_id="acme", owner_id="owner",
        member_id="alice", member_status="removed",
    )
    _seed_subscription(
        session, subject_type="org", subject_id="acme",
        tier="enterprise", status="active",
    )
    r = client.get(
        "/api/auth/me",
        headers={"X-Auth-User-Id": "alice"},
    )
    assert r.json()["effective_tier"] == "free"


def test_canceled_subscription_downgrades_to_free(session, client):
    _seed_user(session, uid="alice")
    _seed_subscription(
        session, subject_type="user", subject_id="alice",
        tier="pro", status="canceled",
        period_end=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2),
    )
    r = client.get(
        "/api/auth/me",
        headers={"X-Auth-User-Id": "alice"},
    )
    assert r.json()["effective_tier"] == "free"


def test_grace_mode_keeps_tier_briefly(session, client, monkeypatch):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "RESEARCH_GRACE_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_GRACE_HOURS", 24)
    _seed_user(session, uid="alice")
    _seed_subscription(
        session, subject_type="user", subject_id="alice",
        tier="pro", status="canceled",
        period_end=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2),
    )
    r = client.get(
        "/api/auth/me",
        headers={"X-Auth-User-Id": "alice"},
    )
    assert r.json()["effective_tier"] == "pro"


def test_client_header_cannot_escalate_tier(session, client):
    """Production path: AUTH_DISABLED_LOCAL=false, alice is on Free.
    Sending X-Research-Tier: enterprise must NOT elevate."""
    _seed_user(session, uid="alice")
    rid = session.execute(text(
        """
        INSERT INTO research_ro.research_run
          (symbol, as_of, schema_version, prompt_bundle_hash,
           input_snapshot_hash, provider, model_id, model_version,
           prompt_template_id, prompt_template_version, prompt_hash,
           temperature, seed, tokens_in, tokens_out, cost_usd,
           status, triggered_by, operator_id, started_at)
        VALUES ('UNH','2026-04-29','v1','h','h','mock','m1','v1',
                't',1,'h',0.0,1,1,1,0.001,'succeeded','manual','op',
                now())
        RETURNING id::text
        """
    )).scalar()
    session.commit()
    r = client.get(
        f"/api/research/runs/{rid}",
        headers={
            "X-Auth-User-Id": "alice",
            "X-Research-Tier": "enterprise",
        },
    )
    assert r.status_code == 200
    assert r.json()["tier"] == "free"
    assert r.json()["outputs"] == []


def test_free_tier_still_hides_body(session, client):
    _seed_user(session, uid="alice")
    rid = session.execute(text(
        """
        INSERT INTO research_ro.research_run
          (symbol, as_of, schema_version, prompt_bundle_hash,
           input_snapshot_hash, provider, model_id, model_version,
           prompt_template_id, prompt_template_version, prompt_hash,
           temperature, seed, tokens_in, tokens_out, cost_usd,
           status, triggered_by, operator_id, started_at)
        VALUES ('UNH','2026-04-29','v1','h','h','mock','m1','v1',
                't',1,'h',0.0,1,1,1,0.001,'succeeded','manual','op',
                now())
        RETURNING id::text
        """
    )).scalar()
    session.execute(text(
        """
        INSERT INTO research_ro.research_agent_output
          (run_id, agent_role, sequence_no, body, body_hash,
           provider, model_id, model_version, prompt_hash,
           tokens_in, tokens_out, cost_usd, status)
        VALUES (CAST(:r AS uuid),'bull_researcher',0,
                'safe narrative','h','mock','m1','v1','h',1,1,0,'succeeded')
        """
    ), {"r": rid})
    session.commit()
    r = client.get(
        f"/api/research/runs/{rid}",
        headers={"X-Auth-User-Id": "alice"},
    )
    j = r.json()
    assert j["tier"] == "free"
    assert j["outputs"] == []


def test_pro_tier_still_hides_audit_operator_controls(session, client):
    _seed_user(session, uid="alice")
    _seed_subscription(
        session, subject_type="user", subject_id="alice",
        tier="pro", status="active",
    )
    r = client.get(
        "/api/research/audit",
        headers={"X-Auth-User-Id": "alice"},
    )
    assert r.json()["audit_table"] == "tier_below_enterprise"
    r2 = client.get(
        "/api/research/operators",
        headers={"X-Auth-User-Id": "alice"},
    )
    assert r2.json()["operators"] == []


def test_enterprise_tier_can_read_audit(session, client):
    _seed_user(session, uid="boss")
    _seed_user(session, uid="owner")
    _seed_org_with_member(
        session, org_id="acme", owner_id="owner", member_id="boss",
    )
    _seed_subscription(
        session, subject_type="org", subject_id="acme",
        tier="enterprise", status="active",
    )
    session.execute(text(
        """
        INSERT INTO research_ro.research_manual_run_audit
          (operator_id, symbol, as_of, provider, request_source, status)
        VALUES ('op','UNH','2026-04-29','mock','cli','accepted')
        """
    ))
    session.commit()
    r = client.get(
        "/api/research/audit",
        headers={"X-Auth-User-Id": "boss"},
    )
    j = r.json()
    assert j["audit_table"] == "present"
    assert len(j["rows"]) >= 1


def test_orgs_endpoint_returns_membership(session, client):
    _seed_user(session, uid="alice")
    _seed_user(session, uid="owner")
    _seed_org_with_member(
        session, org_id="acme", owner_id="owner", member_id="alice",
    )
    r = client.get(
        "/api/auth/orgs",
        headers={"X-Auth-User-Id": "alice"},
    )
    j = r.json()
    assert any(o["id"] == "acme" for o in j["orgs"])


def test_no_post_research_routes_phase_g(client):
    paths = [
        "/api/research/runs",
        "/api/research/usage/summary",
        "/api/research/alerts",
        "/api/research/operators",
        "/api/auth/me",
        "/api/auth/orgs",
    ]
    for p in paths:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            r = client.request(method, p)
            assert r.status_code in (404, 405), f"{method} {p}"


# Static guards ----------------------------------------------------------

import re
from pathlib import Path


_PHASE_G_FILES = (
    "apps/api/src/auth/resolver.py",
    "apps/api/src/api/auth_me.py",
    "infra/alembic/versions/060_auth_subscription_org.py",
)


def test_no_scheduler_worker_phase_g():
    worker = Path("apps/worker/src")
    if not worker.exists():
        pytest.skip("worker dir absent")
    blob = ""
    for p in worker.rglob("*.py"):
        blob += p.read_text(encoding="utf-8", errors="ignore")
    for tok in (
        "auth.resolver", "auth_me", "subscription",
        "organization_member",
    ):
        assert tok not in blob, f"worker references {tok}"


def test_no_execution_imports_phase_g():
    forbidden = (
        "apps.api.src.domain.features.feature_engine",
        "apps.api.src.domain.recommendations.recommendation_engine",
        "apps.api.src.data.evaluation",
        "apps.api.src.domain.stock_engine.decision_engine",
        "apps.api.src.options.paper",
        "apps.api.src.domain.execution",
        "langchain", "langgraph",
    )
    for rel in _PHASE_G_FILES:
        p = Path(rel)
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        for bad in forbidden:
            assert bad not in src, f"{rel} imports {bad}"


def test_research_router_still_only_get_phase_g():
    src = Path("apps/api/src/api/research.py").read_text(encoding="utf-8")
    posts = re.findall(r"@router\.(post|put|patch|delete)\b", src)
    assert posts == []
    src2 = Path("apps/api/src/api/auth_me.py").read_text(encoding="utf-8")
    posts2 = re.findall(r"@router\.(post|put|patch|delete)\b", src2)
    assert posts2 == []
