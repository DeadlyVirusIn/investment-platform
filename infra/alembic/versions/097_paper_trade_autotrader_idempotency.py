"""P0-3B — idempotency guard for auto-trader paper fills.

Root cause (P0-3A forensics): the worker image deployed 2026-06-04 →
2026-06-10 double-executed every auto_trader decision batch — two fill
rows per decision with identical (portfolio_id, recommendation_id,
side). Nothing at the DB layer rejected the second insert.

upgrade:
  Partial UNIQUE index on paper_trade(portfolio_id, recommendation_id,
  side) scoped to auto_trader fills only:
    * recommendation_id IS NOT NULL  — manual/replay fills (NULL rec)
      are never constrained;
    * reason LIKE 'auto_trader:%'    — only the auto-trader write path;
    * fill_ts >= 2026-06-11          — the corrupted window's existing
      duplicate rows stay untouched (data repair is P0-3C, NOT this
      migration); without this bound the index build would fail on the
      31 known duplicate legs.

  Legitimate re-entry is NOT blocked: recommendations are regenerated
  daily with new ids, so a future buy of the same asset rides a new
  recommendation_id. The only blocked shape is the bug shape — the
  same decision written twice. (Edge accepted + documented: a re-buy
  against a STALE, un-regenerated recommendation id would be rejected;
  trading the same rec twice in one portfolio is the dup signature.)

downgrade:
  Drop the index.

Revision ID: 097_paper_trade_idempotency
Revises: 096_funnel_risk_control_skips

NOTE: revision id is intentionally shorter than the filename —
alembic_version.version_num is varchar(32) and the long form
(38 chars) failed the verify-deploy rehearsal with
StringDataRightTruncation.
"""

from __future__ import annotations

from alembic import op


revision = "097_paper_trade_idempotency"
down_revision = "096_funnel_risk_control_skips"
branch_labels = None
depends_on = None

INDEX_NAME = "ux_paper_trade_autotrader_idempotency"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE UNIQUE INDEX {INDEX_NAME}
        ON paper_trade (portfolio_id, recommendation_id, side)
        WHERE recommendation_id IS NOT NULL
          AND reason LIKE 'auto_trader:%'
          AND fill_ts >= '2026-06-11 00:00:00+00'
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
