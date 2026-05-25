"""Phase 2 stock fix Phase 5 — schedule run_paper_exit_cycle daily.

Inserts a single job_schedule row for `run_paper_exit_cycle` so the
worker tickloop picks up the worker wrapper at
`apps/worker/src/jobs/run_paper_exit_cycle.py`.

Cron: `0 23 * * 1-5` interpreted in SCHEDULER_TZ
(America/New_York) → 23:00 ET = 03:00 UTC next day. Slots between
`ingest_prices_daily` (~02:00 UTC) and `run_paper_trading`
(03:30 UTC) so exits free slots before new opens are evaluated.

Paper-only. Next-bar fill guard preserved by `submit_trade`. The
worker wrapper programmatically satisfies the CONFIRM_ENV gate; ad-hoc
CLI invocations still require manual env-var set.

Strictly additive. Reversible.

Revision ID: 071_paper_exit_cycle_schedule
Revises: 070_paper_execution_funnel
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "071_paper_exit_cycle_schedule"
down_revision = "070_paper_execution_funnel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO job_schedule
              (id, name, cron_expr, enabled, created_at, updated_at)
            VALUES
              (gen_random_uuid()::text, 'run_paper_exit_cycle',
               '0 23 * * 1-5', true, NOW(), NOW())
            ON CONFLICT (name) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM job_schedule WHERE name = 'run_paper_exit_cycle'"
        )
    )
