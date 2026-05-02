"""Phase 11W (Phase E.2) — research alerts + operator control tables.

Adds two append-only-ish operational tables to `research_ro`:

  * `research_operator_control` — one row per operator. Tracks
    enforcement state (clear/watch/restricted/blocked) so manual
    runs can refuse blocked operators BEFORE the provider is
    invoked.
  * `research_alert` — append-only alert ledger. Severity buckets
    info/warning/high/critical. Status open/acknowledged/resolved.
    NEVER stores raw model bodies (CHECK + design intent).

Both tables live in `research_ro` and inherit the same isolation
rules: research_writer = INSERT/SELECT/UPDATE; research_reader =
SELECT only; FK from public → research_ro forbidden.

Revision ID: 058_research_alerts
Revises: 057_research_manual_audit
"""

from __future__ import annotations

from alembic import op


revision = "058_research_alerts"
down_revision = "057_research_manual_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS research_ro.research_operator_control (
            operator_id     text PRIMARY KEY,
            state           text NOT NULL DEFAULT 'clear',
            reason          text,
            first_seen_at   timestamptz NOT NULL DEFAULT now(),
            last_seen_at    timestamptz NOT NULL DEFAULT now(),
            blocked_until   timestamptz,
            updated_by      text NOT NULL,
            updated_at      timestamptz NOT NULL DEFAULT now(),
            notes           text,
            CONSTRAINT ck_operator_control_state
              CHECK (state IN ('clear', 'watch', 'restricted', 'blocked'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_operator_control_state "
        "ON research_ro.research_operator_control (state, updated_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS research_ro.research_alert (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at    timestamptz NOT NULL DEFAULT now(),
            severity      text NOT NULL,
            alert_type    text NOT NULL,
            operator_id   text,
            symbol        text,
            message       text NOT NULL,
            status        text NOT NULL DEFAULT 'open',
            metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,
            acknowledged_by text,
            acknowledged_at timestamptz,
            CONSTRAINT ck_alert_severity
              CHECK (severity IN ('info', 'warning', 'high', 'critical')),
            CONSTRAINT ck_alert_status
              CHECK (status IN ('open', 'acknowledged', 'resolved')),
            -- Forbid raw-body fields in metadata. We can't enforce
            -- arbitrary JSON keys at DDL time, but operators
            -- inserting into this table get the same DB CHECK on
            -- the message string as everywhere else in research_ro.
            CONSTRAINT ck_alert_message_no_action_tokens
              CHECK (
                message !~* '\\m(buy|sell|hold|long|short|recommend|recommends|recommended|recommending|recommendation|recommendations|signal|signals|signaled|signaling|allocate|allocates|allocated|allocating|allocation|execute|executes|executed|executing|execution|position|positions|entry|exit|leverage|leveraged|leveraging)\\M'
                AND message !~* 'target\\s+price'
                AND message !~* 'stop[\\s-]?loss'
                AND message !~* 'take[\\s-]?profit'
                AND message !~* 'portfolio\\s+manager'
                AND message !~* 'copy[\\s-]?trade'
              )
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_created "
        "ON research_ro.research_alert (created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_severity_status "
        "ON research_ro.research_alert (severity, status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_operator_created "
        "ON research_ro.research_alert (operator_id, created_at DESC)"
    )

    # Grants — match the rest of research_ro.
    op.execute(
        "GRANT INSERT, SELECT, UPDATE "
        "ON research_ro.research_operator_control TO research_writer"
    )
    op.execute(
        "GRANT SELECT ON research_ro.research_operator_control "
        "TO research_reader"
    )
    op.execute(
        "GRANT INSERT, SELECT, UPDATE ON research_ro.research_alert "
        "TO research_writer"
    )
    op.execute(
        "GRANT SELECT ON research_ro.research_alert TO research_reader"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON research_ro.research_alert FROM research_reader"
    )
    op.execute(
        "REVOKE ALL ON research_ro.research_alert FROM research_writer"
    )
    op.execute(
        "REVOKE ALL ON research_ro.research_operator_control FROM research_reader"
    )
    op.execute(
        "REVOKE ALL ON research_ro.research_operator_control FROM research_writer"
    )
    op.execute("DROP INDEX IF EXISTS research_ro.ix_alert_operator_created")
    op.execute("DROP INDEX IF EXISTS research_ro.ix_alert_severity_status")
    op.execute("DROP INDEX IF EXISTS research_ro.ix_alert_created")
    op.execute("DROP TABLE IF EXISTS research_ro.research_alert")
    op.execute("DROP INDEX IF EXISTS research_ro.ix_operator_control_state")
    op.execute(
        "DROP TABLE IF EXISTS research_ro.research_operator_control"
    )
