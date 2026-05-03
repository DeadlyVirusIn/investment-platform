"""Stock engine Batch 2: regime_snapshot (daily market trend + volatility).

Revision ID: 009
Revises: 008
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EQUITY_NUM = sa.Numeric(20, 6)


def upgrade() -> None:
    op.create_table(
        "regime_snapshot",
        sa.Column("as_of_date", sa.Date(), primary_key=True),
        sa.Column("benchmark_symbol", sa.String(16), nullable=False),
        sa.Column("market_trend", sa.String(16), nullable=False),
        sa.Column("vol_regime", sa.String(16), nullable=False),
        sa.Column("breadth_regime", sa.String(16), nullable=True),
        sa.Column("sma50_over_sma200", sa.Boolean(), nullable=False),
        sa.Column("realized_vol_20d", EQUITY_NUM, nullable=False),
        sa.Column("atr_pctile_1y", EQUITY_NUM, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("regime_snapshot")
