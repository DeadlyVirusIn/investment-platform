"""action_item table — decision UX v1.

Revision ID: 017
Revises: 016
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "action_item",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column(
            "asset_id", sa.String(36),
            sa.ForeignKey("asset.id"), nullable=False,
        ),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("sector", sa.String(32), nullable=True),
        sa.Column(
            "candidate_id", sa.String(36),
            sa.ForeignKey("candidate_idea.id"), nullable=True,
        ),
        sa.Column("priority", sa.Numeric(5, 2), nullable=False),
        sa.Column("priority_tier", sa.String(8), nullable=False),
        sa.Column("urgency", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("composite_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("rationale_short", sa.Text(), nullable=False),
        sa.Column("factor_top", JSONB, nullable=True),
        sa.Column("impact_estimate", JSONB, nullable=True),
        sa.Column("decay_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dependencies", JSONB, nullable=False, server_default="{}"),
        sa.Column("origin", sa.String(24), nullable=False),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="pending",
        ),
        sa.Column(
            "acted_trade_id", sa.String(36),
            sa.ForeignKey("paper_trade.id"), nullable=True,
        ),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismiss_reason", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_action_status_priority", "action_item",
        ["status", sa.text("priority DESC")],
    )
    op.create_index(
        "ix_action_asof_kind", "action_item", ["as_of_date", "kind"],
    )
    op.create_index(
        "ix_action_asset", "action_item", ["asset_id", "status"],
    )
    op.create_index(
        "ux_action_dedup", "action_item",
        ["as_of_date", "asset_id", "kind", "origin"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_action_dedup", table_name="action_item")
    op.drop_index("ix_action_asset", table_name="action_item")
    op.drop_index("ix_action_asof_kind", table_name="action_item")
    op.drop_index("ix_action_status_priority", table_name="action_item")
    op.drop_table("action_item")
