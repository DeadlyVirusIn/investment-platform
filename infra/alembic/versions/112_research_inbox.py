"""Research Inbox — research_task + research_report
(Elite ArthOS, Priority 5).

Generated per docs/architecture/RESEARCH_INBOX_SPEC.md (Priority-5 slice:
tables + service only — no router, no scheduler wiring; `schedule_expr` is
a DEFINITION column, nothing executes it in this slice).
NOT applied to any database (orchestrator applies; validated on an
ephemeral container only). Additive only; downgrade drops both tables.
All FKs ON DELETE RESTRICT — research delivery is durable, no cascade
path can silently destroy reports.

Immutability contract: a research_report row is frozen at delivery.
The only post-delivery writes are the review fields
(review_status/reviewed_by/reviewed_at), moved exclusively by the
service; corrections are NEW rows with version+1 and
supersedes_report_id set. Staleness is derived at read time
(expires_at / citation observed_at age), never stored.

Revision ID: 112_research_inbox
Revises: 111_thesis_links
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "112_research_inbox"
down_revision = "111_thesis_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_task",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        # symbols CSV ("NVDA,TSM") or free theme text ("semi capex cycle")
        sa.Column("scope", sa.Text),
        # cron TEXT — DEFINITION ONLY in this slice; no dispatcher reads it
        sa.Column("schedule_expr", sa.Text),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="open"),
        sa.Column("created_by", sa.String(64), nullable=False,
                  server_default="owner"),
        sa.Column("follow_up_of_task_id", sa.String(36),
                  sa.ForeignKey("research_task.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('open','paused','closed')",
            name="ck_research_task_status",
        ),
    )
    op.create_index("ix_research_task_status", "research_task", ["status"])
    op.create_index("ix_research_task_follow_up", "research_task",
                    ["follow_up_of_task_id"])

    op.create_table(
        "research_report",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36),
                  sa.ForeignKey("research_task.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        # [{source, url, observed_at}] — service validates every citation
        # carries url + observed_at before insert
        sa.Column("citations", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("provenance", sa.String(16), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False,
                  server_default="pending"),
        sa.Column("reviewed_by", sa.String(64)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("supersedes_report_id", sa.String(36),
                  sa.ForeignKey("research_report.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("task_id", "version",
                            name="uq_research_report_task_version"),
        sa.CheckConstraint("version >= 1", name="ck_research_report_version"),
        sa.CheckConstraint(
            "provenance IN ('generated','human')",
            name="ck_research_report_provenance",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="ck_research_report_review",
        ),
        # reviewed rows must say who/when (thesis_evidence precedent)
        sa.CheckConstraint(
            "review_status = 'pending' "
            "OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_research_report_reviewed",
        ),
    )
    op.create_index("ix_research_report_task", "research_report",
                    ["task_id", sa.text("version DESC")])
    op.create_index("ix_research_report_review", "research_report",
                    ["review_status"])


def downgrade() -> None:
    for ix in ("ix_research_report_review", "ix_research_report_task"):
        op.drop_index(ix, table_name="research_report")
    op.drop_table("research_report")
    for ix in ("ix_research_task_follow_up", "ix_research_task_status"):
        op.drop_index(ix, table_name="research_task")
    op.drop_table("research_task")
