"""Phase 10.6 — data hardening (timezone, units, content_hash).

Additive follow-up to 021_phase10_event_data. Chosen over amending 021 so
that schema history is explicit: if 021 is already applied locally, 022
applies cleanly via ALTER TABLE; if 021 has not yet been applied (prod
state as of 2026-04-22), 021 then 022 end-to-end produces the same final
schema.

Adds:
  - content_hash column (NOT NULL) to 3 raw ingestion tables + consensus_estimate
  - unique (source, content_hash) on raw tables
  - value_unit / original_value / original_unit on consensus_estimate

Revision ID: 022
Revises: 021
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_RAW_TABLES = (
    "event_raw_earnings",
    "event_raw_shares",
    "event_raw_consensus",
)


def upgrade() -> None:
    # --- content_hash on raw tables ------------------------------------
    for t in _RAW_TABLES:
        op.add_column(
            t, sa.Column(
                "content_hash", sa.String(64), nullable=True,
            ),
        )
        # Back-fill empty string (safe default) so NOT NULL can be enforced
        op.execute(
            f"UPDATE {t} SET content_hash = '' WHERE content_hash IS NULL"
        )
        op.alter_column(t, "content_hash", nullable=False)
        op.create_index(
            f"ix_{t}_content_hash", t, ["content_hash"],
        )
        op.create_unique_constraint(
            f"ux_{t}_source_content_hash", t,
            ["source", "content_hash"],
        )

    # --- value_unit + original_value + original_unit on consensus_estimate
    op.add_column(
        "consensus_estimate",
        sa.Column("value_unit", sa.String(32), nullable=True),
    )
    op.add_column(
        "consensus_estimate",
        sa.Column("original_value", sa.Numeric(20, 6), nullable=True),
    )
    op.add_column(
        "consensus_estimate",
        sa.Column("original_unit", sa.String(32), nullable=True),
    )
    # For legacy pre-10.6 rows, infer canonical unit per metric
    op.execute(
        "UPDATE consensus_estimate SET value_unit = 'usd_per_share' "
        "WHERE metric = 'eps' AND value_unit IS NULL"
    )
    op.execute(
        "UPDATE consensus_estimate SET value_unit = 'usd_raw' "
        "WHERE metric = 'revenue' AND value_unit IS NULL"
    )
    # After backfill, value_unit may be NULL only if metric is unknown;
    # leave nullable to avoid failing on unexpected legacy rows.

    # content_hash column on consensus_estimate (informational; natural-key
    # uniqueness still primary).
    op.add_column(
        "consensus_estimate",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_consensus_estimate_content_hash",
        "consensus_estimate", ["content_hash"],
    )


def downgrade() -> None:
    # consensus_estimate
    op.drop_index(
        "ix_consensus_estimate_content_hash",
        table_name="consensus_estimate",
    )
    op.drop_column("consensus_estimate", "content_hash")
    op.drop_column("consensus_estimate", "original_unit")
    op.drop_column("consensus_estimate", "original_value")
    op.drop_column("consensus_estimate", "value_unit")

    for t in _RAW_TABLES:
        op.drop_constraint(
            f"ux_{t}_source_content_hash", t, type_="unique",
        )
        op.drop_index(f"ix_{t}_content_hash", table_name=t)
        op.drop_column(t, "content_hash")
