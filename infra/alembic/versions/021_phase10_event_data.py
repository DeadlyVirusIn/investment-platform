"""Phase 10 — event-data ingestion + storage tables.

Adds raw ingestion tables, normalized PIT-queried tables, and a shared
quarantine table. Preserves Phase 9 semantics exactly: joins are
deterministic; unique constraints match the in-memory reference repos.

Revision ID: 021
Revises: 020
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

JSONB = sa.JSON().with_variant(
    __import__("sqlalchemy.dialects.postgresql", fromlist=["JSONB"]).JSONB,
    "postgresql",
)

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _common_raw_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(256), nullable=True),
        sa.Column(
            "ingested_ts", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("payload", JSONB, nullable=True),
    ]


def upgrade() -> None:
    # --- Raw ingestion tables ------------------------------------------
    op.create_table(
        "event_raw_earnings", *_common_raw_columns(),
        sa.UniqueConstraint(
            "source", "external_id",
            name="ux_event_raw_earnings_source_extid",
        ),
    )
    op.create_index(
        "ix_event_raw_earnings_source", "event_raw_earnings", ["source"],
    )
    op.create_index(
        "ix_event_raw_earnings_ingested_ts", "event_raw_earnings", ["ingested_ts"],
    )

    op.create_table(
        "event_raw_shares", *_common_raw_columns(),
        sa.UniqueConstraint(
            "source", "external_id",
            name="ux_event_raw_shares_source_extid",
        ),
    )
    op.create_index(
        "ix_event_raw_shares_source", "event_raw_shares", ["source"],
    )
    op.create_index(
        "ix_event_raw_shares_ingested_ts", "event_raw_shares", ["ingested_ts"],
    )

    op.create_table(
        "event_raw_consensus", *_common_raw_columns(),
        sa.UniqueConstraint(
            "source", "external_id",
            name="ux_event_raw_consensus_source_extid",
        ),
    )
    op.create_index(
        "ix_event_raw_consensus_source", "event_raw_consensus", ["source"],
    )
    op.create_index(
        "ix_event_raw_consensus_ingested_ts", "event_raw_consensus", ["ingested_ts"],
    )

    # --- Normalized: earnings_event ------------------------------------
    op.create_table(
        "earnings_event",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.String(16), nullable=False),
        sa.Column(
            "announcement_timestamp", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("announcement_timestamp_raw", sa.String(128), nullable=True),
        sa.Column("fiscal_period", sa.String(32), nullable=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column(
            "ingested_ts", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_ts", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "asset_id", "event_date", name="ux_earnings_event_asset_date",
        ),
    )
    op.create_index(
        "ix_earnings_event_event_date", "earnings_event", ["event_date"],
    )
    op.create_index(
        "ix_earnings_event_symbol_date", "earnings_event", ["symbol", "event_date"],
    )
    op.create_index(
        "ix_earnings_event_asset_id", "earnings_event", ["asset_id"],
    )
    op.create_index(
        "ix_earnings_event_symbol", "earnings_event", ["symbol"],
    )

    # --- Normalized: shares_outstanding --------------------------------
    op.create_table(
        "shares_outstanding",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("shares_outstanding", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column(
            "ingested_ts", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_ts", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "asset_id", "effective_date", "source",
            name="ux_shares_outstanding_asset_effective_source",
        ),
    )
    op.create_index(
        "ix_shares_outstanding_symbol_filing",
        "shares_outstanding", ["symbol", "filing_date"],
    )
    op.create_index(
        "ix_shares_outstanding_asset_filing",
        "shares_outstanding", ["asset_id", "filing_date"],
    )
    op.create_index(
        "ix_shares_outstanding_asset_id", "shares_outstanding", ["asset_id"],
    )
    op.create_index(
        "ix_shares_outstanding_symbol", "shares_outstanding", ["symbol"],
    )
    op.create_index(
        "ix_shares_outstanding_filing_date",
        "shares_outstanding", ["filing_date"],
    )

    # --- Normalized: consensus_estimate --------------------------------
    op.create_table(
        "consensus_estimate",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(16), nullable=False),
        sa.Column("estimate_type", sa.String(16), nullable=False),
        sa.Column("value", sa.Numeric(20, 6), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column(
            "ingested_ts", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "asset_id", "event_date", "metric", "estimate_type",
            "as_of_date", "source",
            name="ux_consensus_estimate_natural_key",
        ),
    )
    op.create_index(
        "ix_consensus_estimate_lookup", "consensus_estimate",
        ["asset_id", "event_date", "metric", "estimate_type", "as_of_date"],
    )
    op.create_index(
        "ix_consensus_estimate_event_date", "consensus_estimate", ["event_date"],
    )
    op.create_index(
        "ix_consensus_estimate_as_of", "consensus_estimate", ["as_of_date"],
    )
    op.create_index(
        "ix_consensus_estimate_asset_id", "consensus_estimate", ["asset_id"],
    )
    op.create_index(
        "ix_consensus_estimate_symbol", "consensus_estimate", ["symbol"],
    )

    # --- Quarantine ----------------------------------------------------
    op.create_table(
        "event_quarantine",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("raw_ingestion_id", sa.String(36), nullable=True),
        sa.Column("reason", sa.String(128), nullable=False),
        sa.Column("reason_detail", sa.Text(), nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column(
            "quarantined_ts", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_event_quarantine_source_type", "event_quarantine", ["source_type"],
    )
    op.create_index(
        "ix_event_quarantine_quarantined_ts",
        "event_quarantine", ["quarantined_ts"],
    )
    op.create_index(
        "ix_event_quarantine_reason", "event_quarantine", ["reason"],
    )


def downgrade() -> None:
    for table in (
        "event_quarantine",
        "consensus_estimate",
        "shares_outstanding",
        "earnings_event",
        "event_raw_consensus",
        "event_raw_shares",
        "event_raw_earnings",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
