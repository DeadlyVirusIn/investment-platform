"""Phase L M087 — reasoning quality analytics view.

Aggregates over reasoning_audit. Operator-only read surface.

  v_reasoning_quality:
      day                       — render date (UTC)
      skeleton_id               — distinct skeleton
      n_envelopes               — count rendered that day for that skeleton
      avg_marker_count          — mean uncertainty_markers length
      pct_with_markers          — % of envelopes with >=1 marker
      n_distinct_envelope_hashes — uniqueness (truthful concentration vs drift)
      source_distribution       — JSON breakdown by source

Revision ID: 087_phase_l_reasoning_quality_v
Revises: 086_phase_l_skip_analytics_v
"""

from __future__ import annotations

from alembic import op


revision = "087_phase_l_reasoning_qual_v"
down_revision = "086_phase_l_skip_analytics_v"
branch_labels = None
depends_on = None


VIEW_SQL = """
CREATE OR REPLACE VIEW v_reasoning_quality AS
SELECT
    DATE(rendered_at)                     AS day,
    skeleton_id,
    COUNT(*)                              AS n_envelopes,
    AVG(json_array_length(uncertainty_markers))::numeric(8,3) AS avg_marker_count,
    ROUND(
        100.0
        * COUNT(*) FILTER (WHERE json_array_length(uncertainty_markers) > 0)::numeric
        / NULLIF(COUNT(*), 0),
        2
    )                                     AS pct_with_markers,
    COUNT(DISTINCT envelope_hash)         AS n_distinct_envelope_hashes,
    json_object_agg(source, n)            AS source_distribution
FROM (
    SELECT
        rendered_at, skeleton_id, envelope_hash, uncertainty_markers,
        source,
        COUNT(*) OVER (PARTITION BY DATE(rendered_at), skeleton_id, source) AS n
    FROM reasoning_audit
) sub
GROUP BY DATE(rendered_at), skeleton_id;
"""


def upgrade() -> None:
    op.execute(VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_reasoning_quality")
