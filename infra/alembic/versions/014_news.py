"""News Intelligence Layer: news_item + news_symbol_map.

Revision ID: 014
Revises: 013
Create Date: 2026-04-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_item",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.String(40), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("sentiment", sa.String(16), nullable=False),
        sa.Column("sentiment_score", sa.Numeric(6, 3), nullable=False),
        sa.Column("impact_level", sa.String(8), nullable=False),
        sa.Column("impact_score", sa.Integer(), nullable=False),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ux_news_url_hash", "news_item", ["url_hash"], unique=True)
    op.create_index(
        "ix_news_published_at", "news_item", [sa.text("published_at DESC")],
    )
    op.create_index("ix_news_category", "news_item", ["category"])

    op.create_table(
        "news_symbol_map",
        sa.Column(
            "news_id",
            sa.String(36),
            sa.ForeignKey("news_item.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("symbol", sa.String(32), primary_key=True),
    )
    op.create_index(
        "ix_news_symbol_map_symbol", "news_symbol_map", ["symbol"],
    )


def downgrade() -> None:
    op.drop_index("ix_news_symbol_map_symbol", table_name="news_symbol_map")
    op.drop_table("news_symbol_map")
    op.drop_index("ix_news_category", table_name="news_item")
    op.drop_index("ix_news_published_at", table_name="news_item")
    op.drop_index("ux_news_url_hash", table_name="news_item")
    op.drop_table("news_item")
