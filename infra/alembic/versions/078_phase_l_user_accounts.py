"""Phase L M078 — User accounts (dual-account spine).

Introduces user-side $100k paper accounts to mirror the AI's paper
portfolio. Schema is additive; no existing tables modified.

Tables:
  * user_account              — one row per user, with $100k starting balance
  * user_paper_position       — user's open positions
  * user_paper_trade          — user's executed paper trades (mirrors paper_trade shape)
  * user_visit_log            — per-surface visit log for anti-compulsion + returning-user UX

Constraints:
  * paper_only invariant enforced at schema level (CHECK paper_only = TRUE)
  * Indexes for the canonical query patterns (user_id + is_open; user_id + fill_ts)

Revision ID: 078_phase_l_user_accounts
Revises: 077_ai_playbook
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "078_phase_l_user_accounts"
down_revision = "077_ai_playbook"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_account",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column(
            "starting_paper_balance",
            sa.Numeric(20, 6),
            nullable=False,
            server_default="100000",
        ),
        sa.Column(
            "paper_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "persona",
            sa.String(32),
            nullable=False,
            server_default="novice",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("paper_only = TRUE", name="ck_user_account_paper_only"),
    )

    op.create_table(
        "user_paper_position",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user_account.id"),
            nullable=False,
        ),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 10), nullable=False),
        sa.Column("avg_cost", sa.Numeric(20, 6), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_open",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
    )
    op.create_index(
        "idx_user_paper_position_user_open",
        "user_paper_position",
        ["user_id", "is_open"],
    )

    op.create_table(
        "user_paper_trade",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user_account.id"),
            nullable=False,
        ),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 10), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fill_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fill_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(20, 6), nullable=True),
        sa.Column("your_reason", sa.Text(), nullable=True),
        sa.Column("decision_source_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "side IN ('buy','sell')", name="ck_user_paper_trade_side"
        ),
    )
    op.create_index(
        "idx_user_paper_trade_user_ts",
        "user_paper_trade",
        ["user_id", "fill_ts"],
    )

    op.create_table(
        "user_visit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user_account.id"),
            nullable=False,
        ),
        sa.Column("surface", sa.String(64), nullable=False),
        sa.Column(
            "visited_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_user_visit_log_user_ts",
        "user_visit_log",
        ["user_id", sa.text("visited_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_user_visit_log_user_ts", table_name="user_visit_log")
    op.drop_table("user_visit_log")
    op.drop_index("idx_user_paper_trade_user_ts", table_name="user_paper_trade")
    op.drop_table("user_paper_trade")
    op.drop_index("idx_user_paper_position_user_open", table_name="user_paper_position")
    op.drop_table("user_paper_position")
    op.drop_table("user_account")
