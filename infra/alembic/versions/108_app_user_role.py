"""Admin-2 — durable owner/admin role on app_user (additive, rollback-safe).

Adds ``access_role`` (default 'user'), a check constraint for allowed values,
and backfills the bootstrap owner. Pairs with the env allowlist
(``ARTHOS_OWNER_EMAILS``) — EITHER the DB role 'owner' OR an allowlisted email
grants owner access. The env allowlist remains a bootstrap/failsafe; the DB
role is the durable source.

Additive only: a new nullable-defaulted column + a check + one UPDATE. Fully
reversible (downgrade drops the column).

Revision ID: 108_app_user_role
Revises: 107_user_feedback_signal
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "108_app_user_role"
down_revision = "107_user_feedback_signal"
branch_labels = None
depends_on = None

ROLES = ("user", "admin", "owner")
BOOTSTRAP_OWNER = "kunalkhurana1@gmail.com"


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("access_role", sa.Text(), server_default="user", nullable=False),
    )
    op.create_check_constraint(
        "ck_app_user_access_role", "app_user",
        "access_role IN (" + ",".join(f"'{r}'" for r in ROLES) + ")",
    )
    # Backfill the bootstrap owner — idempotent, case-insensitive. Constant
    # literal (no user input); safe to inline.
    op.execute(
        "UPDATE app_user SET access_role = 'owner' "
        f"WHERE lower(email) = lower('{BOOTSTRAP_OWNER}')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_app_user_access_role", "app_user", type_="check")
    op.drop_column("app_user", "access_role")
