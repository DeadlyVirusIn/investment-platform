"""Phase 1.5 — ranked_signal (proper migration) + shadow_run_log.

Revision ID: 020
Revises: 019
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the shadow table if it was created by the lazy create_all() path.
    op.execute("DROP TABLE IF EXISTS ranked_signal CASCADE")

    # ---- ranked_signal (canonical) ------------------------------------------
    op.create_table(
        "ranked_signal",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("score", sa.Numeric(10, 6), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.String(64), nullable=False),
        sa.Column("contributing_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_ranked_signal_as_of_date", "ranked_signal", ["as_of_date"],
    )
    op.create_index(
        "ix_ranked_signal_score", "ranked_signal", [sa.text("score DESC")],
    )
    op.create_index(
        "ux_ranked_signal_dedup", "ranked_signal",
        ["as_of_date", "strategy_id", "rank_position"], unique=True,
    )

    # ---- shadow_run_log -----------------------------------------------------
    op.create_table(
        "shadow_run_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("signals_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ranked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runtime_ms", sa.Integer(), nullable=True),
        sa.Column("diff_status", sa.String(16), nullable=True),   # ok | fail | not_run
        sa.Column("diff_reason", sa.String(64), nullable=True),
        sa.Column("reorder_count", sa.Integer(), nullable=True),
        sa.Column("asset_set_match", sa.Boolean(), nullable=True),
        sa.Column("topn_match", sa.Boolean(), nullable=True),
        sa.Column("max_score_delta", sa.Numeric(10, 6), nullable=True),
        sa.Column("failing_symbols", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_shadow_run_log_as_of_date", "shadow_run_log", ["as_of_date"],
    )
    op.create_index(
        "ux_shadow_run_log_day", "shadow_run_log",
        ["as_of_date"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_shadow_run_log_day", table_name="shadow_run_log")
    op.drop_index("ix_shadow_run_log_as_of_date", table_name="shadow_run_log")
    op.drop_table("shadow_run_log")
    op.drop_index("ux_ranked_signal_dedup", table_name="ranked_signal")
    op.drop_index("ix_ranked_signal_score", table_name="ranked_signal")
    op.drop_index("ix_ranked_signal_as_of_date", table_name="ranked_signal")
    op.drop_table("ranked_signal")
