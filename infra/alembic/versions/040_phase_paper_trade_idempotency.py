"""Phase OPS-IDEMPOTENCY — paper_trade_log natural-key constraint.

Adds a partial unique constraint so that at most ONE open trade exists
per (portfolio_id, entry_date, instrument, engine, action). This lets
the runner use ON CONFLICT DO NOTHING to make --force-recompute safe.

Deliberately PARTIAL on status='open' so a historical closed trade
cannot block a new entry later in the day with the same attributes.
Closed trades accumulate freely.

Revision ID: 040_paper_trade_idempotent
Revises: 039_phase_ml5_hybrid_snapshot
"""

from __future__ import annotations

from alembic import op


revision = "040_paper_trade_idempotent"
down_revision = "039_phase_ml5_hybrid_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # First clean any existing duplicates (defensive — should be none on
    # production data but keep idempotent DDL).
    op.execute("""
        DELETE FROM paper_trade_log a
        USING paper_trade_log b
        WHERE a.ctid < b.ctid
          AND a.portfolio_id = b.portfolio_id
          AND a.entry_date   = b.entry_date
          AND a.instrument   = b.instrument
          AND a.engine       = b.engine
          AND a.action       = b.action
          AND a.status       = 'open'
          AND b.status       = 'open'
    """)
    # Partial unique index: only one OPEN row per key.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
            uq_paper_trade_open_key
        ON paper_trade_log
            (portfolio_id, entry_date, instrument, engine, action)
        WHERE status = 'open'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_paper_trade_open_key")
