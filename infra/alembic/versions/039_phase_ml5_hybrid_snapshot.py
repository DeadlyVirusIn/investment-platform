"""Phase ML-6 — hybrid performance snapshot table.

Revision ID: 039_phase_ml5_hybrid_snapshot
Revises: 038_phase_alpha_context
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "039_phase_ml5_hybrid_snapshot"
down_revision = "038_phase_alpha_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_hybrid_performance_snapshot",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("window_days", sa.Integer, nullable=False),
        sa.Column("mode", sa.Text, nullable=False,
                  server_default="advisory"),
        # Counts
        sa.Column("ml_advice_count",       sa.Integer,
                  nullable=False, server_default="0"),
        sa.Column("ml_reduce_count",       sa.Integer,
                  nullable=False, server_default="0"),
        sa.Column("ml_avoid_count",        sa.Integer,
                  nullable=False, server_default="0"),
        sa.Column("ml_eligible_count",     sa.Integer,
                  nullable=False, server_default="0"),
        sa.Column("ml_gated_count",        sa.Integer,
                  nullable=False, server_default="0"),
        sa.Column("deterministic_trades",  sa.Integer,
                  nullable=False, server_default="0"),
        sa.Column("ml_agreement_count",    sa.Integer,
                  nullable=False, server_default="0"),
        sa.Column("ml_disagreement_count", sa.Integer,
                  nullable=False, server_default="0"),
        # Estimates + rates
        sa.Column("avoided_loss_estimate",       sa.Numeric(12, 4),
                  nullable=True),
        sa.Column("missed_winner_estimate",      sa.Numeric(12, 4),
                  nullable=True),
        sa.Column("false_avoid_rate",            sa.Numeric(6, 4),
                  nullable=True),
        sa.Column("missed_winner_rate",          sa.Numeric(6, 4),
                  nullable=True),
        sa.Column("good_warning_rate",           sa.Numeric(6, 4),
                  nullable=True),
        sa.Column("avg_return_when_ml_agreed",     sa.Numeric(10, 4),
                  nullable=True),
        sa.Column("avg_return_when_ml_warned",     sa.Numeric(10, 4),
                  nullable=True),
        sa.Column("avg_return_when_ml_unavailable", sa.Numeric(10, 4),
                  nullable=True),
        sa.Column("delta_sharpe_vs_deterministic", sa.Numeric(10, 4),
                  nullable=True),
        # Model health
        sa.Column("calibration_ece",  sa.Numeric(10, 6), nullable=True),
        sa.Column("brier_score",      sa.Numeric(10, 6), nullable=True),
        sa.Column("model_status",     sa.Text, nullable=True),
        # Promotion
        sa.Column("promotion_status", sa.Text, nullable=False,
                  server_default="NOT_READY_NO_ML"),
        sa.Column("blockers",         JSONB, nullable=False,
                  server_default="[]"),
        sa.Column("recommendation",   sa.Text, nullable=True),
        sa.Column("metrics",          JSONB, nullable=False,
                  server_default="{}"),
    )
    op.create_index(
        "ix_ml_hybrid_perf_date",
        "ml_hybrid_performance_snapshot",
        ["as_of_date"],
    )
    op.create_index(
        "ix_ml_hybrid_perf_window",
        "ml_hybrid_performance_snapshot",
        ["as_of_date", "window_days"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ml_hybrid_perf_window",
        table_name="ml_hybrid_performance_snapshot",
    )
    op.drop_index(
        "ix_ml_hybrid_perf_date",
        table_name="ml_hybrid_performance_snapshot",
    )
    op.drop_table("ml_hybrid_performance_snapshot")
