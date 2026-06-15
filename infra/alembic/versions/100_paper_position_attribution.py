"""MP1S — stock executed-outcome attribution on paper_position.

Closes the stock executed-outcome loop (forward-only):

    recommendation
      → paper_position.opened_by_recommendation_id
      → paper_position.realized_pnl
    (joinable to recommendation.conviction)

Distinct from recommendation_outcome, which is a price-path / hypothetical
loop (30d/90d returns, barrier labels) — left untouched.

Adds four nullable columns to paper_position:
  * opened_by_recommendation_id VARCHAR(36) — entry-decision identity;
      FK → recommendation(id) ON DELETE SET NULL; indexed.
  * realized_pnl NUMERIC(20,6) — executed P&L accumulated at the position
      level (same type/scale as paper_trade.realized_pnl / EQUITY_NUM).
  * opening_trade_id VARCHAR(36) — entry BUY paper_trade; FK → paper_trade(id)
      ON DELETE SET NULL; indexed.
  * closed_by_trade_id VARCHAR(36) — closing SELL paper_trade; FK →
      paper_trade(id) ON DELETE SET NULL; indexed.

Nullable + no backfill by design:
  * legacy positions have no deterministic opener (avg-cost merges + partial
    BUY recommendation_id + same-asset re-opens make the mapping ambiguous);
    they stay NULL. Backward-compatible — nothing requires the columns.

Forward stamping happens in paper_execution.submit_paper_trade:
  * opener + opening_trade_id at new-position creation,
  * realized_pnl accumulated per sell, closed_by_trade_id at full close.

Revision ID: 100_paper_position_attribution
Revises: 099_opt_trade_candidate_attr

NOTE: revision id length (30) is within alembic_version varchar(32).
"""

from __future__ import annotations

from alembic import op


revision = "100_paper_position_attribution"
down_revision = "099_opt_trade_candidate_attr"
branch_labels = None
depends_on = None

FK_REC = "fk_paper_position_opened_by_recommendation"
FK_OPEN = "fk_paper_position_opening_trade"
FK_CLOSE = "fk_paper_position_closed_by_trade"
IX_REC = "ix_paper_position_opened_by_recommendation_id"
IX_OPEN = "ix_paper_position_opening_trade_id"
IX_CLOSE = "ix_paper_position_closed_by_trade_id"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE paper_position "
        "ADD COLUMN IF NOT EXISTS opened_by_recommendation_id VARCHAR(36)"
    )
    op.execute(
        "ALTER TABLE paper_position "
        "ADD COLUMN IF NOT EXISTS realized_pnl NUMERIC(20, 6)"
    )
    op.execute(
        "ALTER TABLE paper_position "
        "ADD COLUMN IF NOT EXISTS opening_trade_id VARCHAR(36)"
    )
    op.execute(
        "ALTER TABLE paper_position "
        "ADD COLUMN IF NOT EXISTS closed_by_trade_id VARCHAR(36)"
    )
    op.execute(
        f"""
        ALTER TABLE paper_position ADD CONSTRAINT {FK_REC}
        FOREIGN KEY (opened_by_recommendation_id)
        REFERENCES recommendation (id) ON DELETE SET NULL
        """
    )
    op.execute(
        f"""
        ALTER TABLE paper_position ADD CONSTRAINT {FK_OPEN}
        FOREIGN KEY (opening_trade_id)
        REFERENCES paper_trade (id) ON DELETE SET NULL
        """
    )
    op.execute(
        f"""
        ALTER TABLE paper_position ADD CONSTRAINT {FK_CLOSE}
        FOREIGN KEY (closed_by_trade_id)
        REFERENCES paper_trade (id) ON DELETE SET NULL
        """
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {IX_REC} "
        "ON paper_position (opened_by_recommendation_id)"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {IX_OPEN} "
        "ON paper_position (opening_trade_id)"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {IX_CLOSE} "
        "ON paper_position (closed_by_trade_id)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {IX_CLOSE}")
    op.execute(f"DROP INDEX IF EXISTS {IX_OPEN}")
    op.execute(f"DROP INDEX IF EXISTS {IX_REC}")
    op.execute(f"ALTER TABLE paper_position DROP CONSTRAINT IF EXISTS {FK_CLOSE}")
    op.execute(f"ALTER TABLE paper_position DROP CONSTRAINT IF EXISTS {FK_OPEN}")
    op.execute(f"ALTER TABLE paper_position DROP CONSTRAINT IF EXISTS {FK_REC}")
    op.execute(
        "ALTER TABLE paper_position DROP COLUMN IF EXISTS closed_by_trade_id"
    )
    op.execute(
        "ALTER TABLE paper_position DROP COLUMN IF EXISTS opening_trade_id"
    )
    op.execute("ALTER TABLE paper_position DROP COLUMN IF EXISTS realized_pnl")
    op.execute(
        "ALTER TABLE paper_position DROP COLUMN IF EXISTS opened_by_recommendation_id"
    )
