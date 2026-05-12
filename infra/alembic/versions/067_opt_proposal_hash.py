"""Phase Opt-B1 — options_paper_trade.proposal_hash idempotency column.

STRICTLY ADDITIVE migration:
  * One new nullable column on options_paper_trade.
  * Partial UNIQUE index on proposal_hash WHERE proposal_hash IS NOT NULL.
  * No other table touched.
  * No existing row modified (existing rows leave proposal_hash NULL).
  * downgrade() drops the index + column cleanly.

Justification (per Opt-B1 audit, 2026-05-12): the existing options
paper-exec runner has NO dedup mechanism. A double-invocation of
`scripts/run_options_paper_exec.py --commit` on the same date with
the same limit would write duplicate (trade + legs) rows. The Opt-B1
sole-writer service `persist_option()` computes a stable
`proposal_hash` from the proposal's identity inputs (underlying,
strategy_name, strategy_version, opened_at::date, sorted leg specs,
fill_model_version) and refuses to insert when an existing row
matches.

This migration is the storage half of that mechanism. The partial
UNIQUE index makes the dedup race-safe at the DB level (two
concurrent inserts cannot both succeed with the same hash). The
column is NULLABLE so the migration is forward-compatible with
existing rows that pre-date the dedup contract — those rows simply
have proposal_hash IS NULL and don't participate in dedup checks.

Revision ID: 067_options_paper_trade_proposal_hash
Revises: 066_intraday_observation
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "067_opt_proposal_hash"
down_revision = "066_intraday_observation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "options_paper_trade",
        sa.Column(
            "proposal_hash",
            sa.String(32),
            nullable=True,
            comment=(
                "Phase Opt-B1 idempotency key. SHA256(json(proposal))[:32]. "
                "Computed by apps/api/src/options/persist_option.py. NULL for "
                "rows pre-dating the sole-writer contract."
            ),
        ),
    )
    # Partial UNIQUE — race-safe at DB level for new rows; existing
    # NULL rows are exempt from the constraint.
    op.create_index(
        "uq_options_paper_trade_proposal_hash",
        "options_paper_trade",
        ["proposal_hash"],
        unique=True,
        postgresql_where=sa.text("proposal_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_options_paper_trade_proposal_hash",
        table_name="options_paper_trade",
    )
    op.drop_column("options_paper_trade", "proposal_hash")
