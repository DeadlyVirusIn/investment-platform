"""Phase 1 closed-loop foundation — signal + signal_outcome tables.

Revision ID: 018
Revises: 017
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- signal (write target for future model adapters) --------------------
    op.create_table(
        "signal",
        sa.Column("signal_id", sa.String(36), primary_key=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "asset_id", sa.String(36),
            sa.ForeignKey("asset.id"), nullable=False,
        ),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False, server_default="1d"),
        sa.Column("strategy_id", sa.String(64), nullable=False),
        sa.Column("model_family", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("features_version", sa.String(32), nullable=False),
        sa.Column("signal_direction", sa.String(8), nullable=False),   # long|short|neutral
        sa.Column("signal_strength", sa.Numeric(6, 4), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False),
        sa.Column("expected_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("expected_drawdown", sa.Numeric(10, 6), nullable=True),
        sa.Column("holding_period_bars", sa.Integer(), nullable=False),
        sa.Column("risk_score", sa.Numeric(6, 4), nullable=True),
        sa.Column("regime_tag", sa.String(24), nullable=True),
        sa.Column("raw_payload_ref", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "signal_direction IN ('long', 'short', 'neutral')",
            name="ck_signal_direction",
        ),
    )
    op.create_index(
        "ux_signal_dedup", "signal",
        ["as_of_date", "asset_id", "strategy_id"], unique=True,
    )
    op.create_index("ix_signal_as_of_date", "signal", ["as_of_date"])
    op.create_index("ix_signal_strategy", "signal", ["strategy_id"])

    # ---- signal_outcome (write-only in Phase 1) -----------------------------
    op.create_table(
        "signal_outcome",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "signal_id", sa.String(36),
            sa.ForeignKey("signal.signal_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_direction", sa.String(8), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("realized_return", sa.Numeric(10, 6), nullable=False),
        sa.Column("max_drawdown", sa.Numeric(10, 6), nullable=True),
        sa.Column("outcome_label", sa.String(16), nullable=False),
        sa.Column("evaluation_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "outcome_label IN ('win', 'loss', 'breakeven', 'timeout')",
            name="ck_outcome_label",
        ),
        sa.CheckConstraint(
            "signal_direction IN ('long', 'short', 'neutral')",
            name="ck_outcome_direction",
        ),
    )
    op.create_index(
        "ux_signal_outcome_signal", "signal_outcome", ["signal_id"], unique=True,
    )
    op.create_index(
        "ix_signal_outcome_eval_ts", "signal_outcome", ["evaluation_timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_signal_outcome_eval_ts", table_name="signal_outcome")
    op.drop_index("ux_signal_outcome_signal", table_name="signal_outcome")
    op.drop_table("signal_outcome")
    op.drop_index("ix_signal_strategy", table_name="signal")
    op.drop_index("ix_signal_as_of_date", table_name="signal")
    op.drop_index("ux_signal_dedup", table_name="signal")
    op.drop_table("signal")
