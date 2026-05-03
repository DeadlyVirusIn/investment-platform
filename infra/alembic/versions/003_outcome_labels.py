"""Recommendation outcome labeling: triple-barrier columns.

Revision ID: 003
Revises: 002
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EQUITY_NUM = sa.Numeric(20, 6)


def upgrade() -> None:
    op.add_column(
        "recommendation_outcome",
        sa.Column("barrier_label", sa.Integer(), nullable=True),
    )
    op.add_column(
        "recommendation_outcome",
        sa.Column("barrier_first_touch_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "recommendation_outcome",
        sa.Column("suggested_size_pct", EQUITY_NUM, nullable=True),
    )
    op.add_column(
        "recommendation_outcome",
        sa.Column("suggested_stop_price", EQUITY_NUM, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recommendation_outcome", "suggested_stop_price")
    op.drop_column("recommendation_outcome", "suggested_size_pct")
    op.drop_column("recommendation_outcome", "barrier_first_touch_at")
    op.drop_column("recommendation_outcome", "barrier_label")
