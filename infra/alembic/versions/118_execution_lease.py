"""Execution lease — exactly-once guard across independent scheduler paths (P0-5).

Root cause (2026-07-11): auto_trader runs via TWO independent scheduled paths —
the tick-loop's atomic job_schedule claim (registry run_paper_trading) AND
supercronic's run_daily_loop.sh -> scripts.run_paper_daily. The latter bypasses
_claim_due_job entirely, so both fire and the ux_paper_trade_autotrader
idempotency constraint absorbs the collision (0 dup trades, but ERROR noise and
two real executions). The unique trade constraint is defense-in-depth, NOT the
scheduler solution.

`execution_lease` is a single-executor guard keyed by (job, logical window):
both paths must acquire the lease before running; the loser no-ops cleanly (no
ERROR, no duplicate attempt). Bounded lease/expiry gives crash recovery — a
holder that dies mid-run leaves an expired lease that the next attempt steals.
No global worker lock: the key is per (job, date), so unrelated jobs proceed.

PROPOSED — ephemeral-validated only, NOT applied to dev/prod. Additive.

Revision ID: 118_execution_lease
Revises: 117_report_generated_by
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "118_execution_lease"
down_revision = "117_report_generated_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_lease",
        # e.g. 'run_paper_trading:2026-07-11' — job + logical window
        sa.Column("lease_key", sa.String(128), primary_key=True),
        sa.Column("holder", sa.String(64), nullable=False),
        # fencing token (Kleppmann): monotonic generation, incremented on every
        # steal. A stale former holder's (holder, fence) no longer matches after
        # ownership changes, so it cannot continue writing.
        sa.Column("fence", sa.BigInteger, nullable=False, server_default="1"),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="held"),
        sa.CheckConstraint("status IN ('held','released')",
                           name="ck_execution_lease_status"),
    )
    op.create_index("ix_execution_lease_expires", "execution_lease",
                    ["status", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_execution_lease_expires", table_name="execution_lease")
    op.drop_table("execution_lease")
