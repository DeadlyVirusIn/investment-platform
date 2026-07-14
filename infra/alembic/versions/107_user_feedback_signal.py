"""M5 demand-validation — user_feedback_signal table (additive, non-destructive).

Collect-only product-demand signals (trust/useful/would-use-again/beta-interest
etc.). One row per signal. No sensitive data. NO recommendation behavior wired.

Revision ID: 107_user_feedback_signal
Revises: 106_user_profile
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "107_user_feedback_signal"
down_revision = "106_user_profile"
branch_labels = None
depends_on = None

SIGNAL_TYPES = (
    "trust_useful", "trust_not_useful", "would_use_again", "would_not_use_again",
    "confusing", "beta_interest", "investor_interest", "feedback_text",
)
SURFACES = ("pick_detail", "options_detail", "account", "profile", "discover")


def upgrade() -> None:
    op.create_table(
        "user_feedback_signal",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "user_id", sa.Text(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("session_or_device_id", sa.Text(), nullable=True),
        sa.Column("surface", sa.Text(), nullable=False),
        sa.Column("signal_type", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_check_constraint(
        "ck_feedback_signal_type", "user_feedback_signal",
        "signal_type IN (" + ",".join(f"'{v}'" for v in SIGNAL_TYPES) + ")",
    )
    op.create_check_constraint(
        "ck_feedback_surface", "user_feedback_signal",
        "surface IN (" + ",".join(f"'{v}'" for v in SURFACES) + ")",
    )
    op.create_index("ix_feedback_created", "user_feedback_signal", ["created_at"])
    op.create_index("ix_feedback_user", "user_feedback_signal", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_user", table_name="user_feedback_signal")
    op.drop_index("ix_feedback_created", table_name="user_feedback_signal")
    op.drop_table("user_feedback_signal")
