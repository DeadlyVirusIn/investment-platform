"""Phase 11W (Phase E.3) — operator cooldown fields + history table.

Extends `research_ro.research_operator_control` with cooldown
metadata fields used by the auto-enforcement evaluator. Adds an
append-only `research_ro.research_operator_control_history` table
that records every state transition (auto, manual, override).

Schema rules:
  * History table is append-only (no UPDATE on existing rows).
  * `metadata` column is jsonb; the writer sanitizes keys
    body/raw/structured/evidence/reflection/prompt.
  * FK to `research_alert.id` is research_ro → research_ro
    (allowed direction).

Revision ID: 059_research_oper_cooldown
Revises: 058_research_alerts
"""

from __future__ import annotations

from alembic import op


revision = "059_research_oper_cooldown"
down_revision = "058_research_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE research_ro.research_operator_control
          ADD COLUMN IF NOT EXISTS restricted_until        timestamptz,
          ADD COLUMN IF NOT EXISTS cooldown_reason         text,
          ADD COLUMN IF NOT EXISTS cooldown_source         text,
          ADD COLUMN IF NOT EXISTS last_auto_evaluation_at timestamptz,
          ADD COLUMN IF NOT EXISTS previous_state          text,
          ADD COLUMN IF NOT EXISTS state_changed_at        timestamptz
        """
    )
    op.execute(
        """
        ALTER TABLE research_ro.research_operator_control
          DROP CONSTRAINT IF EXISTS ck_operator_control_cooldown_source
        """
    )
    op.execute(
        """
        ALTER TABLE research_ro.research_operator_control
          ADD CONSTRAINT ck_operator_control_cooldown_source
            CHECK (cooldown_source IS NULL
                   OR cooldown_source IN ('auto', 'manual'))
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS
          research_ro.research_operator_control_history (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at      timestamptz NOT NULL DEFAULT now(),
            operator_id     text NOT NULL,
            previous_state  text,
            new_state       text NOT NULL,
            reason          text NOT NULL,
            source          text NOT NULL,
            cooldown_until  timestamptz,
            alert_id        uuid REFERENCES research_ro.research_alert(id),
            metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT ck_op_history_source
              CHECK (source IN ('auto', 'manual', 'override')),
            CONSTRAINT ck_op_history_new_state
              CHECK (new_state IN ('clear', 'watch', 'restricted', 'blocked'))
          )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_op_history_operator_created "
        "ON research_ro.research_operator_control_history "
        "(operator_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_op_history_created "
        "ON research_ro.research_operator_control_history "
        "(created_at DESC)"
    )

    # Grants — same posture as other research_ro tables.
    op.execute(
        "GRANT INSERT, SELECT "
        "ON research_ro.research_operator_control_history TO research_writer"
    )
    op.execute(
        "GRANT SELECT ON research_ro.research_operator_control_history "
        "TO research_reader"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON research_ro.research_operator_control_history "
        "FROM research_reader"
    )
    op.execute(
        "REVOKE ALL ON research_ro.research_operator_control_history "
        "FROM research_writer"
    )
    op.execute(
        "DROP INDEX IF EXISTS research_ro.ix_op_history_created"
    )
    op.execute(
        "DROP INDEX IF EXISTS research_ro.ix_op_history_operator_created"
    )
    op.execute(
        "DROP TABLE IF EXISTS research_ro.research_operator_control_history"
    )
    op.execute(
        "ALTER TABLE research_ro.research_operator_control "
        "DROP CONSTRAINT IF EXISTS ck_operator_control_cooldown_source"
    )
    op.execute(
        """
        ALTER TABLE research_ro.research_operator_control
          DROP COLUMN IF EXISTS state_changed_at,
          DROP COLUMN IF EXISTS previous_state,
          DROP COLUMN IF EXISTS last_auto_evaluation_at,
          DROP COLUMN IF EXISTS cooldown_source,
          DROP COLUMN IF EXISTS cooldown_reason,
          DROP COLUMN IF EXISTS restricted_until
        """
    )
