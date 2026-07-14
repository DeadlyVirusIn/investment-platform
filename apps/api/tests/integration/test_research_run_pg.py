"""Migration 109 / ResearchRun ORM — lifecycle and integrity pins.

Runs against the pg test DB via the alembic-created or create_all schema.
DB-level pins: CHECK enums reject invalid status/promotion; provenance
(git_sha, config_hash) cannot be silently omitted; approvals reference
runs with ON DELETE RESTRICT (append-only companion: correcting a
decision is a NEW row — no update path is exercised anywhere).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.db.models import ResearchRun, ResearchRunApproval

pytestmark = pytest.mark.integration


def _run(**kw) -> ResearchRun:
    defaults = dict(
        run_uid=f"rr_{uuid.uuid4().hex[:12]}",
        run_type="walk_forward",
        name="test run",
        git_sha="a" * 40,
        config_hash="b" * 64,
    )
    defaults.update(kw)
    return ResearchRun(**defaults)


def _has_check_constraints(session: Session) -> bool:
    """create_all-based harnesses lack the migration's CHECK constraints;
    detect so enum tests assert honestly instead of vacuously passing."""
    n = session.execute(text(
        "SELECT count(*) FROM information_schema.check_constraints "
        "WHERE constraint_name = 'ck_research_run_status'"
    )).scalar()
    return bool(n)


def test_insert_read_update_lifecycle(pg_session: Session) -> None:
    r = _run(parameters={"folds": 8}, random_seed=42)
    pg_session.add(r)
    pg_session.commit()

    row = pg_session.get(ResearchRun, r.id)
    assert row.status == "draft"
    assert row.parameters == {"folds": 8}
    assert row.created_at is not None

    row.status = "running"
    row.metrics = {"auc": 0.52}
    pg_session.commit()
    pg_session.expire_all()
    assert pg_session.get(ResearchRun, r.id).metrics["auc"] == 0.52


def test_provenance_cannot_be_omitted(pg_session: Session) -> None:
    r = _run()
    r.git_sha = None  # type: ignore[assignment]
    pg_session.add(r)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

    r2 = _run()
    r2.config_hash = None  # type: ignore[assignment]
    pg_session.add(r2)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_invalid_status_and_promotion_rejected(pg_session: Session) -> None:
    if not _has_check_constraints(pg_session):
        pytest.skip("schema built via create_all (no migration CHECKs) — "
                    "enum enforcement verified on the alembic-built dev DB")
    bad = _run(status="excellent")
    pg_session.add(bad)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

    bad2 = _run(promotion_status="shipped")
    pg_session.add(bad2)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_approval_append_and_restrict(pg_session: Session) -> None:
    r = _run()
    pg_session.add(r)
    pg_session.commit()

    a = ResearchRunApproval(
        run_id=r.id, decision="approve", approver="owner-test",
        rationale="test decision", run_content_hash="c" * 64,
    )
    pg_session.add(a)
    pg_session.commit()

    # a correction is a NEW row (append-only), never an update
    a2 = ResearchRunApproval(
        run_id=r.id, decision="reject", approver="owner-test",
        rationale="reversed after review", run_content_hash="d" * 64,
    )
    pg_session.add(a2)
    pg_session.commit()
    n = pg_session.execute(text(
        "SELECT count(*) FROM research_run_approval WHERE run_id = :r"
    ), {"r": r.id}).scalar()
    assert n == 2

    # decided-on runs are undeletable (FK RESTRICT)
    with pytest.raises(IntegrityError):
        pg_session.delete(pg_session.get(ResearchRun, r.id))
        pg_session.commit()
    pg_session.rollback()


def test_parent_child_lineage_restrict(pg_session: Session) -> None:
    parent = _run(run_type="optuna_study")
    pg_session.add(parent)
    pg_session.commit()
    child = _run(run_type="optuna_trial", parent_run_id=parent.id)
    pg_session.add(child)
    pg_session.commit()

    with pytest.raises(IntegrityError):     # children pin parents
        pg_session.delete(pg_session.get(ResearchRun, parent.id))
        pg_session.commit()
    pg_session.rollback()
