"""Phase L M086 — envelope-generation skip analytics view.

Read-only aggregate view over envelope_generation_run for operator
dashboards / health endpoints.

  v_envelope_gen_coverage: per (portfolio_id, day) rollup with:
      trades_executed       — total trade attempts that day
      envelopes_attached    — number of envelopes successfully produced
      coverage_pct          — envelopes_attached / trades_executed * 100
      skip_features         — features-unavailable count
      skip_min_signals      — extractor returned <2 signals
      skip_no_skeleton      — selector found no matching rule
      skip_empty_slots      — slot builder couldn't populate
      skip_exception        — exception during generation
      skeleton_distribution — JSON aggregate across runs that day

Revision ID: 086_phase_l_skip_analytics_view
Revises: 085_phase_l_env_skip_reasons
"""

from __future__ import annotations

from alembic import op


revision = "086_phase_l_skip_analytics_v"
down_revision = "085_phase_l_env_skip_reasons"
branch_labels = None
depends_on = None


VIEW_SQL = """
CREATE OR REPLACE VIEW v_envelope_gen_coverage AS
SELECT
    portfolio_id,
    COALESCE(as_of_date, DATE(created_at)) AS day,
    SUM(trades_executed)             AS trades_executed,
    SUM(envelopes_attached)          AS envelopes_attached,
    CASE
        WHEN SUM(trades_executed) > 0
        THEN ROUND(100.0 * SUM(envelopes_attached)::numeric
                   / SUM(trades_executed)::numeric, 2)
        ELSE 0
    END                              AS coverage_pct,
    SUM(skip_features_unavailable)   AS skip_features,
    SUM(skip_min_signals)            AS skip_min_signals,
    SUM(skip_no_skeleton_match)      AS skip_no_skeleton,
    SUM(skip_empty_slot_fills)       AS skip_empty_slots,
    SUM(skip_exception)              AS skip_exception
FROM envelope_generation_run
GROUP BY portfolio_id, COALESCE(as_of_date, DATE(created_at));
"""


def upgrade() -> None:
    op.execute(VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_envelope_gen_coverage")
