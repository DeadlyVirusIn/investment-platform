"""M3 profile onboarding — user_profile table (additive, non-destructive).

Collect-only investing profile, one row per app_user. All fields nullable
(partial profiles allowed) and constrained to small enum sets via CHECK. NO
sensitive data (no income, net worth, age, employer, etc.). NO recommendation
behavior is wired by this migration.

Revision ID: 106_user_profile
Revises: 105_login_attempt
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "106_user_profile"
down_revision = "105_login_attempt"
branch_labels = None
depends_on = None

_ENUMS = {
    "investing_experience": ("none", "beginner", "intermediate", "experienced"),
    "investing_goal": ("learn", "grow_wealth", "income", "preserve", "retirement"),
    "risk_comfort": ("low", "medium", "high"),
    "time_horizon": ("short", "medium", "long"),
    "preferred_style": ("steady", "balanced", "growth"),
    "liquidity_need": ("low", "medium", "high"),
    "options_experience": ("none", "learning", "experienced"),
}


def upgrade() -> None:
    op.create_table(
        "user_profile",
        sa.Column(
            "user_id", sa.Text(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("investing_experience", sa.Text(), nullable=True),
        sa.Column("investing_goal", sa.Text(), nullable=True),
        sa.Column("risk_comfort", sa.Text(), nullable=True),
        sa.Column("time_horizon", sa.Text(), nullable=True),
        sa.Column("preferred_style", sa.Text(), nullable=True),
        sa.Column("liquidity_need", sa.Text(), nullable=True),
        sa.Column("options_experience", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    for col, allowed in _ENUMS.items():
        vals = ",".join(f"'{v}'" for v in allowed)
        op.create_check_constraint(
            f"ck_user_profile_{col}", "user_profile",
            f"{col} IS NULL OR {col} IN ({vals})",
        )


def downgrade() -> None:
    op.drop_table("user_profile")
