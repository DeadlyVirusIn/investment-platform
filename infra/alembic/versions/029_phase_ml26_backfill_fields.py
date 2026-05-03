"""Phase ML-2.6 — catalyst backfill + known_at fields.

Extends news_item + earnings_event with canonical historical-backfill
fields. All new columns nullable so existing rows remain valid.

Also creates catalyst_backfill_run for audit + coverage tracking.

Revision ID: 029_phase_ml26_backfill_fields
Revises: 028_phase_ml25_replay
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "029_phase_ml26_backfill_fields"
down_revision = "028_phase_ml25_replay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------- news_item additions -------------
    op.add_column("news_item",
        sa.Column("provider", sa.String(32), nullable=True))
    op.add_column("news_item",
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("news_item",
        sa.Column("dedupe_key", sa.String(80), nullable=True))
    op.add_column("news_item",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_news_item_provider",
        "news_item", ["provider"],
    )
    op.create_index(
        "ix_news_item_dedupe_key",
        "news_item", ["dedupe_key"], unique=False,
    )

    # ------------- earnings_event additions -------------
    op.add_column("earnings_event",
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("earnings_event",
        sa.Column("provider", sa.String(32), nullable=True))
    op.add_column("earnings_event",
        sa.Column("dedupe_key", sa.String(80), nullable=True))
    op.add_column("earnings_event",
        sa.Column("fiscal_year", sa.Integer, nullable=True))
    op.add_column("earnings_event",
        sa.Column("event_time_hint", sa.String(16), nullable=True))
    op.add_column("earnings_event",
        sa.Column("eps_estimate", sa.Numeric(18, 6), nullable=True))
    op.add_column("earnings_event",
        sa.Column("eps_actual", sa.Numeric(18, 6), nullable=True))
    op.add_column("earnings_event",
        sa.Column("revenue_estimate", sa.Numeric(22, 2), nullable=True))
    op.add_column("earnings_event",
        sa.Column("revenue_actual", sa.Numeric(22, 2), nullable=True))
    op.add_column("earnings_event",
        sa.Column("raw_payload", JSONB, nullable=True))
    op.create_index(
        "ix_earnings_event_known_at",
        "earnings_event", ["known_at"],
    )
    op.create_index(
        "ix_earnings_event_provider",
        "earnings_event", ["provider"],
    )

    # ------------- catalyst_backfill_run -------------
    op.create_table(
        "catalyst_backfill_run",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("started_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="running"),
        sa.Column("symbols", JSONB, nullable=False, server_default="[]"),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date",   sa.Date, nullable=False),
        sa.Column("providers",  JSONB, nullable=False, server_default="[]"),
        sa.Column("dry_run", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("config",  JSONB, nullable=False, server_default="{}"),
        sa.Column("summary", JSONB, nullable=True),
        sa.Column("warnings", JSONB, nullable=True),
    )
    op.create_index(
        "ix_catalyst_backfill_run_started",
        "catalyst_backfill_run", ["started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalyst_backfill_run_started",
                  table_name="catalyst_backfill_run")
    op.drop_table("catalyst_backfill_run")

    op.drop_index("ix_earnings_event_provider", table_name="earnings_event")
    op.drop_index("ix_earnings_event_known_at", table_name="earnings_event")
    for c in ("raw_payload", "revenue_actual", "revenue_estimate",
              "eps_actual", "eps_estimate", "event_time_hint",
              "fiscal_year", "dedupe_key", "provider", "known_at"):
        op.drop_column("earnings_event", c)

    op.drop_index("ix_news_item_dedupe_key", table_name="news_item")
    op.drop_index("ix_news_item_provider", table_name="news_item")
    for c in ("updated_at", "dedupe_key", "ingested_at", "provider"):
        op.drop_column("news_item", c)
