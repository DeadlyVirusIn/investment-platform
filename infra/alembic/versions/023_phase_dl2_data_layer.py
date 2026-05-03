"""Phase DL2 — data-layer architecture tables.

Adds 4 new append-only tables for market/positioning observations,
features_daily, context_daily, decision_log.

Does NOT touch existing macro_series_observation, price_bar, earnings_event,
consensus_estimate, or any Phase 10/10.6 tables.

Revision ID: 023_phase_dl2_data_layer
Revises: 022_phase10_6_hardening
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY


revision = "023_phase_dl2_data_layer"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------
    # market_series_observation — daily close for market indices/assets
    # -----------------------------------------------------------------
    op.create_table(
        "market_series_observation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("series_id", sa.Text, nullable=False),
        sa.Column("observation_date", sa.Date, nullable=False),
        sa.Column("close_value", sa.Numeric(20, 6), nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.UniqueConstraint("source", "series_id", "as_of_date",
                            name="ux_market_series_source_id_date"),
    )
    op.create_index("ix_market_series_series_date", "market_series_observation",
                    ["series_id", "as_of_date"])

    # -----------------------------------------------------------------
    # positioning_observation — COT / GEX daily-or-weekly
    # -----------------------------------------------------------------
    op.create_table(
        "positioning_observation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("series_id", sa.Text, nullable=False),
        sa.Column("observation_date", sa.Date, nullable=False),
        sa.Column("value", sa.Numeric(24, 4), nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("report_type", sa.Text),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.UniqueConstraint("source", "series_id", "observation_date",
                            name="ux_positioning_source_id_date"),
    )
    op.create_index("ix_positioning_series_date", "positioning_observation",
                    ["series_id", "observation_date"])

    # -----------------------------------------------------------------
    # features_daily — computed features per trading day
    # -----------------------------------------------------------------
    op.create_table(
        "features_daily",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("feature_name", sa.Text, nullable=False),
        sa.Column("value", sa.Numeric(24, 8)),
        sa.Column("value_bool", sa.Boolean),
        sa.Column("input_hash", sa.Text, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("feature_version", sa.Text, nullable=False),
        sa.UniqueConstraint("as_of_date", "feature_name", "feature_version",
                            name="ux_features_daily_name_ver_date"),
    )
    op.create_index("ix_features_daily_name_date", "features_daily",
                    ["feature_name", "as_of_date"])

    # -----------------------------------------------------------------
    # context_daily — regime/context labels with status
    # -----------------------------------------------------------------
    op.create_table(
        "context_daily",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("context_name", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("value_bool", sa.Boolean, nullable=False),
        sa.Column("source_features", ARRAY(sa.Text), nullable=False),
        sa.Column("logic_version", sa.Text, nullable=False),
        sa.Column("logic_hash", sa.Text, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("as_of_date", "context_name", "logic_version",
                            name="ux_context_daily_name_ver_date"),
    )
    op.create_index("ix_context_daily_name_status_date", "context_daily",
                    ["context_name", "status", "as_of_date"])
    op.create_check_constraint(
        "ck_context_daily_status",
        "context_daily",
        "status IN ('production', 'candidate', 'diagnostic')",
    )

    # -----------------------------------------------------------------
    # decision_log — append-only audit trail
    # -----------------------------------------------------------------
    op.create_table(
        "decision_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("decision_ts", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("engine", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("instrument", sa.Text, nullable=False),
        sa.Column("inputs_used", JSONB, nullable=False),
        sa.Column("context_values", JSONB, nullable=False),
        sa.Column("decision_version", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("blocked_by", sa.Text),
        sa.Column("diagnostic_snapshot", JSONB),
    )
    op.create_index("ix_decision_log_as_of", "decision_log", ["as_of_date"])
    op.create_index("ix_decision_log_engine_date", "decision_log",
                    ["engine", "as_of_date"])
    op.create_check_constraint(
        "ck_decision_log_engine",
        "decision_log",
        "engine IN ('A', 'B', 'none')",
    )


def downgrade() -> None:
    op.drop_table("decision_log")
    op.drop_table("context_daily")
    op.drop_table("features_daily")
    op.drop_table("positioning_observation")
    op.drop_table("market_series_observation")
