"""M1B login rate-limit — login_attempt table (additive, non-destructive).

Records login attempts (email + ip + succeeded + created_at) so the login
endpoint can throttle brute-force attempts. No destructive changes.

Revision ID: 105_login_attempt
Revises: 104_accounts_m1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "105_login_attempt"
down_revision = "104_accounts_m1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_attempt",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("ip", sa.Text(), nullable=False, server_default=""),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_index("ix_login_attempt_email_created", "login_attempt", ["email", "created_at"])
    op.create_index("ix_login_attempt_ip_created", "login_attempt", ["ip", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_login_attempt_ip_created", table_name="login_attempt")
    op.drop_index("ix_login_attempt_email_created", table_name="login_attempt")
    op.drop_table("login_attempt")
