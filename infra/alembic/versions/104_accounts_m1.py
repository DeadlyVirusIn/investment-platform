"""Accounts M1 — real account/session identity (additive, non-destructive).

Adds:
  * app_user.password_hash (nullable) — password auth for email accounts.
  * user_session table — revocable DB-backed sessions (token PK, user_id FK,
    created_at, expires_at, revoked_at).

NO destructive changes. NO portfolio rewrites. Existing device-id books and
demo data are untouched.

Revision ID: 104_accounts_m1
Revises: 103_company_name_refresh
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "104_accounts_m1"
down_revision = "103_company_name_refresh"
branch_labels = None
depends_on = None


_PROVIDERS_OLD = "('placeholder','jwt','oauth_google','oauth_github','sso')"
_PROVIDERS_NEW = "('placeholder','jwt','oauth_google','oauth_github','sso','password')"


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("password_hash", sa.Text(), nullable=True),
    )
    # Allow the 'password' auth_provider used by M1 email accounts.
    op.execute("ALTER TABLE app_user DROP CONSTRAINT IF EXISTS ck_app_user_provider")
    op.execute(
        f"ALTER TABLE app_user ADD CONSTRAINT ck_app_user_provider "
        f"CHECK (auth_provider IN {_PROVIDERS_NEW})"
    )
    op.create_table(
        "user_session",
        sa.Column("token", sa.Text(), primary_key=True),
        sa.Column(
            "user_id", sa.Text(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_session_user_id", "user_session", ["user_id"])


def downgrade() -> None:
    op.execute("ALTER TABLE app_user DROP CONSTRAINT IF EXISTS ck_app_user_provider")
    op.execute(
        f"ALTER TABLE app_user ADD CONSTRAINT ck_app_user_provider "
        f"CHECK (auth_provider IN {_PROVIDERS_OLD})"
    )
    op.drop_index("ix_user_session_user_id", table_name="user_session")
    op.drop_table("user_session")
    op.drop_column("app_user", "password_hash")
