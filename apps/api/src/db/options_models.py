"""SQLAlchemy ORM models for the options paper-trading system (Phase 11B).

Hard-isolated from V2 / equity / governance / execution. Zero foreign
keys to non-`options_*` tables. Zero references to:
  * v2_promotion_*
  * paper_trade_log, decision_log, paper_shadow_log
  * engine_b*, shadow_strategy*
  * b2_v2_comparison

NEVER imports from any execution / routing / risk / strategy module.
Only stdlib + sqlalchemy + db.Base.

Spec: docs/research/OPTIONS_SYSTEM_DESIGN.md
      docs/research/OPTIONS_PAPER_TRADING_DESIGN.md
      docs/research/OPTIONS_BOUNDARIES.md
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.db import Base


# ---------------------------------------------------------------------------
# Frozen enum-like CHECK constraint values (mirror Phase 11A locks)
# ---------------------------------------------------------------------------

OPTION_TYPES = ("CALL", "PUT")
SIDES = ("BUY", "SELL")
TRADE_STATUSES = (
    "PROPOSED",
    "OPEN",
    "EXPIRING",
    "CLOSED",
    "EXPIRED",
    "ASSIGNED",
)
STRATEGY_NAMES = (
    "SHORT_PUT_CREDIT_SPREAD",
    "SHORT_CALL_CREDIT_SPREAD",
    "IRON_CONDOR",
)
LIFECYCLE_EVENT_TYPES = (
    "PROPOSED",
    "FILLED",
    "MTM",
    "EXPIRING_FLAGGED",
    "PIN_RISK_FLAGGED",
    "EARLY_ASSIGN_RISK",
    "CLOSED",
    "EXPIRED",
    "ASSIGNED",
    "FORCE_CLOSED",
)
LIFECYCLE_TRIGGER_SOURCES = (
    "SCHEDULED_JOB",
    "OPERATOR_API",
    "EXPIRATION_HANDLER",
    "ASSIGNMENT_HANDLER",
)
EXPIRATION_CLASSIFICATIONS = ("OTM", "ITM", "PIN_RISK", "MISSING_DATA")
ASSIGNMENT_EVENT_TYPES = (
    "EARLY_ASSIGN_RISK",
    "ASSIGNED",
    "EXERCISED",
    "FORCE_CLOSED_PRE_ASSIGN",
)
ASSIGNMENT_RISK_LEVELS = ("LOW", "MEDIUM", "HIGH")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ---------------------------------------------------------------------------
# 1. options_chain_snapshot
# ---------------------------------------------------------------------------

class OptionsChainSnapshot(Base):
    """Per-strike chain quote snapshot at point in time. Idempotent on
    (snapshot_at_utc, underlying, expiry, strike, option_type)."""

    __tablename__ = "options_chain_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_at_utc: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    underlying: Mapped[str] = mapped_column(Text, nullable=False)
    expiry: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    strike: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    option_type: Mapped[str] = mapped_column(Text, nullable=False)
    option_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    bid: Mapped[float | None] = mapped_column(Numeric(12, 4))
    ask: Mapped[float | None] = mapped_column(Numeric(12, 4))
    mid: Mapped[float | None] = mapped_column(Numeric(12, 4))
    last: Mapped[float | None] = mapped_column(Numeric(12, 4))
    volume: Mapped[int | None] = mapped_column(Integer)
    open_interest: Mapped[int | None] = mapped_column(Integer)
    delta: Mapped[float | None] = mapped_column(Numeric(12, 6))
    gamma: Mapped[float | None] = mapped_column(Numeric(12, 6))
    theta: Mapped[float | None] = mapped_column(Numeric(12, 6))
    vega: Mapped[float | None] = mapped_column(Numeric(12, 6))
    iv: Mapped[float | None] = mapped_column(Numeric(12, 6))
    quote_age_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "snapshot_at_utc", "underlying", "expiry", "strike", "option_type",
            name="ux_options_chain_snapshot_natural_key",
        ),
        CheckConstraint(
            _in("option_type", OPTION_TYPES),
            name="ck_options_chain_snapshot_option_type",
        ),
        CheckConstraint(
            "quote_age_seconds >= 0",
            name="ck_options_chain_snapshot_quote_age_nonneg",
        ),
        Index(
            "ix_options_chain_snapshot_underlying_snapshot_at_desc",
            "underlying", text("snapshot_at_utc DESC"),
        ),
        Index(
            "ix_options_chain_snapshot_underlying_expiry_strike_type",
            "underlying", "expiry", "strike", "option_type",
        ),
    )


# ---------------------------------------------------------------------------
# 2. options_feature_daily
# ---------------------------------------------------------------------------

class OptionsFeatureDaily(Base):
    """Daily computed features per underlying. Idempotent on
    (as_of_date, underlying)."""

    __tablename__ = "options_feature_daily"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    as_of_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    underlying: Mapped[str] = mapped_column(Text, nullable=False)
    iv_rank_252d: Mapped[float | None] = mapped_column(Numeric(8, 4))
    iv_percentile_252d: Mapped[float | None] = mapped_column(Numeric(8, 4))
    realized_vol_30d: Mapped[float | None] = mapped_column(Numeric(10, 6))
    vrp_30d: Mapped[float | None] = mapped_column(Numeric(10, 6))
    term_structure_30_60: Mapped[float | None] = mapped_column(Numeric(10, 6))
    skew_25d: Mapped[float | None] = mapped_column(Numeric(10, 6))
    put_call_oi_ratio: Mapped[float | None] = mapped_column(Numeric(10, 4))
    put_call_volume_ratio: Mapped[float | None] = mapped_column(Numeric(10, 4))
    # Phase 11D additive columns (migration 048)
    atm_iv: Mapped[float | None] = mapped_column(Numeric(10, 6))
    realized_vol_20d: Mapped[float | None] = mapped_column(Numeric(10, 6))
    term_structure_30_90: Mapped[float | None] = mapped_column(Numeric(10, 6))
    unusual_call_volume_z: Mapped[float | None] = mapped_column(Numeric(10, 4))
    unusual_put_volume_z: Mapped[float | None] = mapped_column(Numeric(10, 4))
    gamma_exposure_proxy: Mapped[float | None] = mapped_column(Numeric(20, 4))
    call_wall_strike: Mapped[float | None] = mapped_column(Numeric(12, 4))
    put_wall_strike: Mapped[float | None] = mapped_column(Numeric(12, 4))
    data_quality_flags: Mapped[list] = mapped_column(
        JSONB, nullable=False,
        default=list, server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "as_of_date", "underlying",
            name="ux_options_feature_daily_natural_key",
        ),
        Index(
            "ix_options_feature_daily_underlying_date_desc",
            "underlying", text("as_of_date DESC"),
        ),
    )


# ---------------------------------------------------------------------------
# 3. options_paper_trade
# ---------------------------------------------------------------------------

class OptionsPaperTrade(Base):
    """Multi-leg paper trade header. Paper-only invariant enforced at
    DB level via CHECK (paper_only = TRUE)."""

    __tablename__ = "options_paper_trade"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    underlying: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_name: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    entry_credit_dollars: Mapped[float | None] = mapped_column(Numeric(12, 4))
    exit_debit_dollars: Mapped[float | None] = mapped_column(Numeric(12, 4))
    realized_pnl_dollars: Mapped[float | None] = mapped_column(Numeric(12, 4))
    fees_total_dollars: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, default=0,
    )
    max_loss_dollars: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    max_profit_dollars: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    breakeven_lower: Mapped[float | None] = mapped_column(Numeric(12, 4))
    breakeven_upper: Mapped[float | None] = mapped_column(Numeric(12, 4))
    fill_model_version: Mapped[str] = mapped_column(Text, nullable=False)
    rollback_reason: Mapped[str | None] = mapped_column(Text)
    paper_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now,
        server_default=text("now()"),
    )

    legs: Mapped[list["OptionsPaperTradeLeg"]] = relationship(
        back_populates="trade",
        cascade="save-update, merge",
        passive_deletes=False,
    )
    lifecycle_events: Mapped[list["OptionsTradeLifecycleEvent"]] = relationship(
        back_populates="trade",
        cascade="save-update, merge",
        passive_deletes=False,
    )
    expiration_events: Mapped[list["OptionsExpirationEvent"]] = relationship(
        back_populates="trade",
        cascade="save-update, merge",
        passive_deletes=False,
    )
    assignment_events: Mapped[list["OptionsAssignmentEvent"]] = relationship(
        back_populates="trade",
        cascade="save-update, merge",
        passive_deletes=False,
    )

    __table_args__ = (
        CheckConstraint(
            _in("strategy_name", STRATEGY_NAMES),
            name="ck_options_paper_trade_strategy_name",
        ),
        CheckConstraint(
            _in("status", TRADE_STATUSES),
            name="ck_options_paper_trade_status",
        ),
        CheckConstraint(
            "paper_only = TRUE",
            name="ck_options_paper_trade_paper_only_invariant",
        ),
        CheckConstraint(
            "max_loss_dollars >= 0 AND max_profit_dollars >= 0",
            name="ck_options_paper_trade_minmax_nonneg",
        ),
        CheckConstraint(
            "fees_total_dollars >= 0",
            name="ck_options_paper_trade_fees_nonneg",
        ),
        Index("ix_options_paper_trade_status", "status"),
        Index("ix_options_paper_trade_strategy_name", "strategy_name"),
        Index("ix_options_paper_trade_opened_at_desc", text("opened_at DESC")),
        Index("ix_options_paper_trade_closed_at_desc", text("closed_at DESC")),
        Index(
            "ix_options_paper_trade_underlying_status",
            "underlying", "status",
        ),
    )


# ---------------------------------------------------------------------------
# 4. options_paper_trade_leg
# ---------------------------------------------------------------------------

class OptionsPaperTradeLeg(Base):
    """Per-leg detail. FK to options_paper_trade only; never references
    any equity / V2 table."""

    __tablename__ = "options_paper_trade_leg"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "options_paper_trade.id",
            ondelete="RESTRICT",
            name="fk_options_paper_trade_leg_trade",
        ),
        nullable=False,
    )
    leg_index: Mapped[int] = mapped_column(Integer, nullable=False)
    option_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    underlying: Mapped[str] = mapped_column(Text, nullable=False)
    expiry: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    strike: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    option_type: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    # entry snapshot (frozen at decision time)
    entry_quote_at_utc: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    entry_bid: Mapped[float | None] = mapped_column(Numeric(12, 4))
    entry_ask: Mapped[float | None] = mapped_column(Numeric(12, 4))
    entry_mid: Mapped[float | None] = mapped_column(Numeric(12, 4))
    entry_iv: Mapped[float | None] = mapped_column(Numeric(12, 6))
    entry_delta: Mapped[float | None] = mapped_column(Numeric(12, 6))
    entry_gamma: Mapped[float | None] = mapped_column(Numeric(12, 6))
    entry_theta: Mapped[float | None] = mapped_column(Numeric(12, 6))
    entry_vega: Mapped[float | None] = mapped_column(Numeric(12, 6))
    entry_fill_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    # exit (nullable until close)
    exit_quote_at_utc: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    exit_bid: Mapped[float | None] = mapped_column(Numeric(12, 4))
    exit_ask: Mapped[float | None] = mapped_column(Numeric(12, 4))
    exit_mid: Mapped[float | None] = mapped_column(Numeric(12, 4))
    exit_iv: Mapped[float | None] = mapped_column(Numeric(12, 6))
    exit_delta: Mapped[float | None] = mapped_column(Numeric(12, 6))
    exit_gamma: Mapped[float | None] = mapped_column(Numeric(12, 6))
    exit_theta: Mapped[float | None] = mapped_column(Numeric(12, 6))
    exit_vega: Mapped[float | None] = mapped_column(Numeric(12, 6))
    exit_fill_price: Mapped[float | None] = mapped_column(Numeric(12, 4))
    exit_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now,
        server_default=text("now()"),
    )

    trade: Mapped["OptionsPaperTrade"] = relationship(
        back_populates="legs",
    )

    __table_args__ = (
        UniqueConstraint(
            "trade_id", "leg_index",
            name="ux_options_paper_trade_leg_trade_index",
        ),
        CheckConstraint(
            _in("option_type", OPTION_TYPES),
            name="ck_options_paper_trade_leg_option_type",
        ),
        CheckConstraint(
            _in("side", SIDES),
            name="ck_options_paper_trade_leg_side",
        ),
        CheckConstraint(
            "qty > 0",
            name="ck_options_paper_trade_leg_qty_positive",
        ),
        Index("ix_options_paper_trade_leg_trade_id", "trade_id"),
        Index("ix_options_paper_trade_leg_option_symbol", "option_symbol"),
        Index("ix_options_paper_trade_leg_expiry", "expiry"),
    )


# ---------------------------------------------------------------------------
# 5. options_trade_lifecycle_event
# ---------------------------------------------------------------------------

class OptionsTradeLifecycleEvent(Base):
    """Append-only state-transition + observation log for paper trades."""

    __tablename__ = "options_trade_lifecycle_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "options_paper_trade.id",
            ondelete="RESTRICT",
            name="fk_options_trade_lifecycle_event_trade",
        ),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_at_utc: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )
    triggered_by: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )

    trade: Mapped["OptionsPaperTrade"] = relationship(
        back_populates="lifecycle_events",
    )

    __table_args__ = (
        CheckConstraint(
            _in("event_type", LIFECYCLE_EVENT_TYPES),
            name="ck_options_trade_lifecycle_event_event_type",
        ),
        CheckConstraint(
            _in("triggered_by", LIFECYCLE_TRIGGER_SOURCES),
            name="ck_options_trade_lifecycle_event_triggered_by",
        ),
        Index(
            "ix_options_trade_lifecycle_event_trade_event_at_desc",
            "trade_id", text("event_at_utc DESC"),
        ),
        Index("ix_options_trade_lifecycle_event_event_type", "event_type"),
    )


# ---------------------------------------------------------------------------
# 6. options_expiration_event
# ---------------------------------------------------------------------------

class OptionsExpirationEvent(Base):
    """Per-leg expiration outcome record. One row per (trade, leg, expiry_date)."""

    __tablename__ = "options_expiration_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "options_paper_trade.id",
            ondelete="RESTRICT",
            name="fk_options_expiration_event_trade",
        ),
        nullable=False,
    )
    leg_index: Mapped[int] = mapped_column(Integer, nullable=False)
    expiry_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    underlying_settlement: Mapped[float | None] = mapped_column(Numeric(12, 4))
    classification: Mapped[str] = mapped_column(Text, nullable=False)
    intrinsic_value_dollars: Mapped[float | None] = mapped_column(Numeric(12, 4))
    realized_pnl_dollars: Mapped[float | None] = mapped_column(Numeric(12, 4))
    event_at_utc: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )

    trade: Mapped["OptionsPaperTrade"] = relationship(
        back_populates="expiration_events",
    )

    __table_args__ = (
        UniqueConstraint(
            "trade_id", "leg_index", "expiry_date",
            name="ux_options_expiration_event_natural_key",
        ),
        CheckConstraint(
            _in("classification", EXPIRATION_CLASSIFICATIONS),
            name="ck_options_expiration_event_classification",
        ),
        Index("ix_options_expiration_event_trade_id", "trade_id"),
        Index("ix_options_expiration_event_expiry_date", "expiry_date"),
    )


# ---------------------------------------------------------------------------
# 7. options_assignment_event
# ---------------------------------------------------------------------------

class OptionsAssignmentEvent(Base):
    """Assignment risk + actual assignment / exercise records.

    NOTE v1: paper-only system does NOT create synthetic equity positions
    on assignment (per OPTIONS_PAPER_TRADING_DESIGN.md §8.3). This table
    records assignment events for audit + P&L finalization only.
    """

    __tablename__ = "options_assignment_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "options_paper_trade.id",
            ondelete="RESTRICT",
            name="fk_options_assignment_event_trade",
        ),
        nullable=False,
    )
    leg_index: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str | None] = mapped_column(Text)
    ex_div_date: Mapped[datetime.date | None] = mapped_column(Date)
    ex_div_amount: Mapped[float | None] = mapped_column(Numeric(12, 4))
    intrinsic_value_dollars: Mapped[float | None] = mapped_column(Numeric(12, 4))
    realized_pnl_dollars: Mapped[float | None] = mapped_column(Numeric(12, 4))
    event_at_utc: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )

    trade: Mapped["OptionsPaperTrade"] = relationship(
        back_populates="assignment_events",
    )

    __table_args__ = (
        CheckConstraint(
            _in("event_type", ASSIGNMENT_EVENT_TYPES),
            name="ck_options_assignment_event_event_type",
        ),
        CheckConstraint(
            "risk_level IS NULL OR " + _in("risk_level", ASSIGNMENT_RISK_LEVELS),
            name="ck_options_assignment_event_risk_level",
        ),
        Index("ix_options_assignment_event_trade_id", "trade_id"),
        Index("ix_options_assignment_event_event_type", "event_type"),
        Index(
            "ix_options_assignment_event_event_at_desc",
            text("event_at_utc DESC"),
        ),
    )


# ---------------------------------------------------------------------------
# 8. options_strategy_outcome  (Phase Options-Quality / migration 063)
# ---------------------------------------------------------------------------
# Append-only forward-return scoring of options strategy suggestions /
# paper trades. Read-only with respect to source tables. Mirrors
# 063_options_strategy_outcome.py; declared here so test harness
# (Base.metadata.create_all) builds the table.
OUTCOME_HORIZONS = ("1D", "3D", "5D", "10D", "20D")
OUTCOME_LABELS = ("good", "neutral", "bad", "pending", "data_blocked")
OUTCOME_SOURCES = ("suggestion", "paper_trade")
OUTCOME_MODES = ("strict", "exploratory", "options_exploratory")


class OptionsStrategyOutcome(Base):
    __tablename__ = "options_strategy_outcome"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    underlying: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_name: Mapped[str] = mapped_column(Text, nullable=False)
    legs_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    as_of_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False,
    )
    submitted_at_utc: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    horizon: Mapped[str] = mapped_column(Text, nullable=False)
    entry_reference: Mapped[float | None] = mapped_column(
        Numeric(14, 6),
    )
    exit_reference: Mapped[float | None] = mapped_column(
        Numeric(14, 6),
    )
    forward_return_pct: Mapped[float | None] = mapped_column(
        Numeric(14, 6),
    )
    mfe_pct: Mapped[float | None] = mapped_column(Numeric(14, 6))
    mae_pct: Mapped[float | None] = mapped_column(Numeric(14, 6))
    outcome_label: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at_utc: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "underlying", "strategy_name", "submitted_at_utc",
            "horizon", "source",
            name="ux_options_strategy_outcome_natural_key",
        ),
        CheckConstraint(
            _in("horizon", OUTCOME_HORIZONS),
            name="ck_options_strategy_outcome_horizon",
        ),
        CheckConstraint(
            _in("outcome_label", OUTCOME_LABELS),
            name="ck_options_strategy_outcome_label",
        ),
        CheckConstraint(
            _in("source", OUTCOME_SOURCES),
            name="ck_options_strategy_outcome_source",
        ),
        CheckConstraint(
            _in("mode", OUTCOME_MODES),
            name="ck_options_strategy_outcome_mode",
        ),
        Index(
            "ix_options_strategy_outcome_lookup",
            "as_of_date", "horizon", "mode",
        ),
        Index(
            "ix_options_strategy_outcome_underlying", "underlying",
        ),
    )
