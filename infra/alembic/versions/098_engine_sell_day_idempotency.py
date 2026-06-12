"""P0-3B.3 — idempotency guard for ENGINE sell fills (exit cycle +
auto_trader no-rec sells).

Gap found by the P0-3C dry run: the 06-04..06-10 double-fill window also
duplicated `run_paper_exit_cycle` sells (reason 'exit_cycle: ...'), and
those rows carry recommendation_id = NULL — so migration 097's
(portfolio, recommendation, side) index never sees them. auto_trader's
max_holding_days sells are also rec-NULL and equally unprotected.

upgrade:
  Partial UNIQUE index on paper_trade(portfolio_id, asset_id, fill_ts)
  scoped to engine sells only:
    * side = 'sell'
    * reason LIKE 'exit_cycle:%' OR reason LIKE 'auto_trader:%'
      (both engine write paths; manual / replay / research fills are
      never constrained)
    * fill_ts >= 2026-06-11 — legacy duplicates from the corrupted
      window stay untouched until the P0-3C repair.

  Why (portfolio, asset, fill_ts): engine exits close the full position
  and fill at the next bar — one engine sell per asset per portfolio per
  fill day is the invariant. A duplicated pass produces identical
  fill_ts, so the second insert collides. Legitimate later exits (after
  a re-entry) fill on a different bar -> different fill_ts -> allowed.

  Accepted edge (documented): two DIFFERENT engine rules selling the
  same asset on the same fill day (e.g. exit-cycle close at 23:01 +
  auto_trader rotation sell at 23:30). The second would fail anyway with
  "no open position to sell" — the index just fails it earlier. Partial
  exits do not exist in the engine today; revisit the key if they ship.

downgrade:
  Drop the index.

Revision ID: 098_engine_sell_day_idem
Revises: 097_paper_trade_idempotency

NOTE: revision id kept well under the alembic_version varchar(32)
limit (the 097 rehearsal caught an overflow; don't repeat it).
"""

from __future__ import annotations

from alembic import op


revision = "098_engine_sell_day_idem"
down_revision = "097_paper_trade_idempotency"
branch_labels = None
depends_on = None

INDEX_NAME = "ux_paper_trade_engine_sell_day"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE UNIQUE INDEX {INDEX_NAME}
        ON paper_trade (portfolio_id, asset_id, fill_ts)
        WHERE side = 'sell'
          AND (reason LIKE 'exit_cycle:%' OR reason LIKE 'auto_trader:%')
          AND fill_ts >= '2026-06-11 00:00:00+00'
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
