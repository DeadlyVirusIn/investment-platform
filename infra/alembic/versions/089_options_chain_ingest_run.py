"""Phase Opt-Prep — options chain ingest run telemetry.

Adds `options_chain_ingest_run` as the telemetry-of-truth table for
chain ingest jobs. One row per invocation regardless of outcome.

Mirror of `envelope_generation_run` from stocks side (M084).

Revision ID: 089_opt_chain_ingest_run
Revises: 088_phase_l_reasoning_qual_v2
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "089_opt_chain_ingest_run"
down_revision = "088_phase_l_reasoning_qual_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "options_chain_ingest_run",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column(
            "universe",
            sa.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("rows_inserted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rows_dedup", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "rows_filtered_out",
            sa.Integer, nullable=False, server_default="0",
        ),
        sa.Column("n_symbols_ok", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "n_symbols_partial",
            sa.Integer, nullable=False, server_default="0",
        ),
        sa.Column(
            "n_symbols_error",
            sa.Integer, nullable=False, server_default="0",
        ),
        sa.Column(
            "classification",
            sa.Text,
            nullable=False,
            # 'success' | 'partial' | 'no_new_data' | 'error' | 'flags_off'
        ),
        sa.Column(
            "error_summary",
            sa.dialects.postgresql.JSONB,
            nullable=True,
        ),
        sa.Column("duration_sec", sa.Numeric(8, 3), nullable=True),
    )
    op.create_index(
        "ix_opt_chain_ingest_run_started",
        "options_chain_ingest_run",
        ["started_at"],
    )
    op.create_index(
        "ix_opt_chain_ingest_run_class",
        "options_chain_ingest_run",
        ["classification", "started_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opt_chain_ingest_run_class",
        table_name="options_chain_ingest_run",
    )
    op.drop_index(
        "ix_opt_chain_ingest_run_started",
        table_name="options_chain_ingest_run",
    )
    op.drop_table("options_chain_ingest_run")
