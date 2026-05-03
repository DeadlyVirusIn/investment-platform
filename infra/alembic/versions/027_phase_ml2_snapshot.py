"""Phase ML-2 — ml_research_snapshot table + decision_log advisory cols.

Adds:
  * ml_research_snapshot  — nightly diagnostic record
  * decision_log.ml_advisory       JSONB (optional advisory annotation)
  * decision_log.baseline_advisory JSONB (optional baseline rec)
  * decision_log.pattern_flags     JSONB (optional pattern tags)

All decision_log additions nullable → advisory-only, never affects exec.

Revision ID: 027_phase_ml2_snapshot
Revises: 026_phase_reliability_catalyst
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "027_phase_ml2_snapshot"
down_revision = "026_phase_reliability_catalyst"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_research_snapshot",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("row_count", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("labeled_row_count", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("symbol_count", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("date_start", sa.Date, nullable=True),
        sa.Column("date_end",   sa.Date, nullable=True),
        sa.Column("tier", sa.Text, nullable=False,
                  server_default="diagnostics_only"),
        sa.Column("leakage_clean", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("leakage_report",   JSONB, nullable=True),
        sa.Column("feature_health",   JSONB, nullable=True),
        sa.Column("baseline_results", JSONB, nullable=True),
        sa.Column("patterns",         JSONB, nullable=True),
        sa.Column("engine_c_status",  JSONB, nullable=True),
        sa.Column("warnings",         JSONB, nullable=True),
        sa.Column("recommendation",   sa.Text, nullable=True),
    )
    op.create_index(
        "ix_ml_research_snapshot_asof",
        "ml_research_snapshot", ["as_of_date"],
    )
    op.create_index(
        "ix_ml_research_snapshot_created",
        "ml_research_snapshot", ["created_at"],
    )

    # decision_log advisory annotations (never used to affect execution)
    op.add_column("decision_log",
        sa.Column("ml_advisory", JSONB, nullable=True))
    op.add_column("decision_log",
        sa.Column("baseline_advisory", JSONB, nullable=True))
    op.add_column("decision_log",
        sa.Column("pattern_flags", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("decision_log", "pattern_flags")
    op.drop_column("decision_log", "baseline_advisory")
    op.drop_column("decision_log", "ml_advisory")

    op.drop_index("ix_ml_research_snapshot_created",
                  table_name="ml_research_snapshot")
    op.drop_index("ix_ml_research_snapshot_asof",
                  table_name="ml_research_snapshot")
    op.drop_table("ml_research_snapshot")
