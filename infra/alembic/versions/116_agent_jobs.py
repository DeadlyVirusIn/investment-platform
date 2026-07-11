"""Agent Gateway B/D contracts — agent_job + agent_job_event + agent_idempotency.

Spec §4 (B: offline research jobs, D: draft reports) + §6 (bounded events).
PROPOSED — validated on an ephemeral container only, NOT applied to dev/prod
(dev application is a separate approval-gated step). Additive only.

Design posture (spec §7 prohibitions are structural):
  * job_type is a CHECK enum of hardcoded offline handlers — no executable
    names, paths, modules, shell fragments, URLs, or SQL ever stored;
  * params are size-capped JSONB validated per-type in the service;
  * terminal statuses are immutable (service-enforced; ck guards the shape);
  * error/result summaries are capped columns — never raw stack traces;
  * agent_idempotency is the single atomic replay/conflict gate for BOTH
    write surfaces (jobs + drafts): UNIQUE(token_prefix, idem_key) +
    request_hash comparison, INSERT..ON CONFLICT for race atomicity;
  * every accepted job also gets a research_run registry row (Sprint 5
    discipline) — linked via research_run_id, soft reference.

Revision ID: 116_agent_jobs
Revises: 115_paper_trade_cost_stamp
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "116_agent_jobs"
down_revision = "115_paper_trade_cost_stamp"
branch_labels = None
depends_on = None

JOB_TYPES = "'calibration_study','walk_forward_baseline','drift_report','attribution_fixture'"
JOB_STATUSES = "'queued','running','succeeded','failed','cancelled'"


def upgrade() -> None:
    op.create_table(
        "agent_job",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_uid", sa.String(32), nullable=False),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("params", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        # deterministic seed — required or server-generated, always recorded
        sa.Column("seed", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="queued"),
        sa.Column("token_prefix", sa.String(8), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("research_run_id", sa.String(36)),  # soft ref (registry row)
        sa.Column("result_summary", sa.String(2000)),
        sa.Column("error_summary", sa.String(500)),   # capped — never a stack
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("job_uid", name="uq_agent_job_uid"),
        sa.CheckConstraint(f"job_type IN ({JOB_TYPES})",
                           name="ck_agent_job_type"),
        sa.CheckConstraint(f"status IN ({JOB_STATUSES})",
                           name="ck_agent_job_status"),
        # terminal rows must carry finished_at (immutability anchor)
        sa.CheckConstraint(
            "status IN ('queued','running') OR finished_at IS NOT NULL",
            name="ck_agent_job_finished",
        ),
        sa.CheckConstraint("status <> 'failed' OR error_summary IS NOT NULL",
                           name="ck_agent_job_error"),
        sa.CheckConstraint("pg_column_size(params) <= 16384",
                           name="ck_agent_job_params_size"),
    )
    op.create_index("ix_agent_job_owner_status", "agent_job",
                    ["created_by", "status"])
    op.create_index("ix_agent_job_created", "agent_job",
                    [sa.text("created_at DESC")])

    op.create_table(
        "agent_job_event",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36),
                  sa.ForeignKey("agent_job.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        # bounded payload — status lines only, never stdout/file contents
        sa.Column("payload", sa.String(500), nullable=False,
                  server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("job_id", "seq", name="uq_agent_job_event_seq"),
        sa.CheckConstraint("seq >= 1", name="ck_agent_job_event_seq"),
    )
    op.create_index("ix_agent_job_event_job_seq", "agent_job_event",
                    ["job_id", "seq"])

    op.create_table(
        "agent_idempotency",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_prefix", sa.String(8), nullable=False),
        sa.Column("idem_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),   # job | draft
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("ref_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("token_prefix", "idem_key",
                            name="uq_agent_idem_token_key"),
        sa.CheckConstraint("kind IN ('job','draft')",
                           name="ck_agent_idem_kind"),
    )


def downgrade() -> None:
    op.drop_table("agent_idempotency")
    op.drop_index("ix_agent_job_event_job_seq", table_name="agent_job_event")
    op.drop_table("agent_job_event")
    op.drop_index("ix_agent_job_created", table_name="agent_job")
    op.drop_index("ix_agent_job_owner_status", table_name="agent_job")
    op.drop_table("agent_job")
