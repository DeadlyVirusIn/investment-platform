"""Phase SYSTEM-ALPHA-6 — calibration log + active parameter overrides.

Revision ID: 037_phase_alpha_calibration
Revises: 036_phase_paper_run_log
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "037_phase_alpha_calibration"
down_revision = "036_phase_paper_run_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Active parameter overrides — current applied state.
    # One row per parameter_key. Runner reads at decision time.
    op.create_table(
        "alpha_param_active",
        sa.Column("parameter_key", sa.Text, primary_key=True),
        sa.Column("value", sa.Numeric(12, 6), nullable=False),
        sa.Column("previous_value", sa.Numeric(12, 6), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False,
                  server_default="0"),
        sa.Column("sample_size", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("applied_by", sa.Text, nullable=False,
                  server_default="system"),
        sa.Column("applied_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="active"),
    )

    # Append-only audit trail.
    op.create_table(
        "alpha_calibration_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("parameter_key", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),      # recommend|apply|revert
        sa.Column("old_value", sa.Numeric(12, 6), nullable=True),
        sa.Column("new_value", sa.Numeric(12, 6), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False,
                  server_default="0"),
        sa.Column("sample_size", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("applied_by", sa.Text, nullable=False,
                  server_default="system"),
        sa.Column("auto_applied", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="pending"),
        sa.Column("metrics", JSONB, nullable=True),
    )
    op.create_index("ix_alpha_calibration_log_param",
                    "alpha_calibration_log", ["parameter_key"])
    op.create_index("ix_alpha_calibration_log_created",
                    "alpha_calibration_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_alpha_calibration_log_created",
                  table_name="alpha_calibration_log")
    op.drop_index("ix_alpha_calibration_log_param",
                  table_name="alpha_calibration_log")
    op.drop_table("alpha_calibration_log")
    op.drop_table("alpha_param_active")
