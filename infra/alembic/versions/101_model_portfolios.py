"""MVP — model portfolios ("Ideas you can follow and prove").

Adds four additive tables (no existing table touched):
  * model_portfolio          — curated follow-able portfolio (slug, name, thesis)
  * model_portfolio_holding  — weighted holdings (symbol, weight 0..1)
  * model_portfolio_perf     — cached daily track record (d, nav, ret)
  * portfolio_follow         — links a user's paper portfolio to a model

Revision ID: 101_model_portfolios
Revises: 100_paper_position_attribution
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "101_model_portfolios"
down_revision = "100_paper_position_attribution"
branch_labels = None
depends_on = None

EQUITY_NUM = sa.Numeric(20, 6)


def upgrade() -> None:
    op.create_table(
        "model_portfolio",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("thesis", sa.Text()),
        sa.Column("risk_label", sa.String(32)),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "model_portfolio_holding",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_portfolio_id", sa.String(36),
                  sa.ForeignKey("model_portfolio.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("weight", EQUITY_NUM, nullable=False),
        sa.UniqueConstraint("model_portfolio_id", "symbol", name="uq_model_holding"),
    )

    op.create_table(
        "model_portfolio_perf",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_portfolio_id", sa.String(36),
                  sa.ForeignKey("model_portfolio.id", ondelete="CASCADE"), nullable=False),
        sa.Column("d", sa.Date(), nullable=False),
        sa.Column("nav", EQUITY_NUM, nullable=False),
        sa.Column("ret", EQUITY_NUM),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("model_portfolio_id", "d", name="uq_model_perf_day"),
    )
    op.create_index("ix_model_perf_pf_day", "model_portfolio_perf",
                    ["model_portfolio_id", sa.text("d DESC")])

    op.create_table(
        "portfolio_follow",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(64)),
        sa.Column("model_portfolio_id", sa.String(36),
                  sa.ForeignKey("model_portfolio.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paper_portfolio_id", sa.String(36), nullable=False),
        sa.Column("followed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_follow_model", "portfolio_follow", ["model_portfolio_id"])
    op.create_index("ix_follow_user", "portfolio_follow", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_follow_user", table_name="portfolio_follow")
    op.drop_index("ix_follow_model", table_name="portfolio_follow")
    op.drop_table("portfolio_follow")
    op.drop_index("ix_model_perf_pf_day", table_name="model_portfolio_perf")
    op.drop_table("model_portfolio_perf")
    op.drop_table("model_portfolio_holding")
    op.drop_table("model_portfolio")
