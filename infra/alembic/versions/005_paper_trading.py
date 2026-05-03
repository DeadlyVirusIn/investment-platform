"""Paper trading tables.

Revision ID: 005
Revises: 004
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CRYPTO_NUM = sa.Numeric(28, 10)
EQUITY_NUM = sa.Numeric(20, 6)


def upgrade() -> None:
    op.create_table(
        "paper_portfolio",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("starting_cash", EQUITY_NUM, nullable=False),
        sa.Column("cash", EQUITY_NUM, nullable=False),
        sa.Column("config_json", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "paper_position",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("portfolio_id", sa.String(36),
                  sa.ForeignKey("paper_portfolio.id"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("asset.id"), nullable=False),
        sa.Column("quantity", CRYPTO_NUM, nullable=False),
        sa.Column("avg_cost", EQUITY_NUM, nullable=False),
        sa.Column("is_open", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_paper_position_open",
        "paper_position",
        ["portfolio_id", "asset_id", "is_open"],
    )

    op.create_table(
        "paper_trade",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("portfolio_id", sa.String(36),
                  sa.ForeignKey("paper_portfolio.id"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("asset.id"), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", CRYPTO_NUM, nullable=False),
        sa.Column("fill_price", EQUITY_NUM, nullable=False),
        sa.Column("fill_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("recommendation_id", sa.String(36),
                  sa.ForeignKey("recommendation.id"), nullable=True),
        sa.Column("realized_pnl", EQUITY_NUM, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_paper_trade_portfolio_ts",
        "paper_trade",
        ["portfolio_id", "fill_ts"],
    )

    op.create_table(
        "paper_equity_snapshot",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("portfolio_id", sa.String(36),
                  sa.ForeignKey("paper_portfolio.id"), nullable=False),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cash", EQUITY_NUM, nullable=False),
        sa.Column("positions_value", EQUITY_NUM, nullable=False),
        sa.Column("total_equity", EQUITY_NUM, nullable=False),
        sa.Column("unrealized_pnl", EQUITY_NUM, nullable=True),
        sa.Column("realized_pnl_cumulative", EQUITY_NUM, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("portfolio_id", "snapshot_date",
                            name="uq_paper_equity_snapshot"),
    )


def downgrade() -> None:
    op.drop_table("paper_equity_snapshot")
    op.drop_index("ix_paper_trade_portfolio_ts", "paper_trade")
    op.drop_table("paper_trade")
    op.drop_index("ix_paper_position_open", "paper_position")
    op.drop_table("paper_position")
    op.drop_table("paper_portfolio")
