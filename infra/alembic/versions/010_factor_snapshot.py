"""Stock engine Batch 3: factor_snapshot + asset.sector column.

Revision ID: 010
Revises: 009
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EQUITY_NUM = sa.Numeric(20, 6)
ADV_NUM = sa.Numeric(20, 2)


def upgrade() -> None:
    # Asset gets an optional sector tag; falls back to asset_class when NULL.
    op.add_column("asset", sa.Column("sector", sa.String(32), nullable=True))

    op.create_table(
        "factor_snapshot",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "asset_id",
            sa.String(36),
            sa.ForeignKey("asset.id"),
            nullable=False,
        ),
        sa.Column("residual_momentum_20d", EQUITY_NUM, nullable=True),
        sa.Column("residual_momentum_60d", EQUITY_NUM, nullable=True),
        sa.Column("sector_relative_rank", EQUITY_NUM, nullable=True),
        sa.Column("trend_strength_20d", EQUITY_NUM, nullable=True),
        sa.Column("price_vs_200sma", EQUITY_NUM, nullable=True),
        sa.Column("atr_percent_14", EQUITY_NUM, nullable=True),
        sa.Column("earnings_proximity_days", sa.Integer(), nullable=True),
        sa.Column("avg_dollar_volume_20d", ADV_NUM, nullable=True),
        sa.Column("feature_set_hash", sa.String(32), nullable=False),
        sa.Column(
            "enough_data",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "stale_data",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ux_factor_snapshot",
        "factor_snapshot",
        ["as_of_date", "asset_id"],
        unique=True,
    )
    op.create_index(
        "ix_factor_snapshot_date",
        "factor_snapshot",
        ["as_of_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_factor_snapshot_date", table_name="factor_snapshot")
    op.drop_index("ux_factor_snapshot", table_name="factor_snapshot")
    op.drop_table("factor_snapshot")
    op.drop_column("asset", "sector")
