"""Phase OPS1 — paper trading state tables.

Revision ID: 024_phase_ops1_paper_trading
Revises: 023_phase_dl2_data_layer
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "024_phase_ops1_paper_trading"
down_revision = "023_phase_dl2_data_layer"

branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_portfolio_snapshot",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("portfolio_id", sa.Text, nullable=False,
                  server_default="default"),
        sa.Column("equity", sa.Numeric(20, 6), nullable=False),
        sa.Column("cash", sa.Numeric(20, 6), nullable=False),
        sa.Column("open_positions", JSONB, nullable=False),
        sa.Column("daily_pnl", sa.Numeric(20, 6), nullable=False,
                  server_default="0"),
        sa.Column("cum_pct", sa.Numeric(12, 6)),
        sa.Column("max_dd_pct", sa.Numeric(12, 6)),
        sa.Column("regime", sa.Text),
        sa.Column("engine_active", sa.Text),
        sa.Column("run_version", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("portfolio_id", "as_of_date",
                            name="ux_paper_portfolio_daily"),
    )
    op.create_index("ix_paper_portfolio_date", "paper_portfolio_snapshot",
                    ["as_of_date"])

    op.create_table(
        "paper_trade_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("portfolio_id", sa.Text, nullable=False,
                  server_default="default"),
        sa.Column("decision_id", UUID(as_uuid=True)),
        sa.Column("engine", sa.Text, nullable=False),
        sa.Column("instrument", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("exit_date", sa.Date),
        sa.Column("exit_price", sa.Numeric(20, 6)),
        sa.Column("position_size_pct", sa.Numeric(8, 4), nullable=False),
        sa.Column("slippage_bps_assumed", sa.Numeric(8, 2), nullable=False),
        sa.Column("gross_ret_pct", sa.Numeric(12, 6)),
        sa.Column("net_ret_pct", sa.Numeric(12, 6)),
        sa.Column("regime_at_entry", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("decision_version", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="open"),
        sa.Column("target_exit_date", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_paper_trade_portfolio_status", "paper_trade_log",
                    ["portfolio_id", "status"])
    op.create_index("ix_paper_trade_entry_date", "paper_trade_log",
                    ["entry_date"])
    op.create_check_constraint(
        "ck_paper_trade_status",
        "paper_trade_log",
        "status IN ('open', 'closed', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_paper_trade_engine",
        "paper_trade_log",
        "engine IN ('A', 'B')",
    )


def downgrade() -> None:
    op.drop_table("paper_trade_log")
    op.drop_table("paper_portfolio_snapshot")
