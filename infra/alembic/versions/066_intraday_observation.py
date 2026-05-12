"""Phase 16 Phase 2 — intraday_observation table (data collection only).

Creates the durable feature-row store for the intraday ML shadow
layer. Per the architecture proposal in
`docs/research/INTRADAY_ML_SHADOW.md`, this migration is STRICTLY
ADDITIVE:

  * No ALTER on any existing table.
  * No DROP, no rename of any existing object.
  * No data migration.
  * `downgrade()` cleanly drops the new table and its indexes.

Nothing in production writes to this table at migration time. Writes
begin only when `INTRADAY_ML_SHADOW_ENABLED=true` is set in the
running api container — default is False. The observation_writer
module hooks into the existing market-tape poller AFTER a successful
Polygon refresh and produces one row per (recommendation_id, 15-min
slot). The UNIQUE (recommendation_id, observed_at_15min) constraint
makes the write idempotent — duplicate poll cycles upsert into the
same row.

This is Phase 2 (collection) only. No trainer / scorer / UI / cron
change ships with this migration.

Revision ID: 066_intraday_observation
Revises: 065_pipeline_run_ledger
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "066_intraday_observation"
down_revision = "065_pipeline_run_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intraday_observation",
        # Identity
        sa.Column(
            "id", UUID(as_uuid=True),
            primary_key=True, server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "recommendation_id", sa.String(36),
            sa.ForeignKey("recommendation.id"), nullable=False,
        ),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column(
            "observed_at_15min", sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC timestamp truncated to 15-min slot boundary",
        ),
        # Quantitative features (architecture doc §1)
        sa.Column("intraday_change_pct", sa.Numeric(10, 4)),
        sa.Column("vs_open_pct", sa.Numeric(10, 4)),
        sa.Column("vs_recommendation_entry_pct", sa.Numeric(10, 4)),
        sa.Column("vs_macro_drift_pct", sa.Numeric(10, 4)),
        sa.Column("intraday_range_pct", sa.Numeric(10, 4)),
        sa.Column("spy_change_pct", sa.Numeric(10, 4)),
        sa.Column("qqq_change_pct", sa.Numeric(10, 4)),
        sa.Column("dia_change_pct", sa.Numeric(10, 4)),
        # Categorical features
        sa.Column(
            "time_of_day_bucket", sa.String(16), nullable=False,
            comment="premarket | open30 | morning | midday | afternoon | close30 | afterhours",
        ),
        sa.Column("prior_eod_conviction", sa.Numeric(10, 4)),
        sa.Column(
            "action_type", sa.String(8), nullable=False,
            comment="buy | sell | trim | hold (from joined Recommendation.action)",
        ),
        sa.Column(
            "position_state", sa.String(16), nullable=False,
            comment="open_long | open_short | flat",
        ),
        # 60d daily-derived features (computed from existing price_bar)
        sa.Column("atr_60d_pct", sa.Numeric(10, 4)),
        sa.Column("vol_60d_pct", sa.Numeric(10, 4)),
        sa.Column("sector_id", sa.String(64)),
        # Provenance
        sa.Column(
            "source", sa.String(16), nullable=False,
            comment="upstream provider — e.g. 'polygon'",
        ),
        sa.Column(
            "delay_minutes", sa.SmallInteger, nullable=False,
            comment="upstream-reported delay floor (15 for Polygon Starter)",
        ),
        sa.Column(
            "quote_ts", sa.DateTime(timezone=True),
            comment="source-reported quote timestamp (delayed)",
        ),
        sa.Column(
            "feature_hash", sa.String(32), nullable=False,
            comment="SHA256(feature_dict)[:32] — for idempotency audits",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "recommendation_id", "observed_at_15min",
            name="uq_intraday_obs_rec_slot",
        ),
    )
    op.create_index(
        "ix_intraday_obs_symbol_time",
        "intraday_observation",
        ["symbol", sa.text("observed_at_15min DESC")],
    )
    op.create_index(
        "ix_intraday_obs_observed",
        "intraday_observation",
        [sa.text("observed_at_15min DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intraday_obs_observed",
        table_name="intraday_observation",
    )
    op.drop_index(
        "ix_intraday_obs_symbol_time",
        table_name="intraday_observation",
    )
    op.drop_table("intraday_observation")
