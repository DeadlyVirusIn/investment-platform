"""Phase ENGINE-B-MIGRATION — paper_shadow_log B-vs-B2 columns.

Adds columns required for shadow comparison logging:
  - engine_b_signal       (LONG | FLAT | NULL)
  - b2_signal             (LONG | FLAT | NULL)
  - divergence_flag       (boolean — True if B and B2 disagree)
  - divergence_outcome    (numeric — realized fwd_ret_1d under B minus
                           realized fwd_ret_1d under B2; sign-aware)
  - mode_at_decision      (text — captured ENGINE_B_MODE at decision time)
  - routed_signal         (LONG | FLAT — what the router actually picked)

Idempotent (uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS).
NEVER touches paper_trade_log, decision_log, or production execution.

Revision ID: 042_engine_b_migration_columns
Revises: 041_phase_shadow_log
"""

from __future__ import annotations

from alembic import op


revision = "042_engine_b_migration_columns"
down_revision = "041_phase_shadow_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE paper_shadow_log
            ADD COLUMN IF NOT EXISTS engine_b_signal     TEXT,
            ADD COLUMN IF NOT EXISTS b2_signal           TEXT,
            ADD COLUMN IF NOT EXISTS divergence_flag     BOOLEAN
                NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS divergence_outcome  NUMERIC(12, 8),
            ADD COLUMN IF NOT EXISTS mode_at_decision    TEXT,
            ADD COLUMN IF NOT EXISTS routed_signal       TEXT
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_paper_shadow_divergence
            ON paper_shadow_log (divergence_flag, as_of_date)
            WHERE divergence_flag IS TRUE
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_paper_shadow_divergence")
    op.execute("""
        ALTER TABLE paper_shadow_log
            DROP COLUMN IF EXISTS engine_b_signal,
            DROP COLUMN IF EXISTS b2_signal,
            DROP COLUMN IF EXISTS divergence_flag,
            DROP COLUMN IF EXISTS divergence_outcome,
            DROP COLUMN IF EXISTS mode_at_decision,
            DROP COLUMN IF EXISTS routed_signal
    """)
