"""ML research: historical_label table.

Revision ID: 015
Revises: 014
Create Date: 2026-04-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "historical_label",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "asset_id",
            sa.String(36),
            sa.ForeignKey("asset.id"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("composite_score", sa.Numeric(20, 6), nullable=True),
        sa.Column("confidence", sa.Numeric(20, 6), nullable=True),
        # Factor inputs frozen at as_of
        sa.Column("residual_momentum_20d", sa.Numeric(20, 6), nullable=True),
        sa.Column("residual_momentum_60d", sa.Numeric(20, 6), nullable=True),
        sa.Column("sector_relative_rank", sa.Numeric(20, 6), nullable=True),
        sa.Column("trend_strength_20d", sa.Numeric(20, 6), nullable=True),
        sa.Column("price_vs_200sma", sa.Numeric(20, 6), nullable=True),
        sa.Column("atr_percent_14", sa.Numeric(20, 6), nullable=True),
        sa.Column("avg_dollar_volume_20d", sa.Numeric(20, 2), nullable=True),
        # Regime frozen at as_of
        sa.Column("market_trend", sa.String(16), nullable=True),
        sa.Column("vol_regime", sa.String(16), nullable=True),
        sa.Column("realized_vol_20d", sa.Numeric(20, 6), nullable=True),
        sa.Column("atr_pctile_1y", sa.Numeric(20, 6), nullable=True),
        # Triple-barrier outcome
        sa.Column("label", sa.Integer(), nullable=False),  # +1 hit, -1 stop, 0 timeout
        sa.Column("forward_return_pct", sa.Numeric(20, 6), nullable=False),
        sa.Column("barrier_first_touch_bar", sa.Integer(), nullable=True),
        sa.Column("barrier_n_bars", sa.Integer(), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("exit_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("pt_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("sl_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("sector", sa.String(32), nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ux_historical_label",
        "historical_label",
        ["as_of_date", "asset_id", "engine_version"],
        unique=True,
    )
    op.create_index(
        "ix_historical_label_date", "historical_label", ["as_of_date"],
    )
    op.create_index(
        "ix_historical_label_symbol", "historical_label", ["symbol"],
    )
    op.create_index(
        "ix_historical_label_engine", "historical_label", ["engine_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_historical_label_engine", table_name="historical_label")
    op.drop_index("ix_historical_label_symbol", table_name="historical_label")
    op.drop_index("ix_historical_label_date", table_name="historical_label")
    op.drop_index("ux_historical_label", table_name="historical_label")
    op.drop_table("historical_label")
