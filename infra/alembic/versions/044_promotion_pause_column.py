"""Phase ENGINE-B-PAUSE — promotion_pause JSONB column.

Adds promotion_pause JSONB to engine_b_decision_snapshot for clean
storage of governance-pause state (active, severity, reason, metrics,
clear_condition, label_override).

Idempotent (ADD COLUMN IF NOT EXISTS). Read-only impact on prior rows.

Revision ID: 044_promotion_pause_column
Revises: 043_engine_b_decision_snapshot
"""

from __future__ import annotations

from alembic import op


revision = "044_promotion_pause_column"
down_revision = "043_engine_b_decision_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE engine_b_decision_snapshot
            ADD COLUMN IF NOT EXISTS promotion_pause JSONB
                NOT NULL DEFAULT '{}'::jsonb
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_engine_b_decision_pause_active
            ON engine_b_decision_snapshot
            ((COALESCE((promotion_pause ->> 'active')::boolean, FALSE)),
             as_of_date)
    """)
    # Update label CHECK to allow pause-suffixed variants
    op.execute("""
        ALTER TABLE engine_b_decision_snapshot
            DROP CONSTRAINT IF EXISTS ck_engine_b_decision_label
    """)
    op.execute("""
        ALTER TABLE engine_b_decision_snapshot
            ADD CONSTRAINT ck_engine_b_decision_label CHECK (
                label IN (
                    'NOT_READY', 'READY_FOR_REVIEW', 'STRONG_CANDIDATE',
                    'READY_FOR_REVIEW_PAUSED',
                    'PROMOTION_PAUSED_EDGE_DECAY',
                    'STRUCTURAL_REVIEW_REQUIRED'
                )
            )
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_engine_b_decision_pause_active")
    op.execute("""
        ALTER TABLE engine_b_decision_snapshot
            DROP COLUMN IF EXISTS promotion_pause
    """)
