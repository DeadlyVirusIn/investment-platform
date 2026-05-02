"""Phase 11W (Phase E.1) — research_manual_run_audit append-only audit table.

Records every manual-run **attempt** — accepted and rejected — so
operators have a single tail-able log of who tried what and why it
was allowed or blocked. Lives in `research_ro` schema; subject to
the same isolation rules (no FK from public, research_writer-only
INSERT).

Schema rules:
  * Append-only (no UPDATE column triggers, no DELETE trigger).
  * One row per attempt; `request_id` UNIQUE for idempotent retry
    (CLI/HTTP can supply a shared key).
  * `research_run_id` is nullable — populated only when the run
    actually completed and a research_run row exists.
  * NEVER stores raw provider body. Only metadata + decision +
    rejection reason.

Revision ID: 057_research_manual_audit
Revises: 056_options_shadow
"""

from __future__ import annotations

from alembic import op


revision = "057_research_manual_audit"
down_revision = "056_options_shadow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS research_ro.research_manual_run_audit (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at          timestamptz NOT NULL DEFAULT now(),
            operator_id         text NOT NULL,
            symbol              text NOT NULL,
            as_of               date NOT NULL,
            provider            text NOT NULL,
            model_id            text,
            request_source      text NOT NULL,
            prompt_hash         text,
            estimated_cost_usd  numeric(12,6),
            actual_cost_usd     numeric(12,6),
            status              text NOT NULL,
            rejection_reason    text,
            anomaly_flags       jsonb NOT NULL DEFAULT '[]'::jsonb,
            research_run_id     uuid,
            request_id          text,
            CONSTRAINT ck_audit_request_source
              CHECK (request_source IN ('cli', 'http')),
            CONSTRAINT ck_audit_status
              CHECK (status IN (
                'in_flight', 'accepted', 'rejected',
                'duplicate', 'error'
              ))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_created "
        "ON research_ro.research_manual_run_audit (created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_operator_created "
        "ON research_ro.research_manual_run_audit (operator_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_symbol_created "
        "ON research_ro.research_manual_run_audit (symbol, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_status_created "
        "ON research_ro.research_manual_run_audit (status, created_at DESC)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_audit_request_id "
        "ON research_ro.research_manual_run_audit (request_id) "
        "WHERE request_id IS NOT NULL"
    )
    # Grant constrained perms on the new table.
    op.execute(
        "GRANT INSERT, SELECT, UPDATE "
        "ON research_ro.research_manual_run_audit TO research_writer"
    )
    op.execute(
        "GRANT SELECT ON research_ro.research_manual_run_audit "
        "TO research_reader"
    )


def downgrade() -> None:
    op.execute("REVOKE ALL ON research_ro.research_manual_run_audit FROM research_reader")
    op.execute("REVOKE ALL ON research_ro.research_manual_run_audit FROM research_writer")
    op.execute("DROP INDEX IF EXISTS research_ro.ux_audit_request_id")
    op.execute("DROP INDEX IF EXISTS research_ro.ix_audit_status_created")
    op.execute("DROP INDEX IF EXISTS research_ro.ix_audit_symbol_created")
    op.execute("DROP INDEX IF EXISTS research_ro.ix_audit_operator_created")
    op.execute("DROP INDEX IF EXISTS research_ro.ix_audit_created")
    op.execute("DROP TABLE IF EXISTS research_ro.research_manual_run_audit")
