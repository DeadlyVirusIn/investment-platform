"""Stock engine Batch 1: universe_membership (point-in-time membership).

Revision ID: 008
Revises: 007
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "universe_membership",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("universe_name", sa.String(64), nullable=False),
        sa.Column(
            "asset_id",
            sa.String(36),
            sa.ForeignKey("asset.id"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_um_universe_asset",
        "universe_membership",
        ["universe_name", "asset_id"],
    )
    op.create_index(
        "ix_um_universe_active",
        "universe_membership",
        ["universe_name", "end_date"],
    )
    # Partial unique index: at most one open row per (universe, asset).
    op.create_index(
        "ux_um_open_member",
        "universe_membership",
        ["universe_name", "asset_id"],
        unique=True,
        postgresql_where=sa.text("end_date IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_um_open_member", table_name="universe_membership")
    op.drop_index("ix_um_universe_active", table_name="universe_membership")
    op.drop_index("ix_um_universe_asset", table_name="universe_membership")
    op.drop_table("universe_membership")
