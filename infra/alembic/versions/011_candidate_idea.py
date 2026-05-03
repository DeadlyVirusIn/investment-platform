"""Stock engine Batch 4: candidate_idea (per-asset daily evaluation log).

Revision ID: 011
Revises: 010
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EQUITY_NUM = sa.Numeric(20, 6)


def upgrade() -> None:
    op.create_table(
        "candidate_idea",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "asset_id",
            sa.String(36),
            sa.ForeignKey("asset.id"),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column(
            "engine",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'stock_swing'"),
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("action", sa.String(16), nullable=True),
        sa.Column("rejection_reason", sa.String(64), nullable=True),
        sa.Column("composite_score", EQUITY_NUM, nullable=True),
        sa.Column("confidence", EQUITY_NUM, nullable=True),
        sa.Column(
            "factor_breakdown", JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "regime_snapshot", JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("recommendation_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "(status = 'accepted' AND action IS NOT NULL) OR "
            "(status = 'rejected' AND rejection_reason IS NOT NULL)",
            name="ck_candidate_status_fields",
        ),
    )
    op.create_index(
        "ux_candidate_idea",
        "candidate_idea",
        ["as_of_date", "asset_id", "model_version"],
        unique=True,
    )
    op.create_index(
        "ix_candidate_status",
        "candidate_idea",
        ["as_of_date", "status"],
    )
    op.create_index(
        "ix_candidate_reject",
        "candidate_idea",
        ["rejection_reason"],
        postgresql_where=sa.text("status = 'rejected'"),
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_reject", table_name="candidate_idea")
    op.drop_index("ix_candidate_status", table_name="candidate_idea")
    op.drop_index("ux_candidate_idea", table_name="candidate_idea")
    op.drop_table("candidate_idea")
