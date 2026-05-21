"""Phase L M088 — fix v_reasoning_quality.source_distribution.

The window-function approach in M087 emitted duplicate (source, n)
pairs per row inside json_object_agg, producing a malformed JSON with
the same key repeated. Replace with a clean CTE-based aggregate.

Revision ID: 088_phase_l_reasoning_qual_v2
Revises: 087_phase_l_reasoning_qual_v
"""

from __future__ import annotations

from alembic import op


revision = "088_phase_l_reasoning_qual_v2"
down_revision = "087_phase_l_reasoning_qual_v"
branch_labels = None
depends_on = None


VIEW_SQL = """
CREATE OR REPLACE VIEW v_reasoning_quality AS
WITH base AS (
    SELECT
        DATE(rendered_at)     AS day,
        skeleton_id,
        envelope_hash,
        uncertainty_markers,
        source
    FROM reasoning_audit
),
source_counts AS (
    SELECT day, skeleton_id, source, COUNT(*) AS n
    FROM base
    GROUP BY day, skeleton_id, source
),
dist AS (
    SELECT day, skeleton_id,
           json_object_agg(source, n) AS source_distribution
    FROM source_counts
    GROUP BY day, skeleton_id
),
agg AS (
    SELECT
        day,
        skeleton_id,
        COUNT(*)                                                AS n_envelopes,
        AVG(json_array_length(uncertainty_markers))::numeric(8,3)
                                                                AS avg_marker_count,
        ROUND(
            100.0 * COUNT(*) FILTER (
                WHERE json_array_length(uncertainty_markers) > 0
            )::numeric / NULLIF(COUNT(*), 0), 2
        )                                                       AS pct_with_markers,
        COUNT(DISTINCT envelope_hash)                           AS n_distinct_envelope_hashes
    FROM base
    GROUP BY day, skeleton_id
)
SELECT a.day, a.skeleton_id, a.n_envelopes, a.avg_marker_count,
       a.pct_with_markers, a.n_distinct_envelope_hashes,
       d.source_distribution
FROM agg a
LEFT JOIN dist d USING (day, skeleton_id);
"""


def upgrade() -> None:
    op.execute(VIEW_SQL)


def downgrade() -> None:
    # No clean inverse — M087's view was buggy; just drop and recreate
    # M087's SQL would still produce the same bad output.
    op.execute("DROP VIEW IF EXISTS v_reasoning_quality")
