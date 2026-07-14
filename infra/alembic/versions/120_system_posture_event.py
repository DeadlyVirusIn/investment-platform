"""Research Safe Mode — system_posture_event append-only ledger (Wave 1B).

One additive table recording every posture evaluation, owner incident,
acknowledgment, and incident closure as immutable rows. Posture history is
never updated in place: acknowledgment and closure are their OWN events
(the acknowledged_* columns are written only at insert time by the ack
event itself). Idempotency/concurrency: UNIQUE NULLS NOT DISTINCT over
(previous_event_id, input_hash, posture, triggered_by) — identical
evaluations with the same predecessor collapse to one row, including the
first event where previous_event_id is NULL (PostgreSQL >= 15 semantics;
dev runs PG16).

PROPOSED as revision 120 after verifying ``alembic heads`` == 119 on this
branch (verified 2026-07-13). Validated up/down/up on an ephemeral
container; dev application follows a fresh backup; prod remains at 109.

Revision ID: 120_system_posture_event
Revises: 119_recommendation_preflight
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "120_system_posture_event"
down_revision = "119_recommendation_preflight"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_posture_event",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("posture", sa.String(16), nullable=False),
        sa.Column("reasons_json", sa.Text, nullable=False),
        sa.Column("signal_snapshot_json", sa.Text, nullable=False),
        sa.Column("triggered_by", sa.String(120), nullable=False),
        sa.Column(
            "previous_event_id",
            sa.String(36),
            sa.ForeignKey("system_posture_event.id"),
            nullable=True,
        ),
        sa.Column("evaluator_version", sa.String(32), nullable=False),
        sa.Column("evaluator_git_sha", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "posture IN ('NORMAL','RESTRICTED','SAFE')",
            name="ck_posture_event_posture",
        ),
        sa.CheckConstraint(
            "triggered_by = 'auto' OR triggered_by = 'system' "
            "OR triggered_by LIKE 'owner:%'",
            name="ck_posture_event_trigger",
        ),
        sa.CheckConstraint(
            "char_length(reasons_json) <= 4000",
            name="ck_posture_event_reasons_bound",
        ),
        sa.CheckConstraint(
            "char_length(signal_snapshot_json) <= 16000",
            name="ck_posture_event_snapshot_bound",
        ),
    )
    # Idempotency key incl. the NULL-predecessor first event.
    op.execute(
        "CREATE UNIQUE INDEX ux_posture_event_idempotency "
        "ON system_posture_event "
        "(previous_event_id, input_hash, posture, triggered_by) "
        "NULLS NOT DISTINCT"
    )
    op.create_index(
        "ix_posture_event_created",
        "system_posture_event",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_posture_event_created", table_name="system_posture_event")
    op.execute("DROP INDEX ux_posture_event_idempotency")
    op.drop_table("system_posture_event")
