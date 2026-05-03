"""Phase ENGINE-B-DECISION-SNAPSHOT — daily decision-framework log.

Stores one row per (as_of_date, current_state) capturing the full
DecisionResult: 9 gates, confidence score breakdown, stability windows,
kill switch state, recommendation. Read-only audit surface.

NEVER touches paper_trade_log, decision_log, or production execution.

Revision ID: 043_engine_b_decision_snapshot
Revises: 042_engine_b_migration_columns
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "043_engine_b_decision_snapshot"
down_revision = "042_engine_b_migration_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engine_b_decision_snapshot",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("current_state", sa.Text, nullable=False),
        sa.Column("recommended_state", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("operator_approval", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("kill_switch_triggered", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("kill_switch_reason", sa.Text),
        sa.Column("n_observations", sa.Integer, nullable=False,
                  server_default=sa.text("0")),
        sa.Column("gates", JSONB, nullable=False),
        sa.Column("failed_gates", JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("score_breakdown", JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("stability_windows", JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("as_of_date", "current_state",
                              name="ux_engine_b_decision_snapshot_date_state"),
        sa.CheckConstraint(
            "action IN ('HOLD', 'READY_FOR_NEXT', 'ADVANCE', 'REVERT')",
            name="ck_engine_b_decision_action"),
        sa.CheckConstraint(
            "label IN ('NOT_READY', 'READY_FOR_REVIEW', 'STRONG_CANDIDATE')",
            name="ck_engine_b_decision_label"),
        sa.CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_engine_b_decision_score_range"),
    )
    op.create_index("ix_engine_b_decision_snapshot_date",
                      "engine_b_decision_snapshot", ["as_of_date"])


def downgrade() -> None:
    op.drop_index("ix_engine_b_decision_snapshot_date",
                    "engine_b_decision_snapshot")
    op.drop_table("engine_b_decision_snapshot")
