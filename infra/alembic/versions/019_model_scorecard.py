"""Phase 2 — model_scorecard (read-only analytics layer).

Revision ID: 019
Revises: 018
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_scorecard",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_name", sa.String(64), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("total_signals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("avg_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("avg_drawdown", sa.Numeric(10, 6), nullable=True),
        sa.Column("sharpe_like_metric", sa.Numeric(10, 4), nullable=True),
        sa.Column("avg_days_to_evaluation", sa.Numeric(8, 2), nullable=True),
        sa.Column("max_days_to_evaluation", sa.Integer(), nullable=True),
        sa.Column("pct_within_horizon", sa.Numeric(6, 4), nullable=True),
        sa.Column("calibration", JSONB, nullable=True),
        sa.Column("factor_effectiveness", JSONB, nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ux_scorecard_dedup",
        "model_scorecard",
        ["model_name", "window_start", "window_end"],
        unique=True,
    )
    op.create_index(
        "ix_scorecard_window_end",
        "model_scorecard",
        ["window_end"],
    )


def downgrade() -> None:
    op.drop_index("ix_scorecard_window_end", table_name="model_scorecard")
    op.drop_index("ux_scorecard_dedup", table_name="model_scorecard")
    op.drop_table("model_scorecard")
