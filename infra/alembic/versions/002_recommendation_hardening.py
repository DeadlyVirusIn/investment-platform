"""Recommendation hardening: snapshot_hash column + unique + outcome table.

Revision ID: 002
Revises: 001
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EQUITY_NUM = sa.Numeric(20, 6)


def upgrade() -> None:
    op.add_column(
        "recommendation",
        sa.Column("snapshot_hash", sa.String(32), nullable=True),
    )
    op.create_index(
        "ux_recommendation_snap",
        "recommendation",
        ["asset_id", "model_version", "snapshot_hash"],
        unique=True,
    )

    op.create_table(
        "recommendation_outcome",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "recommendation_id",
            sa.String(36),
            sa.ForeignKey("recommendation.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("price_at_recommendation", EQUITY_NUM, nullable=True),
        sa.Column("price_after_30d", EQUITY_NUM, nullable=True),
        sa.Column("price_after_90d", EQUITY_NUM, nullable=True),
        sa.Column("realized_30d_return", EQUITY_NUM, nullable=True),
        sa.Column("realized_90d_return", EQUITY_NUM, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_recommendation_outcome_rec",
        "recommendation_outcome",
        ["recommendation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendation_outcome_rec", "recommendation_outcome")
    op.drop_table("recommendation_outcome")
    op.drop_index("ux_recommendation_snap", "recommendation")
    op.drop_column("recommendation", "snapshot_hash")
