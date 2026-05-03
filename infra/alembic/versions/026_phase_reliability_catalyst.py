"""Phase reliability + catalyst — extend decision_log + paper_trade_log.

Adds columns so every decision carries:
  * data_quality (JSONB)  — missing/stale/degraded features + confidence
  * catalyst (JSONB)      — catalyst summary at decision time
  * feature_confidence    — roll-up 0..1
  * skip_reason           — plain-text reason if engine skipped

All columns nullable so existing rows remain valid.

Revision ID: 026_phase_reliability_catalyst
Revises: 025_phase_mon1_anomaly_events
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "026_phase_reliability_catalyst"
down_revision = "025_phase_mon1_anomaly_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------- decision_log -------------
    op.add_column("decision_log",
        sa.Column("data_quality", JSONB, nullable=True))
    op.add_column("decision_log",
        sa.Column("catalyst", JSONB, nullable=True))
    op.add_column("decision_log",
        sa.Column("feature_confidence", sa.Numeric(6, 4), nullable=True))
    op.add_column("decision_log",
        sa.Column("skip_reason", sa.Text, nullable=True))
    op.add_column("decision_log",
        sa.Column("missing_features", JSONB, nullable=True))

    op.create_index(
        "ix_decision_log_feature_confidence",
        "decision_log", ["feature_confidence"],
    )

    # ------------- paper_trade_log -------------
    op.add_column("paper_trade_log",
        sa.Column("catalyst_snapshot", JSONB, nullable=True))
    op.add_column("paper_trade_log",
        sa.Column("data_confidence", sa.Numeric(6, 4), nullable=True))
    op.add_column("paper_trade_log",
        sa.Column("near_earnings", sa.Boolean, nullable=True,
                  server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("paper_trade_log", "near_earnings")
    op.drop_column("paper_trade_log", "data_confidence")
    op.drop_column("paper_trade_log", "catalyst_snapshot")

    op.drop_index("ix_decision_log_feature_confidence", table_name="decision_log")
    op.drop_column("decision_log", "missing_features")
    op.drop_column("decision_log", "skip_reason")
    op.drop_column("decision_log", "feature_confidence")
    op.drop_column("decision_log", "catalyst")
    op.drop_column("decision_log", "data_quality")
