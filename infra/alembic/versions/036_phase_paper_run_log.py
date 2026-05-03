"""Phase DAILY-VISIBILITY — paper_run_log table.

Revision ID: 036_phase_paper_run_log
Revises: 035_phase_alpha_exploratory
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "036_phase_paper_run_log"
down_revision = "035_phase_alpha_exploratory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_run_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_date", sa.Date, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="running"),
        sa.Column("decisions_evaluated", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("trades_opened", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("trades_closed", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("trades_skipped", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("exploratory_trades", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("strict_trades", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("blocked_by_gates",      sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("blocked_by_anomaly",    sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("blocked_by_data_quality", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("net_pnl_today", sa.Numeric(18, 4), nullable=True),
        sa.Column("nav_start",     sa.Numeric(18, 4), nullable=True),
        sa.Column("nav_end",       sa.Numeric(18, 4), nullable=True),
        sa.Column("summary",   sa.Text, nullable=True),
        sa.Column("warnings",  JSONB,   nullable=True),
        sa.Column("details",   JSONB,   nullable=True),
        sa.UniqueConstraint("run_date",
                              name="ux_paper_run_log_run_date"),
    )
    op.create_index("ix_paper_run_log_started",
                    "paper_run_log", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_paper_run_log_started", table_name="paper_run_log")
    op.drop_table("paper_run_log")
