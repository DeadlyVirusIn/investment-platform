"""Phase 11B — options paper-trading schema (NEW namespace, hard-isolated).

Adds 7 `options_*` tables for the new options paper-trading system:
  * options_chain_snapshot
  * options_feature_daily
  * options_paper_trade
  * options_paper_trade_leg
  * options_trade_lifecycle_event
  * options_expiration_event
  * options_assignment_event

Hard-isolated from V2 / equity / governance / execution per
docs/research/OPTIONS_BOUNDARIES.md:
  * ZERO foreign keys to non-`options_*` tables
  * ZERO references to v2_promotion_*, paper_trade_log, decision_log,
    paper_shadow_log, engine_b*, shadow_strategy*, b2_v2_comparison
  * paper_only invariant enforced at DB level via CHECK (paper_only = TRUE)
  * Strategy enum locked to {SHORT_PUT_CREDIT_SPREAD,
    SHORT_CALL_CREDIT_SPREAD, IRON_CONDOR}

NEVER touches existing equity / V2 tables. Pure additive migration.

Revision ID: 047_phase11b_options_schema
Revises: 046_v2_promotion_phase9a
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "047_phase11b_options_schema"
down_revision = "046_v2_promotion_phase9a"
branch_labels = None
depends_on = None


# Frozen enum values (mirror options_models.py constants)
_OPTION_TYPES = ("CALL", "PUT")
_SIDES = ("BUY", "SELL")
_TRADE_STATUSES = (
    "PROPOSED", "OPEN", "EXPIRING", "CLOSED", "EXPIRED", "ASSIGNED",
)
_STRATEGY_NAMES = (
    "SHORT_PUT_CREDIT_SPREAD",
    "SHORT_CALL_CREDIT_SPREAD",
    "IRON_CONDOR",
)
_LIFECYCLE_EVENT_TYPES = (
    "PROPOSED", "FILLED", "MTM", "EXPIRING_FLAGGED", "PIN_RISK_FLAGGED",
    "EARLY_ASSIGN_RISK", "CLOSED", "EXPIRED", "ASSIGNED", "FORCE_CLOSED",
)
_LIFECYCLE_TRIGGER_SOURCES = (
    "SCHEDULED_JOB", "OPERATOR_API",
    "EXPIRATION_HANDLER", "ASSIGNMENT_HANDLER",
)
_EXPIRATION_CLASSIFICATIONS = ("OTM", "ITM", "PIN_RISK", "MISSING_DATA")
_ASSIGNMENT_EVENT_TYPES = (
    "EARLY_ASSIGN_RISK", "ASSIGNED", "EXERCISED", "FORCE_CLOSED_PRE_ASSIGN",
)
_ASSIGNMENT_RISK_LEVELS = ("LOW", "MEDIUM", "HIGH")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    # ----- 1. options_chain_snapshot -----
    op.create_table(
        "options_chain_snapshot",
        sa.Column(
            "id", sa.BigInteger,
            sa.Identity(always=False, start=1),
            primary_key=True,
        ),
        sa.Column("snapshot_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("underlying", sa.Text, nullable=False),
        sa.Column("expiry", sa.Date, nullable=False),
        sa.Column("strike", sa.Numeric(12, 4), nullable=False),
        sa.Column("option_type", sa.Text, nullable=False),
        sa.Column("option_symbol", sa.Text, nullable=False),
        sa.Column("bid", sa.Numeric(12, 4)),
        sa.Column("ask", sa.Numeric(12, 4)),
        sa.Column("mid", sa.Numeric(12, 4)),
        sa.Column("last", sa.Numeric(12, 4)),
        sa.Column("volume", sa.Integer),
        sa.Column("open_interest", sa.Integer),
        sa.Column("delta", sa.Numeric(12, 6)),
        sa.Column("gamma", sa.Numeric(12, 6)),
        sa.Column("theta", sa.Numeric(12, 6)),
        sa.Column("vega", sa.Numeric(12, 6)),
        sa.Column("iv", sa.Numeric(12, 6)),
        sa.Column("quote_age_seconds", sa.Integer, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("provider_version", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "snapshot_at_utc", "underlying", "expiry", "strike", "option_type",
            name="ux_options_chain_snapshot_natural_key",
        ),
        sa.CheckConstraint(
            _in("option_type", _OPTION_TYPES),
            name="ck_options_chain_snapshot_option_type",
        ),
        sa.CheckConstraint(
            "quote_age_seconds >= 0",
            name="ck_options_chain_snapshot_quote_age_nonneg",
        ),
    )
    op.create_index(
        "ix_options_chain_snapshot_underlying_snapshot_at_desc",
        "options_chain_snapshot",
        ["underlying", sa.text("snapshot_at_utc DESC")],
    )
    op.create_index(
        "ix_options_chain_snapshot_underlying_expiry_strike_type",
        "options_chain_snapshot",
        ["underlying", "expiry", "strike", "option_type"],
    )

    # ----- 2. options_feature_daily -----
    op.create_table(
        "options_feature_daily",
        sa.Column(
            "id", sa.BigInteger,
            sa.Identity(always=False, start=1),
            primary_key=True,
        ),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("underlying", sa.Text, nullable=False),
        sa.Column("iv_rank_252d", sa.Numeric(8, 4)),
        sa.Column("iv_percentile_252d", sa.Numeric(8, 4)),
        sa.Column("realized_vol_30d", sa.Numeric(10, 6)),
        sa.Column("vrp_30d", sa.Numeric(10, 6)),
        sa.Column("term_structure_30_60", sa.Numeric(10, 6)),
        sa.Column("skew_25d", sa.Numeric(10, 6)),
        sa.Column("put_call_oi_ratio", sa.Numeric(10, 4)),
        sa.Column("put_call_volume_ratio", sa.Numeric(10, 4)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "as_of_date", "underlying",
            name="ux_options_feature_daily_natural_key",
        ),
    )
    op.create_index(
        "ix_options_feature_daily_underlying_date_desc",
        "options_feature_daily",
        ["underlying", sa.text("as_of_date DESC")],
    )

    # ----- 3. options_paper_trade -----
    op.create_table(
        "options_paper_trade",
        sa.Column(
            "id", sa.BigInteger,
            sa.Identity(always=False, start=1),
            primary_key=True,
        ),
        sa.Column("underlying", sa.Text, nullable=False),
        sa.Column("strategy_name", sa.Text, nullable=False),
        sa.Column("strategy_version", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("entry_credit_dollars", sa.Numeric(12, 4)),
        sa.Column("exit_debit_dollars", sa.Numeric(12, 4)),
        sa.Column("realized_pnl_dollars", sa.Numeric(12, 4)),
        sa.Column(
            "fees_total_dollars", sa.Numeric(12, 4),
            nullable=False, server_default=sa.text("0"),
        ),
        sa.Column("max_loss_dollars", sa.Numeric(12, 4), nullable=False),
        sa.Column("max_profit_dollars", sa.Numeric(12, 4), nullable=False),
        sa.Column("breakeven_lower", sa.Numeric(12, 4)),
        sa.Column("breakeven_upper", sa.Numeric(12, 4)),
        sa.Column("fill_model_version", sa.Text, nullable=False),
        sa.Column("rollback_reason", sa.Text),
        sa.Column(
            "paper_only", sa.Boolean,
            nullable=False, server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            _in("strategy_name", _STRATEGY_NAMES),
            name="ck_options_paper_trade_strategy_name",
        ),
        sa.CheckConstraint(
            _in("status", _TRADE_STATUSES),
            name="ck_options_paper_trade_status",
        ),
        sa.CheckConstraint(
            "paper_only = TRUE",
            name="ck_options_paper_trade_paper_only_invariant",
        ),
        sa.CheckConstraint(
            "max_loss_dollars >= 0 AND max_profit_dollars >= 0",
            name="ck_options_paper_trade_minmax_nonneg",
        ),
        sa.CheckConstraint(
            "fees_total_dollars >= 0",
            name="ck_options_paper_trade_fees_nonneg",
        ),
    )
    op.create_index("ix_options_paper_trade_status",
                      "options_paper_trade", ["status"])
    op.create_index("ix_options_paper_trade_strategy_name",
                      "options_paper_trade", ["strategy_name"])
    op.create_index(
        "ix_options_paper_trade_opened_at_desc",
        "options_paper_trade", [sa.text("opened_at DESC")],
    )
    op.create_index(
        "ix_options_paper_trade_closed_at_desc",
        "options_paper_trade", [sa.text("closed_at DESC")],
    )
    op.create_index(
        "ix_options_paper_trade_underlying_status",
        "options_paper_trade", ["underlying", "status"],
    )

    # ----- 4. options_paper_trade_leg -----
    op.create_table(
        "options_paper_trade_leg",
        sa.Column(
            "id", sa.BigInteger,
            sa.Identity(always=False, start=1),
            primary_key=True,
        ),
        sa.Column(
            "trade_id", sa.BigInteger,
            sa.ForeignKey(
                "options_paper_trade.id",
                ondelete="RESTRICT",
                name="fk_options_paper_trade_leg_trade",
            ),
            nullable=False,
        ),
        sa.Column("leg_index", sa.Integer, nullable=False),
        sa.Column("option_symbol", sa.Text, nullable=False),
        sa.Column("underlying", sa.Text, nullable=False),
        sa.Column("expiry", sa.Date, nullable=False),
        sa.Column("strike", sa.Numeric(12, 4), nullable=False),
        sa.Column("option_type", sa.Text, nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("entry_quote_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_bid", sa.Numeric(12, 4)),
        sa.Column("entry_ask", sa.Numeric(12, 4)),
        sa.Column("entry_mid", sa.Numeric(12, 4)),
        sa.Column("entry_iv", sa.Numeric(12, 6)),
        sa.Column("entry_delta", sa.Numeric(12, 6)),
        sa.Column("entry_gamma", sa.Numeric(12, 6)),
        sa.Column("entry_theta", sa.Numeric(12, 6)),
        sa.Column("entry_vega", sa.Numeric(12, 6)),
        sa.Column("entry_fill_price", sa.Numeric(12, 4), nullable=False),
        sa.Column("exit_quote_at_utc", sa.DateTime(timezone=True)),
        sa.Column("exit_bid", sa.Numeric(12, 4)),
        sa.Column("exit_ask", sa.Numeric(12, 4)),
        sa.Column("exit_mid", sa.Numeric(12, 4)),
        sa.Column("exit_iv", sa.Numeric(12, 6)),
        sa.Column("exit_delta", sa.Numeric(12, 6)),
        sa.Column("exit_gamma", sa.Numeric(12, 6)),
        sa.Column("exit_theta", sa.Numeric(12, 6)),
        sa.Column("exit_vega", sa.Numeric(12, 6)),
        sa.Column("exit_fill_price", sa.Numeric(12, 4)),
        sa.Column("exit_reason", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "trade_id", "leg_index",
            name="ux_options_paper_trade_leg_trade_index",
        ),
        sa.CheckConstraint(
            _in("option_type", _OPTION_TYPES),
            name="ck_options_paper_trade_leg_option_type",
        ),
        sa.CheckConstraint(
            _in("side", _SIDES),
            name="ck_options_paper_trade_leg_side",
        ),
        sa.CheckConstraint(
            "qty > 0",
            name="ck_options_paper_trade_leg_qty_positive",
        ),
    )
    op.create_index("ix_options_paper_trade_leg_trade_id",
                      "options_paper_trade_leg", ["trade_id"])
    op.create_index("ix_options_paper_trade_leg_option_symbol",
                      "options_paper_trade_leg", ["option_symbol"])
    op.create_index("ix_options_paper_trade_leg_expiry",
                      "options_paper_trade_leg", ["expiry"])

    # ----- 5. options_trade_lifecycle_event -----
    op.create_table(
        "options_trade_lifecycle_event",
        sa.Column(
            "id", sa.BigInteger,
            sa.Identity(always=False, start=1),
            primary_key=True,
        ),
        sa.Column(
            "trade_id", sa.BigInteger,
            sa.ForeignKey(
                "options_paper_trade.id",
                ondelete="RESTRICT",
                name="fk_options_trade_lifecycle_event_trade",
            ),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column(
            "event_at_utc", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("triggered_by", sa.Text, nullable=False),
        sa.Column(
            "payload_json", JSONB,
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            _in("event_type", _LIFECYCLE_EVENT_TYPES),
            name="ck_options_trade_lifecycle_event_event_type",
        ),
        sa.CheckConstraint(
            _in("triggered_by", _LIFECYCLE_TRIGGER_SOURCES),
            name="ck_options_trade_lifecycle_event_triggered_by",
        ),
    )
    op.create_index(
        "ix_options_trade_lifecycle_event_trade_event_at_desc",
        "options_trade_lifecycle_event",
        ["trade_id", sa.text("event_at_utc DESC")],
    )
    op.create_index(
        "ix_options_trade_lifecycle_event_event_type",
        "options_trade_lifecycle_event", ["event_type"],
    )

    # ----- 6. options_expiration_event -----
    op.create_table(
        "options_expiration_event",
        sa.Column(
            "id", sa.BigInteger,
            sa.Identity(always=False, start=1),
            primary_key=True,
        ),
        sa.Column(
            "trade_id", sa.BigInteger,
            sa.ForeignKey(
                "options_paper_trade.id",
                ondelete="RESTRICT",
                name="fk_options_expiration_event_trade",
            ),
            nullable=False,
        ),
        sa.Column("leg_index", sa.Integer, nullable=False),
        sa.Column("expiry_date", sa.Date, nullable=False),
        sa.Column("underlying_settlement", sa.Numeric(12, 4)),
        sa.Column("classification", sa.Text, nullable=False),
        sa.Column("intrinsic_value_dollars", sa.Numeric(12, 4)),
        sa.Column("realized_pnl_dollars", sa.Numeric(12, 4)),
        sa.Column(
            "event_at_utc", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "trade_id", "leg_index", "expiry_date",
            name="ux_options_expiration_event_natural_key",
        ),
        sa.CheckConstraint(
            _in("classification", _EXPIRATION_CLASSIFICATIONS),
            name="ck_options_expiration_event_classification",
        ),
    )
    op.create_index("ix_options_expiration_event_trade_id",
                      "options_expiration_event", ["trade_id"])
    op.create_index("ix_options_expiration_event_expiry_date",
                      "options_expiration_event", ["expiry_date"])

    # ----- 7. options_assignment_event -----
    op.create_table(
        "options_assignment_event",
        sa.Column(
            "id", sa.BigInteger,
            sa.Identity(always=False, start=1),
            primary_key=True,
        ),
        sa.Column(
            "trade_id", sa.BigInteger,
            sa.ForeignKey(
                "options_paper_trade.id",
                ondelete="RESTRICT",
                name="fk_options_assignment_event_trade",
            ),
            nullable=False,
        ),
        sa.Column("leg_index", sa.Integer, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("risk_level", sa.Text),
        sa.Column("ex_div_date", sa.Date),
        sa.Column("ex_div_amount", sa.Numeric(12, 4)),
        sa.Column("intrinsic_value_dollars", sa.Numeric(12, 4)),
        sa.Column("realized_pnl_dollars", sa.Numeric(12, 4)),
        sa.Column(
            "event_at_utc", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("notes", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            _in("event_type", _ASSIGNMENT_EVENT_TYPES),
            name="ck_options_assignment_event_event_type",
        ),
        sa.CheckConstraint(
            "risk_level IS NULL OR " + _in("risk_level", _ASSIGNMENT_RISK_LEVELS),
            name="ck_options_assignment_event_risk_level",
        ),
    )
    op.create_index("ix_options_assignment_event_trade_id",
                      "options_assignment_event", ["trade_id"])
    op.create_index("ix_options_assignment_event_event_type",
                      "options_assignment_event", ["event_type"])
    op.create_index(
        "ix_options_assignment_event_event_at_desc",
        "options_assignment_event",
        [sa.text("event_at_utc DESC")],
    )


def downgrade() -> None:
    # Reverse FK / dependency order
    op.drop_index(
        "ix_options_assignment_event_event_at_desc",
        table_name="options_assignment_event",
    )
    op.drop_index(
        "ix_options_assignment_event_event_type",
        table_name="options_assignment_event",
    )
    op.drop_index(
        "ix_options_assignment_event_trade_id",
        table_name="options_assignment_event",
    )
    op.drop_table("options_assignment_event")

    op.drop_index(
        "ix_options_expiration_event_expiry_date",
        table_name="options_expiration_event",
    )
    op.drop_index(
        "ix_options_expiration_event_trade_id",
        table_name="options_expiration_event",
    )
    op.drop_table("options_expiration_event")

    op.drop_index(
        "ix_options_trade_lifecycle_event_event_type",
        table_name="options_trade_lifecycle_event",
    )
    op.drop_index(
        "ix_options_trade_lifecycle_event_trade_event_at_desc",
        table_name="options_trade_lifecycle_event",
    )
    op.drop_table("options_trade_lifecycle_event")

    op.drop_index(
        "ix_options_paper_trade_leg_expiry",
        table_name="options_paper_trade_leg",
    )
    op.drop_index(
        "ix_options_paper_trade_leg_option_symbol",
        table_name="options_paper_trade_leg",
    )
    op.drop_index(
        "ix_options_paper_trade_leg_trade_id",
        table_name="options_paper_trade_leg",
    )
    op.drop_table("options_paper_trade_leg")

    op.drop_index(
        "ix_options_paper_trade_underlying_status",
        table_name="options_paper_trade",
    )
    op.drop_index(
        "ix_options_paper_trade_closed_at_desc",
        table_name="options_paper_trade",
    )
    op.drop_index(
        "ix_options_paper_trade_opened_at_desc",
        table_name="options_paper_trade",
    )
    op.drop_index(
        "ix_options_paper_trade_strategy_name",
        table_name="options_paper_trade",
    )
    op.drop_index(
        "ix_options_paper_trade_status",
        table_name="options_paper_trade",
    )
    op.drop_table("options_paper_trade")

    op.drop_index(
        "ix_options_feature_daily_underlying_date_desc",
        table_name="options_feature_daily",
    )
    op.drop_table("options_feature_daily")

    op.drop_index(
        "ix_options_chain_snapshot_underlying_expiry_strike_type",
        table_name="options_chain_snapshot",
    )
    op.drop_index(
        "ix_options_chain_snapshot_underlying_snapshot_at_desc",
        table_name="options_chain_snapshot",
    )
    op.drop_table("options_chain_snapshot")
