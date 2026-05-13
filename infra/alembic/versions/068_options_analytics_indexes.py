"""Phase Opt-B3a Phase 6b-2 — options analytics index (single, non-blocking).

STRICTLY ADDITIVE migration:
  * Single new composite index on options_shadow_decision_log
    (run_date, strategy_name, would_trade)
  * Built with `CONCURRENTLY` → zero table-level write lock; no blocking
  * No table mutations. No column changes. No data movement.

Rationale (per 6b-1 query evidence + amendment 5: no speculative indexes)
------------------------------------------------------------------------
6b-1 EXPLAIN ANALYZE on current dataset (7 505 rows) showed:

  Query              | Today      | Plan          | Year-1 risk
  ------------------ | ---------- | ------------- | ----------------------
  daily_counts (14d) | 3.944 ms   | Seq Scan      | Linear in row count;
                                                    will degrade to ~120ms
                                                    at 225k rows (30d, year-1)
  by_strategy (1d)   | 1.550 ms   | Seq Scan      | Same Seq Scan risk
  _select_run_batch  | 0.032 ms   | Index Scan    | Covered by existing
                                                    natural-key index
  provider_mix (14d) | 3.285 ms   | Hash Join     | Build side full scan;
                                                    index unhelpful
  by_rejection (7d)  | 0.121 ms   | Index Scan    | Covered by
                                                    ix_options_shadow_run_date
  universe_drift     | 0.442 ms   | Index Scan    | Covered

ONLY the (run_date, strategy_name) Seq Scans demonstrably risk
year-1 degradation. The new composite index targets BOTH affected
endpoints (daily_counts, by_strategy) with a single structure.

Selectivity analysis
--------------------
* (run_date) leading column: ~7 500 rows per distinct value at
  year-1; high cardinality (~365 distinct values year-1).
* (strategy_name) second column: currently 1 distinct value
  (options_shadow_v1); expected ~3-8 distinct values when
  strategy templates split. Low cardinality but enables
  GROUP BY index walk.
* (would_trade) third column: 2 distinct values. Included so
  COUNT(*) FILTER (WHERE would_trade) can use index-only scans
  when stats stay tight.

Expected year-1 benefit
-----------------------
* daily_counts: Seq Scan → Bitmap Index Scan + Index Cond on
  run_date. Estimated 5-10× speedup at year-1 scale.
* by_strategy: Seq Scan → Index Scan + Filter. Estimated 3-5×.
* No regression on existing queries (additive index only).

Estimated index size at year-1
------------------------------
~30 bytes/entry × 2.7 M rows ≈ 80 MB
Trivial vs ~3.8 GB projected table heap.

Write overhead
--------------
~+15-20% per INSERT into options_shadow_decision_log. Daily
7 500-row batch insert wall-clock moves from 1.5 s to ~1.8 s.
Acceptable for once-EOD cadence.

Indexes NOT added (per amendment 5 — speculative)
-------------------------------------------------
* Partial (run_date, reason) WHERE NOT would_trade — by_rejection
  is already 0.121 ms; partial index would cover 99.6 % of rows
  anyway (NOT would_trade is the dominant case), so it would
  approximate a full index.
* (provider, snapshot_at_utc DESC) on chain — _select_run_batch
  already uses natural-key index efficiently; provider_mix is
  a Hash Join with build-side full scan that an index cannot
  meaningfully accelerate.

Revision ID: 068_options_analytics_indexes
Revises: 067_opt_proposal_hash
"""

from __future__ import annotations

from alembic import op


revision = "068_options_analytics_indexes"
down_revision = "067_opt_proposal_hash"
branch_labels = None
depends_on = None


# CREATE INDEX CONCURRENTLY cannot run inside a transaction — alembic
# wraps each upgrade in a transaction by default. autocommit_block
# detaches the next statement(s) from the surrounding TX so PG accepts
# the CONCURRENTLY directive.

def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_options_shadow_decision_run_date_strategy "
            "ON options_shadow_decision_log "
            "  (run_date, strategy_name, would_trade)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS "
            "ix_options_shadow_decision_run_date_strategy"
        )
