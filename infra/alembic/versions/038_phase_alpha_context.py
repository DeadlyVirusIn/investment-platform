"""Phase SYSTEM-ALPHA-7 — context-aware multiplier table.

Revision ID: 038_phase_alpha_context
Revises: 037_phase_alpha_calibration
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "038_phase_alpha_context"
down_revision = "037_phase_alpha_calibration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alpha_context_multiplier",
        sa.Column("context_key", sa.Text, primary_key=True),
        sa.Column("context", JSONB, nullable=False,
                  server_default="{}"),
        sa.Column("multiplier", sa.Numeric(6, 4), nullable=False,
                  server_default="1.0"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False,
                  server_default="0"),
        sa.Column("sample_size", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("applied_by", sa.Text, nullable=False,
                  server_default="system"),
        sa.Column("applied_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("previous_multiplier", sa.Numeric(6, 4), nullable=True),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="active"),
    )

    op.create_table(
        "alpha_context_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("context_key", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("old_multiplier", sa.Numeric(6, 4), nullable=True),
        sa.Column("new_multiplier", sa.Numeric(6, 4), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False,
                  server_default="0"),
        sa.Column("sample_size", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("applied_by", sa.Text, nullable=False,
                  server_default="system"),
        sa.Column("context", JSONB, nullable=True),
    )
    op.create_index("ix_alpha_context_log_key",
                    "alpha_context_log", ["context_key"])
    op.create_index("ix_alpha_context_log_created",
                    "alpha_context_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_alpha_context_log_created",
                  table_name="alpha_context_log")
    op.drop_index("ix_alpha_context_log_key",
                  table_name="alpha_context_log")
    op.drop_table("alpha_context_log")
    op.drop_table("alpha_context_multiplier")
