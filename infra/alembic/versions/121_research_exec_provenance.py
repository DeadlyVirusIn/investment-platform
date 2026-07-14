"""Wave 2C — research execution & origin provenance (design-approved).

Design of record: docs/architecture/
TRACKED_ENTITY_AND_RESEARCH_PROVENANCE_DESIGN.md. Additive only; NO
backfill anywhere (historical jobs/tasks stay NULL — absence of a link is
honest state, never inferred from logs or free text).

1. agent_job.research_task_id — nullable FK ON DELETE RESTRICT: a job
   belongs to zero or one research task, recorded immutably at submit.
   RESTRICT makes a task with execution history undeletable, which also
   neutralizes the agent_job→agent_job_event CASCADE at the task boundary.
2. research_task.source_report_id — the EXACT report version a follow-up
   was created from. The composite FK (source_report_id,
   follow_up_of_task_id) → research_report(id, task_id) makes a
   cross-task source report structurally impossible; the (id, task_id)
   unique index on research_report exists only as this FK's target.
3. DB-level immutability triggers (arthos_* scoped): provenance columns
   may be set ONLY at INSERT. Any UPDATE that changes
   agent_job.research_task_id, research_task.source_report_id, or
   research_task.follow_up_of_task_id-once-source-is-set is refused by
   the database itself — route absence and service whitelists are not the
   only line of defense. Unrelated updates pass through untouched.

Downgrade removes triggers, functions, constraints, columns, and the
helper unique index, restoring the exact migration-120 schema.

Revision ID: 121_research_exec_provenance
Revises: 120_system_posture_event
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "121_research_exec_provenance"
down_revision = "120_system_posture_event"
branch_labels = None
depends_on = None

# Exposed as module constants so integration tests can install the exact
# same guards on create_all-built schemas (no drift between test and
# migration DDL).
PROVENANCE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION arthos_agent_job_provenance_guard()
RETURNS trigger AS $$
BEGIN
    IF NEW.research_task_id IS DISTINCT FROM OLD.research_task_id THEN
        RAISE EXCEPTION
            'agent_job.research_task_id is immutable after insert';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_arthos_agent_job_provenance
    BEFORE UPDATE ON agent_job
    FOR EACH ROW
    EXECUTE FUNCTION arthos_agent_job_provenance_guard();

CREATE OR REPLACE FUNCTION arthos_research_task_provenance_guard()
RETURNS trigger AS $$
BEGIN
    IF NEW.source_report_id IS DISTINCT FROM OLD.source_report_id THEN
        RAISE EXCEPTION
            'research_task.source_report_id is immutable after insert';
    END IF;
    IF OLD.source_report_id IS NOT NULL
       AND NEW.follow_up_of_task_id IS DISTINCT FROM OLD.follow_up_of_task_id
    THEN
        RAISE EXCEPTION
            'research_task.follow_up_of_task_id is immutable once '
            'source_report_id is set';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_arthos_research_task_provenance
    BEFORE UPDATE ON research_task
    FOR EACH ROW
    EXECUTE FUNCTION arthos_research_task_provenance_guard();
"""

PROVENANCE_TRIGGER_DROP_SQL = """
DROP TRIGGER IF EXISTS trg_arthos_agent_job_provenance ON agent_job;
DROP FUNCTION IF EXISTS arthos_agent_job_provenance_guard();
DROP TRIGGER IF EXISTS trg_arthos_research_task_provenance ON research_task;
DROP FUNCTION IF EXISTS arthos_research_task_provenance_guard();
"""


def upgrade() -> None:
    # -- 1. task ↔ job execution provenance --------------------------------
    op.add_column(
        "agent_job",
        sa.Column("research_task_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_job_research_task",
        "agent_job",
        "research_task",
        ["research_task_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_agent_job_research_task",
        "agent_job",
        ["research_task_id"],
        postgresql_where=sa.text("research_task_id IS NOT NULL"),
    )

    # -- 2. follow-up ← exact source report version -------------------------
    # FK-target-only unique (id is already the PK; this composite exists so
    # the composite FK below can reference it).
    op.create_unique_constraint(
        "uq_research_report_id_task", "research_report", ["id", "task_id"]
    )
    op.add_column(
        "research_task",
        sa.Column("source_report_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_research_task_source_report",
        "research_task",
        "research_report",
        ["source_report_id", "follow_up_of_task_id"],
        ["id", "task_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_research_task_source_needs_parent",
        "research_task",
        "source_report_id IS NULL OR follow_up_of_task_id IS NOT NULL",
    )

    # -- 3. DB-enforced immutability ----------------------------------------
    op.execute(PROVENANCE_TRIGGER_SQL)


def downgrade() -> None:
    op.execute(PROVENANCE_TRIGGER_DROP_SQL)
    op.drop_constraint(
        "ck_research_task_source_needs_parent", "research_task", type_="check"
    )
    op.drop_constraint(
        "fk_research_task_source_report", "research_task", type_="foreignkey"
    )
    op.drop_column("research_task", "source_report_id")
    op.drop_constraint(
        "uq_research_report_id_task", "research_report", type_="unique"
    )
    op.drop_index("ix_agent_job_research_task", table_name="agent_job")
    op.drop_constraint(
        "fk_agent_job_research_task", "agent_job", type_="foreignkey"
    )
    op.drop_column("agent_job", "research_task_id")
