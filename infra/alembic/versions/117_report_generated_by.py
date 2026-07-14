"""Research report agent provenance — research_report.generated_by (P7 D-scope).

One additive nullable column recording WHO authored a report version:
'agent:<name>' for gateway D-scope drafts (spec §4), the owner email for
human reports, NULL for legacy rows. The existing `provenance`
(generated|human) says HOW; `generated_by` says WHO — needed so the owner
console can show a draft's agent origin at review time (spec §3 D: drafts
land 'invisible until a human reviews', flagged agent-origin).

PROPOSED — ephemeral-validated only, NOT applied to dev/prod. Additive;
downgrade drops the column. No backfill.

Revision ID: 117_report_generated_by
Revises: 116_agent_jobs
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "117_report_generated_by"
down_revision = "116_agent_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_report",
        sa.Column("generated_by", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_report", "generated_by")
