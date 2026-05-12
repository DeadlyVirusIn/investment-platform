"""Phase 15i.A — pipeline_run ledger (truth-infrastructure only).

Creates the canonical operational truth ledger for the daily
pipeline. One row per (trading_date, stage, run_id). The ledger
groups all stages of a single orchestrator pass under a shared
`run_id` UUID, captures input/output watermarks, and supports
caller-supplied idempotency keys.

This migration is STRICTLY ADDITIVE:
  * No ALTER on any existing table.
  * No DROP, no rename of any existing object.
  * No data migration.
  * `downgrade()` cleanly drops the new table and its indexes.

Nothing in production currently writes to this table. The ORM
class `PipelineRun` exposes write capability so future
orchestrator code (Phase 15i.B) can populate rows without a
further schema change. The Phase 15i.C `/api/freshness` endpoint
is read-only against this ledger plus existing source-of-truth
tables (`recommendation`, `paper_run_log`, `paper_equity_snapshot`,
`ml_model_run`, `options_chain_snapshot`).

Revision ID: 065_pipeline_run_ledger
Revises: 064_agent_insight_cache
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "065_pipeline_run_ledger"
down_revision = "064_agent_insight_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_run",
        sa.Column(
            "id", sa.BigInteger,
            primary_key=True, autoincrement=True,
        ),
        sa.Column(
            "run_id", UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("trading_date", sa.Date, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "finished_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("duration_ms", sa.BigInteger, nullable=True),
        sa.Column("triggered_by", sa.Text, nullable=True),
        sa.Column(
            "retry_count", sa.Integer,
            nullable=False, server_default="0",
        ),
        sa.Column("error_class", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "input_watermark", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "output_watermark", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("rows_read", sa.BigInteger, nullable=True),
        sa.Column("rows_written", sa.BigInteger, nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=True),
        sa.Column(
            "metadata", JSONB,
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
    )

    # Uniqueness: one row per (trading_date, stage, run_id). The same
    # stage can be retried by issuing a new run_id.
    op.create_index(
        "uq_pipeline_run_trading_stage_runid",
        "pipeline_run",
        ["trading_date", "stage", "run_id"],
        unique=True,
    )

    # Idempotency dedup — partial unique index on non-null keys only.
    op.create_index(
        "uq_pipeline_run_idempotency",
        "pipeline_run",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # Query indexes.
    op.create_index(
        "ix_pipeline_run_trading_date",
        "pipeline_run",
        [sa.text("trading_date DESC")],
    )
    op.create_index(
        "ix_pipeline_run_stage_status",
        "pipeline_run",
        ["stage", "status"],
    )
    op.create_index(
        "ix_pipeline_run_run_id",
        "pipeline_run",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pipeline_run_run_id", table_name="pipeline_run",
    )
    op.drop_index(
        "ix_pipeline_run_stage_status", table_name="pipeline_run",
    )
    op.drop_index(
        "ix_pipeline_run_trading_date", table_name="pipeline_run",
    )
    op.drop_index(
        "uq_pipeline_run_idempotency", table_name="pipeline_run",
    )
    op.drop_index(
        "uq_pipeline_run_trading_stage_runid",
        table_name="pipeline_run",
    )
    op.drop_table("pipeline_run")
