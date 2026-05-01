"""Phase 11W (Phase D.1) — end-to-end manual run against Postgres.

Applies the research_ro migration, then exercises
`run_single_asset_context_note` with the deterministic mock
provider. Asserts:
  * 1 research_run row.
  * 1 research_agent_output row.
  * No public-table mutations.
  * Token-violation path inserts research_run only (no output).
  * Provider-error path inserts research_run only (no output).
  * Idempotency unique key blocks duplicate runs.
"""

from __future__ import annotations

import datetime as dt
import importlib

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.research.input_snapshot import build_input_snapshot
from apps.api.src.research.manual_run import (
    PHASE_D1_AGENT_ROLE,
    run_single_asset_context_note,
)
from apps.api.src.research.providers.mock_provider import (
    MockResearchProvider,
)


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Migration helper — same pattern as Phase B integration test.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def research_schema(pg_engine):
    mod = importlib.import_module(
        "infra.alembic.versions.052_research_ro_init"
    )
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    yield pg_engine

    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()


@pytest.fixture
def session(research_schema, pg_session):
    """Use the conftest pg_session (superuser) so research_ro INSERTs
    work without role-switching gymnastics. The role-grant boundary
    is verified independently in test_research_schema_isolation_pg.py."""
    return pg_session


def _count(session: Session, table: str, schema: str = "public") -> int:
    return session.execute(
        text(f"SELECT count(*) FROM {schema}.{table}")
    ).scalar_one()


def _public_table_counts(session: Session) -> dict[str, int]:
    """Snapshot relevant public-table row counts so we can assert
    no mutation occurred during a research run."""
    return {
        t: _count(session, t)
        for t in (
            "candidate_idea", "asset", "alert",
        )
    }


# ---------------------------------------------------------------------------
# Test 8 — successful run inserts exactly 1 + 1
# ---------------------------------------------------------------------------


def test_successful_run_inserts_one_run_and_one_output(session):
    before = _public_table_counts(session)
    res = run_single_asset_context_note(
        session,
        symbol="AAPL",
        as_of=dt.date(2026, 4, 30),
        provider_name="mock",
        operator_id="op-1",
    )
    assert res.status == "succeeded"
    assert res.run_id
    assert res.agent_output_id
    assert res.body_hash and len(res.body_hash) == 64
    assert _count(session, "research_run", "research_ro") == 1
    assert _count(session, "research_agent_output", "research_ro") == 1
    after = _public_table_counts(session)
    assert before == after, (
        f"public tables mutated by manual run: before={before} "
        f"after={after}"
    )


# ---------------------------------------------------------------------------
# Test 9 — no public-table writes during a manual run
# ---------------------------------------------------------------------------


def test_run_does_not_write_to_public_execution_tables(session):
    before = _public_table_counts(session)
    run_single_asset_context_note(
        session,
        symbol="MSFT",
        as_of=dt.date(2026, 4, 30),
        provider_name="mock",
        operator_id="op-2",
    )
    after = _public_table_counts(session)
    assert before == after


# ---------------------------------------------------------------------------
# Test 10 — research_run has full provenance
# ---------------------------------------------------------------------------


def test_research_run_has_full_provenance(session):
    res = run_single_asset_context_note(
        session,
        symbol="NVDA",
        as_of=dt.date(2026, 4, 30),
        provider_name="mock",
        operator_id="op-3",
    )
    row = session.execute(
        text(
            """
            SELECT provider, model_id, model_version,
                   prompt_template_id, prompt_template_version,
                   prompt_hash, tokens_in, tokens_out, cost_usd,
                   status, triggered_by, operator_id,
                   schema_version, prompt_bundle_hash,
                   input_snapshot_hash
            FROM research_ro.research_run WHERE id = :id
            """
        ),
        {"id": res.run_id},
    ).mappings().first()
    assert row is not None
    assert row["provider"] == "mock"
    assert row["model_id"] == "research-mock-v1"
    assert row["model_version"] == "2026-04-30"
    assert row["prompt_template_id"] == "single_asset_context_note_v1"
    assert row["prompt_template_version"] == 1
    assert row["prompt_hash"] == res.prompt_hash
    assert row["status"] == "succeeded"
    assert row["triggered_by"] == "manual"
    assert row["operator_id"] == "op-3"
    assert row["input_snapshot_hash"] == res.input_snapshot_hash


# ---------------------------------------------------------------------------
# Test 11 — research_agent_output has body_hash + evidence_refs
# ---------------------------------------------------------------------------


def test_agent_output_has_body_hash_and_evidence_refs(session):
    res = run_single_asset_context_note(
        session,
        symbol="GOOGL",
        as_of=dt.date(2026, 4, 30),
        provider_name="mock",
        operator_id="op-4",
    )
    row = session.execute(
        text(
            """
            SELECT body, body_hash, evidence_refs, agent_role,
                   provider, model_id, status
            FROM research_ro.research_agent_output WHERE id = :id
            """
        ),
        {"id": res.agent_output_id},
    ).mappings().first()
    assert row is not None
    assert row["body"]
    assert row["body_hash"] == res.body_hash
    assert row["evidence_refs"] == []
    assert row["agent_role"] == PHASE_D1_AGENT_ROLE
    assert row["provider"] == "mock"
    assert row["status"] == "succeeded"


# ---------------------------------------------------------------------------
# Test 12 — duplicate run hits idempotency unique key
# ---------------------------------------------------------------------------


def test_duplicate_run_raises_integrity_error_on_idempotency_key(session):
    run_single_asset_context_note(
        session,
        symbol="META", as_of=dt.date(2026, 4, 30),
        provider_name="mock", operator_id="op-5",
    )
    with pytest.raises(IntegrityError):
        run_single_asset_context_note(
            session,
            symbol="META", as_of=dt.date(2026, 4, 30),
            provider_name="mock", operator_id="op-5",
        )


# ---------------------------------------------------------------------------
# Test 13 — unsafe provider body → token_violation, no agent_output
# ---------------------------------------------------------------------------


def test_unsafe_body_inserts_token_violation_only(session, monkeypatch):
    # Force the resolver to return an unsafe-body provider for this
    # call.
    from apps.api.src.research import manual_run as mr

    def _unsafe_resolver(name: str):
        return MockResearchProvider(force_unsafe_body=True)

    monkeypatch.setattr(mr, "_resolve_provider", _unsafe_resolver)

    res = run_single_asset_context_note(
        session,
        symbol="TSLA", as_of=dt.date(2026, 4, 30),
        provider_name="mock", operator_id="op-6",
    )
    assert res.status == "token_violation"
    assert res.agent_output_id is None
    assert res.body_hash is None
    # research_run row exists with the violation status; no output.
    run_status = session.execute(
        text(
            "SELECT status FROM research_ro.research_run WHERE id = :id"
        ),
        {"id": res.run_id},
    ).scalar_one()
    assert run_status == "token_violation"
    out_count = session.execute(
        text(
            "SELECT count(*) FROM research_ro.research_agent_output "
            "WHERE run_id = :id"
        ),
        {"id": res.run_id},
    ).scalar_one()
    assert out_count == 0


# ---------------------------------------------------------------------------
# Test 14 — provider failure → provider_error, no agent_output
# ---------------------------------------------------------------------------


def test_provider_failure_inserts_provider_error_only(session, monkeypatch):
    from apps.api.src.research import manual_run as mr

    def _failure_resolver(name: str):
        return MockResearchProvider(force_failure=True)

    monkeypatch.setattr(mr, "_resolve_provider", _failure_resolver)

    res = run_single_asset_context_note(
        session,
        symbol="VZ", as_of=dt.date(2026, 4, 30),
        provider_name="mock", operator_id="op-7",
    )
    assert res.status == "provider_error"
    assert res.agent_output_id is None
    assert res.body_hash is None
    run_status = session.execute(
        text(
            "SELECT status FROM research_ro.research_run WHERE id = :id"
        ),
        {"id": res.run_id},
    ).scalar_one()
    assert run_status == "provider_error"
    out_count = session.execute(
        text(
            "SELECT count(*) FROM research_ro.research_agent_output "
            "WHERE run_id = :id"
        ),
        {"id": res.run_id},
    ).scalar_one()
    assert out_count == 0


# ---------------------------------------------------------------------------
# Test 15 — generated_at excluded from input_snapshot_hash
# ---------------------------------------------------------------------------


def test_generated_at_excluded_from_input_snapshot_hash(session):
    """Two snapshots from identical DB state should produce the same
    input_snapshot_hash even though their `generated_at` values
    differ. We invoke build_input_snapshot directly twice and
    compute the hash to verify the contract."""
    from apps.api.src.research.provenance import (
        compute_input_snapshot_hash,
    )

    snap_a = build_input_snapshot(
        session, symbol="HON", as_of=dt.date(2026, 4, 30),
    )
    snap_b = build_input_snapshot(
        session, symbol="HON", as_of=dt.date(2026, 4, 30),
    )
    # generated_at timestamps differ at sub-second granularity.
    assert compute_input_snapshot_hash(snap_a) == (
        compute_input_snapshot_hash(snap_b)
    )
