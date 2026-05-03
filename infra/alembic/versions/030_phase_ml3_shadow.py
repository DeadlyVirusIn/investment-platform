"""Phase ML-3 — passive shadow ML tables.

Two separate tables so shadow predictions never mix with production
decisions:
  * ml_model_run         — one row per training run (even skipped ones)
  * ml_shadow_prediction — one row per scored decision (real or replay)

Revision ID: 030_phase_ml3_shadow
Revises: 029_phase_ml26_backfill_fields
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "030_phase_ml3_shadow"
down_revision = "029_phase_ml26_backfill_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------- ml_model_run -------------
    op.create_table(
        "ml_model_run",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("run_name",   sa.Text, nullable=False),
        sa.Column("model_type", sa.Text, nullable=False,
                  server_default="logistic"),
        sa.Column("dataset_source", sa.Text, nullable=False,
                  server_default="real"),
        sa.Column("train_start_date", sa.Date, nullable=True),
        sa.Column("train_end_date",   sa.Date, nullable=True),
        sa.Column("test_start_date",  sa.Date, nullable=True),
        sa.Column("test_end_date",    sa.Date, nullable=True),
        sa.Column("row_count",         sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("labeled_row_count", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("feature_list",      JSONB, nullable=False,
                  server_default="[]"),
        sa.Column("label_target", sa.Text, nullable=False,
                  server_default="label_win_5d"),
        sa.Column("horizon",      sa.Integer, nullable=False,
                  server_default="5"),
        sa.Column("hyperparams",  JSONB, nullable=False, server_default="{}"),
        sa.Column("metrics",      JSONB, nullable=True),
        sa.Column("baseline_comparison", JSONB, nullable=True),
        sa.Column("leakage_report",      JSONB, nullable=True),
        sa.Column("feature_health",      JSONB, nullable=True),
        sa.Column("calibration",         JSONB, nullable=True),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="skipped"),
        sa.Column("blockers", JSONB, nullable=True),
        sa.Column("artifact_path", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_ml_model_run_created",
                    "ml_model_run", ["created_at"])
    op.create_index("ix_ml_model_run_status",
                    "ml_model_run", ["status"])

    # ------------- ml_shadow_prediction -------------
    op.create_table(
        "ml_shadow_prediction",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("model_run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("decision_id",        UUID(as_uuid=True), nullable=True),
        sa.Column("replay_decision_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.Text, nullable=False,
                  server_default="real"),
        sa.Column("symbol",      sa.Text, nullable=False),
        sa.Column("as_of_date",  sa.Date, nullable=False),
        sa.Column("decision_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engine",      sa.Text, nullable=True),
        sa.Column("original_decision",  sa.Text, nullable=True),
        sa.Column("engine_confidence",  sa.Numeric(6, 4), nullable=True),
        sa.Column("ml_score",           sa.Numeric(6, 4), nullable=False,
                  server_default="0.5"),
        sa.Column("ml_confidence",      sa.Numeric(6, 4), nullable=False,
                  server_default="0"),
        sa.Column("ml_action", sa.Text, nullable=False,
                  server_default="needs_more_data"),
        sa.Column("ml_reason_codes", JSONB, nullable=True),
        sa.Column("baseline_action", sa.Text, nullable=True),
        sa.Column("actual_outcome",  sa.Numeric(12, 6), nullable=True),
        sa.Column("outcome_available", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("evaluation", JSONB, nullable=True),
    )
    op.create_foreign_key(
        "fk_shadow_prediction_model_run",
        "ml_shadow_prediction", "ml_model_run",
        ["model_run_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_shadow_prediction_model",
                    "ml_shadow_prediction", ["model_run_id"])
    op.create_index("ix_shadow_prediction_symbol_date",
                    "ml_shadow_prediction", ["symbol", "as_of_date"])
    op.create_index("ix_shadow_prediction_decision",
                    "ml_shadow_prediction", ["decision_id"])


def downgrade() -> None:
    op.drop_index("ix_shadow_prediction_decision",
                  table_name="ml_shadow_prediction")
    op.drop_index("ix_shadow_prediction_symbol_date",
                  table_name="ml_shadow_prediction")
    op.drop_index("ix_shadow_prediction_model",
                  table_name="ml_shadow_prediction")
    op.drop_constraint("fk_shadow_prediction_model_run",
                        "ml_shadow_prediction", type_="foreignkey")
    op.drop_table("ml_shadow_prediction")

    op.drop_index("ix_ml_model_run_status", table_name="ml_model_run")
    op.drop_index("ix_ml_model_run_created", table_name="ml_model_run")
    op.drop_table("ml_model_run")
