"""Phase SYSTEM-ALPHA-2 — job audit table.

Adds job_run_log so every alpha_nightly execution is auditable without
flooding stdout. Keeps per-phase timing + counts for ops visibility.

Revision ID: 032_phase_alpha_activation
Revises: 031_phase_system_alpha
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "032_phase_alpha_activation"
down_revision = "031_phase_system_alpha"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_run_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_name", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="running"),
        sa.Column("dry_run", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("phases", JSONB, nullable=True),
        sa.Column("summary", JSONB, nullable=True),
        sa.Column("warnings", JSONB, nullable=True),
        sa.Column("errors", JSONB, nullable=True),
    )
    op.create_index("ix_job_run_log_job", "job_run_log", ["job_name"])
    op.create_index("ix_job_run_log_started",
                    "job_run_log", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_job_run_log_started", table_name="job_run_log")
    op.drop_index("ix_job_run_log_job", table_name="job_run_log")
    op.drop_table("job_run_log")
