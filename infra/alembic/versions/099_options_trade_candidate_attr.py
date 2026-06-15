"""MP1A — options candidate→trade attribution link.

Closes the first missing join of the options outcome-feedback loop:

    options_strategy_candidate (confidence / diagnostics->confidence_v2)
      → options_paper_trade.strategy_candidate_id
      → options_paper_trade.realized_pnl_dollars

Adds a nullable BIGINT `strategy_candidate_id` to `options_paper_trade`,
a FK to `options_strategy_candidate(id)` (ON DELETE SET NULL so deleting a
candidate never blocks/destroys an executed trade row), and a lookup index.

Nullable + no backfill by design:
  * Existing rows pre-date the link and have no deterministic candidate
    mapping (the canary path never recorded one), so they stay NULL.
  * Non-canary writers (replay/backfill) that don't carry a candidate
    also leave it NULL. Backward-compatible: nothing requires the column.

The column is stamped going forward by the live promotion path
(canary.engine.promote_one → paper.engine.open_trade → _insert_trade_row),
which threads the candidate id from canary.selection.

Revision ID: 099_opt_trade_candidate_attr
Revises: 098_engine_sell_day_idem

NOTE: revision id is intentionally shorter than the filename —
alembic_version.version_num is varchar(32).
"""

from __future__ import annotations

from alembic import op


revision = "099_opt_trade_candidate_attr"
down_revision = "098_engine_sell_day_idem"
branch_labels = None
depends_on = None

FK_NAME = "fk_options_paper_trade_strategy_candidate"
IX_NAME = "ix_options_paper_trade_strategy_candidate_id"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE options_paper_trade "
        "ADD COLUMN IF NOT EXISTS strategy_candidate_id BIGINT"
    )
    op.execute(
        f"""
        ALTER TABLE options_paper_trade
        ADD CONSTRAINT {FK_NAME}
        FOREIGN KEY (strategy_candidate_id)
        REFERENCES options_strategy_candidate (id)
        ON DELETE SET NULL
        """
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {IX_NAME} "
        "ON options_paper_trade (strategy_candidate_id)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {IX_NAME}")
    op.execute(
        f"ALTER TABLE options_paper_trade DROP CONSTRAINT IF EXISTS {FK_NAME}"
    )
    op.execute(
        "ALTER TABLE options_paper_trade DROP COLUMN IF EXISTS strategy_candidate_id"
    )
