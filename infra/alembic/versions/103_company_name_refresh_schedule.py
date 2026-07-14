"""Phase 2 — schedule nightly refresh_company_names.

Inserts a single job_schedule row so the worker tickloop runs the
company-name backfill/refresh handler at
`apps/worker/src/jobs/refresh_company_names.py`.

Cron: `30 5 * * *` (daily 05:30 in SCHEDULER_TZ) — after the nightly
price-ingest window. Idempotent handler (only fills NULL names) so the
exact slot is non-critical.

Strictly additive. Reversible.

Revision ID: 103_company_name_refresh_schedule
Revises: 102_portfolio_follow_fk
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "103_company_name_refresh"
down_revision = "102_portfolio_follow_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO job_schedule
              (id, name, cron_expr, enabled, created_at, updated_at)
            VALUES
              (gen_random_uuid()::text, 'refresh_company_names',
               '30 5 * * *', true, NOW(), NOW())
            ON CONFLICT (name) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM job_schedule WHERE name = 'refresh_company_names'")
    )
