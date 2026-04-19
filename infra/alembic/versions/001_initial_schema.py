"""Initial schema – all tables for investment-intelligence platform Phase 0.

Revision ID: 001
Revises:
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Precision constants
CRYPTO_NUM  = sa.Numeric(28, 10)   # crypto qty / price
EQUITY_NUM  = sa.Numeric(20, 6)    # equity qty / price / financial metrics


def upgrade() -> None:
    # ------------------------------------------------------------------ asset
    op.create_table(
        "asset",
        sa.Column("id",          sa.String(36),  primary_key=True),
        sa.Column("symbol",      sa.String(32),  nullable=False),
        sa.Column("name",        sa.String(256), nullable=True),
        sa.Column("asset_class", sa.String(32),  nullable=False),
        sa.Column("exchange",    sa.String(32),  nullable=True),
        sa.Column("currency",    sa.String(8),   nullable=False, server_default="USD"),
        sa.Column("is_active",   sa.Boolean(),   nullable=False, server_default=sa.text("true")),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("symbol", "exchange", name="uq_asset_symbol_exchange"),
    )
    op.create_index("ix_asset_symbol", "asset", ["symbol"])

    # ------------------------------------------------------------------ price_bar
    op.create_table(
        "price_bar",
        sa.Column("id",             sa.String(36), primary_key=True),
        sa.Column("asset_id",       sa.String(36), sa.ForeignKey("asset.id"), nullable=False),
        sa.Column("timeframe",      sa.String(8),  nullable=False),
        sa.Column("ts",             sa.DateTime(timezone=True), nullable=False),
        sa.Column("open",           EQUITY_NUM,    nullable=True),
        sa.Column("high",           EQUITY_NUM,    nullable=True),
        sa.Column("low",            EQUITY_NUM,    nullable=True),
        sa.Column("close",          EQUITY_NUM,    nullable=True),
        sa.Column("adjusted_close", EQUITY_NUM,    nullable=True),
        sa.Column("volume",         sa.BigInteger(), nullable=True),
        sa.Column("provider",       sa.String(32), nullable=False),
        sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("asset_id", "timeframe", "ts", "provider", name="uq_price_bar"),
    )
    op.create_index("ix_price_bar_asset_ts", "price_bar", ["asset_id", "ts"])

    # ------------------------------------------------------------------ corporate_action
    op.create_table(
        "corporate_action",
        sa.Column("id",          sa.String(36), primary_key=True),
        sa.Column("asset_id",    sa.String(36), sa.ForeignKey("asset.id"), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("ex_date",     sa.DateTime(timezone=True), nullable=False),
        sa.Column("ratio",       EQUITY_NUM,   nullable=True),
        sa.Column("amount",      EQUITY_NUM,   nullable=True),
        sa.Column("currency",    sa.String(8), nullable=True),
        sa.Column("provider",    sa.String(32), nullable=False),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------ fundamental_fact
    op.create_table(
        "fundamental_fact",
        sa.Column("id",          sa.String(36), primary_key=True),
        sa.Column("asset_id",    sa.String(36), sa.ForeignKey("asset.id"), nullable=False),
        sa.Column("period_end",  sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_type", sa.String(8),  nullable=False),
        sa.Column("metric",      sa.String(64), nullable=False),
        sa.Column("value",       EQUITY_NUM,   nullable=True),
        sa.Column("unit",        sa.String(32), nullable=True),
        sa.Column("provider",    sa.String(32), nullable=False),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "asset_id", "period_end", "period_type", "metric", "provider",
            name="uq_fundamental_fact",
        ),
    )

    # ------------------------------------------------------------------ macro_series_observation
    op.create_table(
        "macro_series_observation",
        sa.Column("id",          sa.String(36), primary_key=True),
        sa.Column("series_id",   sa.String(64), nullable=False),
        sa.Column("series_name", sa.String(128), nullable=True),
        sa.Column("ts",          sa.DateTime(timezone=True), nullable=False),
        sa.Column("value",       EQUITY_NUM,   nullable=True),
        sa.Column("provider",    sa.String(32), nullable=False),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("series_id", "ts", "provider", name="uq_macro_obs"),
    )

    # ------------------------------------------------------------------ account
    op.create_table(
        "account",
        sa.Column("id",           sa.String(36),  primary_key=True),
        sa.Column("name",         sa.String(128), nullable=False),
        sa.Column("broker",       sa.String(64),  nullable=True),
        sa.Column("account_type", sa.String(32),  nullable=False),
        sa.Column("currency",     sa.String(8),   nullable=False, server_default="USD"),
        sa.Column("is_active",    sa.Boolean(),   nullable=False, server_default=sa.text("true")),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------ transaction
    op.create_table(
        "transaction",
        sa.Column("id",         sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("asset_id",   sa.String(36), sa.ForeignKey("asset.id"),   nullable=False),
        sa.Column("ts",         sa.DateTime(timezone=True), nullable=False),
        sa.Column("action",     sa.String(16), nullable=False),
        sa.Column("quantity",   CRYPTO_NUM,   nullable=False),
        sa.Column("price",      CRYPTO_NUM,   nullable=False),
        sa.Column("fees",       EQUITY_NUM,   nullable=True),
        sa.Column("currency",   sa.String(8), nullable=False, server_default="USD"),
        sa.Column("notes",      sa.Text(),    nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_transaction_account_ts", "transaction", ["account_id", "ts"])

    # ------------------------------------------------------------------ lot
    op.create_table(
        "lot",
        sa.Column("id",                  sa.String(36), primary_key=True),
        sa.Column("open_transaction_id", sa.String(36),
                  sa.ForeignKey("transaction.id"), nullable=False),
        sa.Column("asset_id",            sa.String(36),
                  sa.ForeignKey("asset.id"), nullable=False),
        sa.Column("quantity_opened",     CRYPTO_NUM, nullable=False),
        sa.Column("quantity_remaining",  CRYPTO_NUM, nullable=False),
        sa.Column("cost_basis_per_unit", CRYPTO_NUM, nullable=False),
        sa.Column("currency",            sa.String(8), nullable=False, server_default="USD"),
        sa.Column("created_at",          sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------ lot_close
    op.create_table(
        "lot_close",
        sa.Column("id",                   sa.String(36), primary_key=True),
        sa.Column("lot_id",               sa.String(36), sa.ForeignKey("lot.id"), nullable=False),
        sa.Column("close_transaction_id", sa.String(36),
                  sa.ForeignKey("transaction.id"), nullable=False),
        sa.Column("quantity_closed",      CRYPTO_NUM, nullable=False),
        sa.Column("proceeds_per_unit",    CRYPTO_NUM, nullable=False),
        sa.Column("realized_pnl",         EQUITY_NUM, nullable=True),
        sa.Column("created_at",           sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------ position_snapshot
    op.create_table(
        "position_snapshot",
        sa.Column("id",            sa.String(36), primary_key=True),
        sa.Column("account_id",    sa.String(36), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("asset_id",      sa.String(36), sa.ForeignKey("asset.id"),   nullable=False),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity",      CRYPTO_NUM,   nullable=False),
        sa.Column("market_value",  EQUITY_NUM,   nullable=True),
        sa.Column("unrealized_pnl",EQUITY_NUM,   nullable=True),
        sa.Column("created_at",    sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("account_id", "asset_id", "snapshot_date",
                            name="uq_position_snapshot"),
    )

    # ------------------------------------------------------------------ recommendation
    op.create_table(
        "recommendation",
        sa.Column("id",            sa.String(36), primary_key=True),
        sa.Column("asset_id",      sa.String(36), sa.ForeignKey("asset.id"), nullable=False),
        sa.Column("generated_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("action",        sa.String(16), nullable=False),
        sa.Column("conviction",    EQUITY_NUM,   nullable=True),
        sa.Column("rationale",     sa.Text(),    nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("expires_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",    sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_recommendation_asset_generated_at",
                    "recommendation", ["asset_id", "generated_at"])

    # ------------------------------------------------------------------ recommendation_evidence
    op.create_table(
        "recommendation_evidence",
        sa.Column("id",                sa.String(36), primary_key=True),
        sa.Column("recommendation_id", sa.String(36),
                  sa.ForeignKey("recommendation.id"), nullable=False),
        sa.Column("evidence_type",     sa.String(32), nullable=False),
        sa.Column("source",            sa.String(256), nullable=True),
        sa.Column("summary",           sa.Text(),     nullable=True),
        sa.Column("weight",            EQUITY_NUM,   nullable=True),
        sa.Column("created_at",        sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------ alert
    op.create_table(
        "alert",
        sa.Column("id",           sa.String(36), primary_key=True),
        sa.Column("asset_id",     sa.String(36), sa.ForeignKey("asset.id"), nullable=True),
        sa.Column("alert_type",   sa.String(32), nullable=False),
        sa.Column("condition",    sa.Text(),     nullable=False),
        sa.Column("is_active",    sa.Boolean(),  nullable=False, server_default=sa.text("true")),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------ job_schedule
    op.create_table(
        "job_schedule",
        sa.Column("id",          sa.String(36),  primary_key=True),
        sa.Column("name",        sa.String(128), nullable=False, unique=True),
        sa.Column("cron_expr",   sa.String(64),  nullable=False),
        sa.Column("enabled",     sa.Boolean(),   nullable=False, server_default=sa.text("true")),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------ job_run
    op.create_table(
        "job_run",
        sa.Column("id",               sa.String(36), primary_key=True),
        sa.Column("job_schedule_id",  sa.String(36),
                  sa.ForeignKey("job_schedule.id"), nullable=False),
        sa.Column("started_at",       sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("finished_at",      sa.DateTime(timezone=True), nullable=True),
        sa.Column("status",           sa.String(16), nullable=False, server_default="running"),
        sa.Column("error_message",    sa.Text(),     nullable=True),
        sa.Column("duration_seconds", EQUITY_NUM,   nullable=True),
    )
    op.create_index("ix_job_run_schedule_started_at",
                    "job_run", ["job_schedule_id", "started_at"])

    # ------------------------------------------------------------------ provider_raw_archive
    op.create_table(
        "provider_raw_archive",
        sa.Column("id",           sa.String(36),  primary_key=True),
        sa.Column("provider",     sa.String(32),  nullable=False),
        sa.Column("endpoint",     sa.String(512), nullable=False),
        sa.Column("params_hash",  sa.String(64),  nullable=False),
        sa.Column("content_hash", sa.String(64),  nullable=False),
        sa.Column("status_code",  sa.Integer(),   nullable=False),
        sa.Column("payload_blob", sa.Text(),      nullable=True),
        sa.Column("fetched_at",   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "provider", "endpoint", "params_hash", "content_hash",
            name="uq_raw_archive",
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_raw_archive")
    op.drop_index("ix_job_run_schedule_started_at", table_name="job_run")
    op.drop_table("job_run")
    op.drop_table("job_schedule")
    op.drop_table("alert")
    op.drop_table("recommendation_evidence")
    op.drop_index("ix_recommendation_asset_generated_at", table_name="recommendation")
    op.drop_table("recommendation")
    op.drop_table("position_snapshot")
    op.drop_table("lot_close")
    op.drop_table("lot")
    op.drop_index("ix_transaction_account_ts", table_name="transaction")
    op.drop_table("transaction")
    op.drop_table("account")
    op.drop_table("macro_series_observation")
    op.drop_table("fundamental_fact")
    op.drop_table("corporate_action")
    op.drop_index("ix_price_bar_asset_ts", table_name="price_bar")
    op.drop_table("price_bar")
    op.drop_index("ix_asset_symbol", table_name="asset")
    op.drop_table("asset")
