"""Phase MON1 — anomaly_event table.

Revision ID: 025_phase_mon1_anomaly_events
Revises: 024_phase_ops1_paper_trading
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "025_phase_mon1_anomaly_events"
down_revision = "024_phase_ops1_paper_trading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anomaly_event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("rule_key", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("related_engine", sa.Text),
        sa.Column("related_trade_id", UUID(as_uuid=True)),
        sa.Column("related_decision_id", UUID(as_uuid=True)),
        sa.Column("metrics_snapshot", JSONB, nullable=False,
                  server_default="{}"),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("as_of_date", "rule_key", "related_trade_id",
                            name="ux_anomaly_date_rule_trade"),
    )
    op.create_index("ix_anomaly_date_status", "anomaly_event",
                    ["as_of_date", "status"])
    op.create_index("ix_anomaly_severity_status", "anomaly_event",
                    ["severity", "status"])
    op.create_check_constraint(
        "ck_anomaly_severity", "anomaly_event",
        "severity IN ('info', 'warning', 'critical')",
    )
    op.create_check_constraint(
        "ck_anomaly_status", "anomaly_event",
        "status IN ('open', 'acknowledged', 'resolved')",
    )
    op.create_check_constraint(
        "ck_anomaly_category", "anomaly_event",
        "category IN ('decision', 'trade', 'regime', 'data', 'shadow')",
    )


def downgrade() -> None:
    op.drop_table("anomaly_event")
