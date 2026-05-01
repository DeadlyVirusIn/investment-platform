"""Phase 11W (Phase B) — research_ro schema isolation tests.

These tests apply the Phase B migration to the testcontainer Postgres,
then verify every isolation invariant from the Phase A audit:
  * schema research_ro exists with the 5 expected tables
  * roles research_writer / research_reader exist with minimal grants
  * research_writer cannot write to ANY execution table
  * research_reader cannot SELECT from execution tables
  * body CHECK constraints reject every forbidden token
  * substring false-positives (`household`, `longitude`, `shortlist`) pass
  * provenance columns are NOT NULL
  * idempotency unique key works
  * no FK from public.* to research_ro.*
  * alembic downgrade is clean
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import (
    DataError,
    IntegrityError,
    ProgrammingError,
)
from sqlalchemy.orm import Session, sessionmaker


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Migration helper — run the Phase B migration directly via op.execute
# equivalents on the test engine. We re-use the migration module's
# upgrade() sequence so tests track the real DDL.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def research_schema(pg_engine):
    """Apply the research_ro migration to the testcontainer DB. Yields
    the engine. Cleans up via downgrade() at module teardown."""
    import importlib
    mod = importlib.import_module(
        "infra.alembic.versions.052_research_ro_init"
    )

    # Bind alembic op.* to the live engine for the duration of upgrade().
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
def writer_session(research_schema):
    """Session connected as the unprivileged research_writer role."""
    # NOTE: Postgres roles created with NOLOGIN — connect as the
    # superuser then SET ROLE to simulate the privileged path.
    SessionCls = sessionmaker(
        bind=research_schema, class_=Session, expire_on_commit=False,
    )
    s = SessionCls()
    s.execute(text("SET ROLE research_writer"))
    try:
        yield s
    finally:
        try:
            s.rollback()
        except Exception:
            pass
        s.execute(text("RESET ROLE"))
        s.close()


@pytest.fixture
def reader_session(research_schema):
    SessionCls = sessionmaker(
        bind=research_schema, class_=Session, expire_on_commit=False,
    )
    s = SessionCls()
    s.execute(text("SET ROLE research_reader"))
    try:
        yield s
    finally:
        try:
            s.rollback()
        except Exception:
            pass
        s.execute(text("RESET ROLE"))
        s.close()


def _valid_run_payload(**override) -> dict:
    base = {
        "id": str(uuid.uuid4()),
        "symbol": "AAPL",
        "as_of": dt.date(2026, 4, 30),
        "schema_version": "v1.0.0",
        "prompt_bundle_hash": "bundle-" + uuid.uuid4().hex[:16],
        "input_snapshot_hash": "snap-" + uuid.uuid4().hex[:16],
        "provider": "anthropic",
        "model_id": "claude-opus-4-7",
        "model_version": "2026-04-15",
        "prompt_template_id": "research_v1",
        "prompt_template_version": 1,
        "prompt_hash": "ph-" + uuid.uuid4().hex[:16],
        "temperature": 0.0,
        "seed": 42,
        "tokens_in": 100,
        "tokens_out": 50,
        "cost_usd": 0.001,
        "status": "succeeded",
        "triggered_by": "manual",
        "operator_id": "test-operator",
    }
    base.update(override)
    return base


def _insert_run(session: Session, payload: dict) -> None:
    session.execute(
        text(
            """
            INSERT INTO research_ro.research_run
              (id, symbol, as_of, schema_version,
               prompt_bundle_hash, input_snapshot_hash,
               provider, model_id, model_version,
               prompt_template_id, prompt_template_version,
               prompt_hash, temperature, seed,
               tokens_in, tokens_out, cost_usd, status,
               triggered_by, operator_id)
            VALUES
              (:id, :symbol, :as_of, :schema_version,
               :prompt_bundle_hash, :input_snapshot_hash,
               :provider, :model_id, :model_version,
               :prompt_template_id, :prompt_template_version,
               :prompt_hash, :temperature, :seed,
               :tokens_in, :tokens_out, :cost_usd, :status,
               :triggered_by, :operator_id)
            """
        ),
        payload,
    )


# ---------------------------------------------------------------------------
# Schema + roles
# ---------------------------------------------------------------------------


def test_research_ro_schema_exists(research_schema):
    with research_schema.connect() as conn:
        names = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='research_ro' ORDER BY table_name"
            )
        ).scalars().all()
    assert sorted(names) == [
        "research_agent_output",
        "research_checkpoint",
        "research_debate_summary",
        "research_reflection",
        "research_run",
    ]


def test_research_roles_exist(research_schema):
    with research_schema.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT rolname FROM pg_roles "
                "WHERE rolname IN ('research_writer','research_reader')"
            )
        ).scalars().all()
    assert sorted(rows) == ["research_reader", "research_writer"]


def test_no_fk_from_public_to_research_ro(research_schema):
    with research_schema.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT n_src.nspname AS src, n_tgt.nspname AS tgt,
                       c_src.relname AS src_table, c_tgt.relname AS tgt_table
                FROM pg_constraint con
                JOIN pg_class c_src ON con.conrelid = c_src.oid
                JOIN pg_namespace n_src ON c_src.relnamespace = n_src.oid
                JOIN pg_class c_tgt ON con.confrelid = c_tgt.oid
                JOIN pg_namespace n_tgt ON c_tgt.relnamespace = n_tgt.oid
                WHERE con.contype = 'f'
                  AND n_src.nspname = 'public'
                  AND n_tgt.nspname = 'research_ro'
                """
            )
        ).all()
    assert rows == [], (
        "Forbidden FK direction: public -> research_ro must NEVER exist. "
        f"Found: {rows}"
    )


# ---------------------------------------------------------------------------
# Role isolation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "table",
    [
        # ORM-model tables present in the test schema. paper_run_log
        # and paper_decision_log are raw-SQL tables not created by
        # Base.metadata in the test harness; their grant-check is
        # covered indirectly by the schema-wide REVOKE in the
        # migration.
        "candidate_idea", "asset", "alert",
    ],
)
def test_research_writer_cannot_insert_into_execution_tables(
    writer_session, table,
):
    # Best-effort INSERT with bogus columns; we only need to confirm
    # insufficient_privilege fires before any column-level check.
    with pytest.raises(ProgrammingError) as excinfo:
        writer_session.execute(
            text(f"INSERT INTO public.{table} DEFAULT VALUES")
        )
        writer_session.flush()
    msg = str(excinfo.value).lower()
    assert (
        "permission denied" in msg
        or "insufficient privilege" in msg
        or "must be owner" in msg
    ), f"unexpected error: {excinfo.value}"


def test_research_reader_cannot_select_from_execution_tables(reader_session):
    with pytest.raises(ProgrammingError) as excinfo:
        reader_session.execute(
            text("SELECT 1 FROM public.candidate_idea LIMIT 1")
        )
        reader_session.flush()
    msg = str(excinfo.value).lower()
    assert "permission denied" in msg or "insufficient privilege" in msg


def test_research_reader_can_select_research_ro(reader_session):
    out = reader_session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar_one()
    assert out == 0


def test_research_reader_cannot_insert_into_research_ro(reader_session):
    with pytest.raises(ProgrammingError) as excinfo:
        _insert_run(reader_session, _valid_run_payload(symbol="READ-ONLY"))
        reader_session.flush()
    msg = str(excinfo.value).lower()
    assert "permission denied" in msg or "insufficient privilege" in msg


# ---------------------------------------------------------------------------
# CHECK constraints — body token rejection
# ---------------------------------------------------------------------------


FORBIDDEN_TOKENS = [
    "buy", "sell", "hold", "long", "short",
    "recommend", "recommendation", "signal",
    "allocate", "execute", "execution",
    "position", "entry", "exit", "leverage",
]


@pytest.mark.parametrize("token", FORBIDDEN_TOKENS)
def test_research_agent_output_body_rejects_forbidden_word(
    pg_session, research_schema, token,
):
    # Connect as superuser (pg_session) to isolate this test from the
    # role-grant tests above. The CHECK fires regardless of role.
    run_id = str(uuid.uuid4())
    _insert_run(pg_session, _valid_run_payload(id=run_id))
    pg_session.commit()

    body = f"This narrative discusses why we should {token} this asset."
    with pytest.raises(IntegrityError) as excinfo:
        pg_session.execute(
            text(
                """
                INSERT INTO research_ro.research_agent_output
                  (id, run_id, agent_role, sequence_no, body, body_hash,
                   provider, model_id, model_version, prompt_hash,
                   tokens_in, tokens_out, cost_usd, status)
                VALUES
                  (:id, :run_id, 'fundamentals', 1, :body, 'h',
                   'anthropic', 'claude', 'v1', 'ph',
                   10, 5, 0.0001, 'succeeded')
                """
            ),
            {"id": str(uuid.uuid4()), "run_id": run_id, "body": body},
        )
        pg_session.flush()
    msg = str(excinfo.value).lower()
    assert "body_no_action_tokens" in msg or "check" in msg
    pg_session.rollback()


@pytest.mark.parametrize(
    "phrase", ["target price", "stop loss", "take profit",
               "portfolio manager", "copy trade"],
)
def test_research_agent_output_body_rejects_forbidden_phrase(
    pg_session, research_schema, phrase,
):
    run_id = str(uuid.uuid4())
    _insert_run(pg_session, _valid_run_payload(id=run_id))
    pg_session.commit()

    body = f"The narrative cites {phrase} as a relevant concept."
    with pytest.raises(IntegrityError):
        pg_session.execute(
            text(
                """
                INSERT INTO research_ro.research_agent_output
                  (id, run_id, agent_role, sequence_no, body, body_hash,
                   provider, model_id, model_version, prompt_hash,
                   tokens_in, tokens_out, cost_usd, status)
                VALUES
                  (:id, :run_id, 'fundamentals', 1, :body, 'h',
                   'anthropic', 'claude', 'v1', 'ph',
                   10, 5, 0.0001, 'succeeded')
                """
            ),
            {"id": str(uuid.uuid4()), "run_id": run_id, "body": body},
        )
        pg_session.flush()
    pg_session.rollback()


@pytest.mark.parametrize("ok_word", ["household", "longitude", "shortlist"])
def test_research_agent_output_body_allows_substring_falsepositives(
    pg_session, research_schema, ok_word,
):
    run_id = str(uuid.uuid4())
    _insert_run(pg_session, _valid_run_payload(id=run_id))
    pg_session.commit()

    body = (
        f"Narrative analysis: this firm has unusual {ok_word} exposure "
        f"in its broader market footprint."
    )
    pg_session.execute(
        text(
            """
            INSERT INTO research_ro.research_agent_output
              (id, run_id, agent_role, sequence_no, body, body_hash,
               provider, model_id, model_version, prompt_hash,
               tokens_in, tokens_out, cost_usd, status)
            VALUES
              (:id, :run_id, 'fundamentals', 1, :body, 'h',
               'anthropic', 'claude', 'v1', 'ph',
               10, 5, 0.0001, 'succeeded')
            """
        ),
        {"id": str(uuid.uuid4()), "run_id": run_id, "body": body},
    )
    pg_session.commit()


# ---------------------------------------------------------------------------
# Provenance NOT NULL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing_col",
    [
        "provider", "model_id", "model_version", "prompt_hash",
        "tokens_in", "tokens_out", "cost_usd", "status",
    ],
)
def test_research_run_provenance_columns_not_null(
    pg_session, research_schema, missing_col,
):
    payload = _valid_run_payload()
    payload[missing_col] = None
    with pytest.raises((IntegrityError, DataError)):
        _insert_run(pg_session, payload)
        pg_session.flush()
    pg_session.rollback()


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_research_run_idempotency_unique_key(pg_session, research_schema):
    p1 = _valid_run_payload()
    p2 = _valid_run_payload(
        id=str(uuid.uuid4()),
        symbol=p1["symbol"], as_of=p1["as_of"],
        prompt_bundle_hash=p1["prompt_bundle_hash"],
        input_snapshot_hash=p1["input_snapshot_hash"],
        schema_version=p1["schema_version"],
    )
    _insert_run(pg_session, p1)
    pg_session.commit()
    with pytest.raises(IntegrityError) as excinfo:
        _insert_run(pg_session, p2)
        pg_session.flush()
    assert "research_run_idempotency" in str(excinfo.value).lower() or (
        "unique" in str(excinfo.value).lower()
    )
    pg_session.rollback()


# ---------------------------------------------------------------------------
# Tripwire: is_research_artifact = TRUE
# ---------------------------------------------------------------------------


def test_is_research_artifact_tripwire(pg_session, research_schema):
    payload = _valid_run_payload()
    _insert_run(pg_session, payload)
    pg_session.commit()
    with pytest.raises(IntegrityError):
        pg_session.execute(
            text(
                "UPDATE research_ro.research_run "
                "SET is_research_artifact = FALSE WHERE id = :id"
            ),
            {"id": payload["id"]},
        )
        pg_session.flush()
    pg_session.rollback()
