"""Phase 2 stock fix Phase 4 — paper-trading execution funnel telemetry.

Adds `paper_execution_funnel` to make the auto_trader funnel visible
to SQL / API / UI. Today the only record of WHY buys are rejected
lives in artifacts/paper_trading_skips/<date>.jsonl files written by
run_paper_trading. Operators cannot query that, the API cannot serve
it, and the WebUI cannot render it.

Schema mirrors the proposal in the Phase 2 design pass and the
options canary funnel pattern from migration 069.

Strictly additive. No mutation of any existing table.

Revision ID: 070_paper_execution_funnel
Revises: 069_options_canary_pre0
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "070_paper_execution_funnel"
down_revision = "069_options_canary_pre0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_execution_funnel",
        sa.Column(
            "id", sa.BigInteger(),
            sa.Identity(always=False), primary_key=True,
        ),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column(
            "portfolio_id", sa.String(36),
            sa.ForeignKey(
                "paper_portfolio.id",
                name="fk_paper_funnel_portfolio",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        # Top of funnel
        sa.Column(
            "buy_candidates_total", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "buys_executed", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "sells_executed", sa.Integer(), nullable=False, server_default="0",
        ),
        # Skip-reason rollup (mirrors auto_trader._record_skip codes)
        sa.Column(
            "skip_portfolio_full", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_duplicate_holding", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_pending_sell_same_asset", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_sizing_below_threshold", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_position_too_small", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_cash_constraint", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_execution_failure", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_unknown_reason", sa.Integer(), nullable=False,
            server_default="0",
        ),
        # Saturation snapshot at run start
        sa.Column("open_positions_at_start", sa.Integer(), nullable=False),
        sa.Column("max_open_positions", sa.Integer(), nullable=False),
        sa.Column("cash_at_start", sa.Numeric(20, 4), nullable=False),
        sa.Column("equity_at_start", sa.Numeric(20, 4), nullable=False),
        sa.Column("details_json", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "run_date", "portfolio_id",
            name="ux_paper_funnel_run_portfolio",
        ),
    )
    op.create_index(
        "ix_paper_funnel_run_date",
        "paper_execution_funnel",
        [sa.text("run_date DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_paper_funnel_run_date", table_name="paper_execution_funnel")
    op.drop_table("paper_execution_funnel")
