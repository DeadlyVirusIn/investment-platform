"""Phase ML-2.5 — historical replay tables.

Three separate tables so replay data NEVER mixes with real decision_log:
  * ml_replay_run       — one row per replay execution (config + status)
  * ml_replay_decision  — per-date per-symbol synthetic decision
  * ml_replay_outcome   — future labels per decision per horizon

Revision ID: 028_phase_ml25_replay
Revises: 027_phase_ml2_snapshot
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "028_phase_ml25_replay"
down_revision = "027_phase_ml2_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------- ml_replay_run -------------
    op.create_table(
        "ml_replay_run",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("replay_name", sa.Text, nullable=False),
        sa.Column("replay_version", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date",   sa.Date, nullable=False),
        sa.Column("universe", JSONB, nullable=False, server_default="[]"),
        sa.Column("engine_versions", JSONB, nullable=False,
                  server_default="{}"),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("provider_priority", JSONB, nullable=False,
                  server_default="[]"),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="pending"),
        sa.Column("warnings", JSONB, nullable=True),
        sa.Column("leakage_report", JSONB, nullable=True),
        sa.Column("summary", JSONB, nullable=True),
    )
    op.create_index(
        "ix_ml_replay_run_created",
        "ml_replay_run", ["created_at"],
    )
    op.create_index(
        "ix_ml_replay_run_status",
        "ml_replay_run", ["status"],
    )

    # ------------- ml_replay_decision -------------
    op.create_table(
        "ml_replay_decision",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("replay_run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("decision_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("engine", sa.Text, nullable=False),
        sa.Column("decision", sa.Text, nullable=False),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column("features", JSONB, nullable=False, server_default="{}"),
        sa.Column("data_quality", JSONB, nullable=True),
        sa.Column("catalyst", JSONB, nullable=True),
        sa.Column("regime", JSONB, nullable=True),
        sa.Column("anomaly", JSONB, nullable=True),
        sa.Column("advisory", JSONB, nullable=True),
        sa.Column("missing_features", JSONB, nullable=True),
        sa.Column("skip_reason", sa.Text, nullable=True),
        sa.Column("provenance", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_foreign_key(
        "fk_replay_decision_run",
        "ml_replay_decision", "ml_replay_run",
        ["replay_run_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index(
        "ix_replay_decision_run",
        "ml_replay_decision", ["replay_run_id"],
    )
    op.create_index(
        "ix_replay_decision_asof",
        "ml_replay_decision", ["as_of_date"],
    )
    op.create_index(
        "ix_replay_decision_symbol",
        "ml_replay_decision", ["symbol"],
    )

    # ------------- ml_replay_outcome -------------
    op.create_table(
        "ml_replay_outcome",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("replay_decision_id", UUID(as_uuid=True), nullable=False),
        sa.Column("label_horizon", sa.Integer, nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("exit_price",  sa.Numeric(18, 6), nullable=True),
        sa.Column("forward_return", sa.Numeric(12, 8), nullable=True),
        sa.Column("max_adverse",    sa.Numeric(12, 8), nullable=True),
        sa.Column("max_favorable",  sa.Numeric(12, 8), nullable=True),
        sa.Column("win_label", sa.Boolean, nullable=True),
        sa.Column("label_start_date", sa.Date, nullable=True),
        sa.Column("label_end_date",   sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_foreign_key(
        "fk_replay_outcome_decision",
        "ml_replay_outcome", "ml_replay_decision",
        ["replay_decision_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index(
        "ix_replay_outcome_decision",
        "ml_replay_outcome", ["replay_decision_id"],
    )
    op.create_index(
        "ix_replay_outcome_horizon",
        "ml_replay_outcome", ["label_horizon"],
    )


def downgrade() -> None:
    op.drop_index("ix_replay_outcome_horizon", table_name="ml_replay_outcome")
    op.drop_index("ix_replay_outcome_decision", table_name="ml_replay_outcome")
    op.drop_constraint("fk_replay_outcome_decision",
                       "ml_replay_outcome", type_="foreignkey")
    op.drop_table("ml_replay_outcome")

    op.drop_index("ix_replay_decision_symbol",
                  table_name="ml_replay_decision")
    op.drop_index("ix_replay_decision_asof",
                  table_name="ml_replay_decision")
    op.drop_index("ix_replay_decision_run",
                  table_name="ml_replay_decision")
    op.drop_constraint("fk_replay_decision_run",
                       "ml_replay_decision", type_="foreignkey")
    op.drop_table("ml_replay_decision")

    op.drop_index("ix_ml_replay_run_status", table_name="ml_replay_run")
    op.drop_index("ix_ml_replay_run_created", table_name="ml_replay_run")
    op.drop_table("ml_replay_run")
