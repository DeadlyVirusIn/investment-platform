"""SQLAlchemy 2 ORM models for the investment-intelligence platform."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import (
    JSON,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

JSON_COL = JSON().with_variant(JSONB, "postgresql")
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.db import Base

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# Precision aliases per spec
# Crypto:   NUMERIC(28, 10)
# Equities: NUMERIC(20,  6)
CRYPTO_NUM  = Numeric(28, 10)
EQUITY_NUM  = Numeric(20, 6)


# ---------------------------------------------------------------------------
# asset
# ---------------------------------------------------------------------------

class Asset(Base):
    __tablename__ = "asset"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    symbol: Mapped[str]      = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(256))
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)   # equity | crypto | etf | …
    sector: Mapped[str | None] = mapped_column(String(32))                  # falls back to asset_class when NULL
    exchange: Mapped[str | None] = mapped_column(String(32))
    currency: Mapped[str]    = mapped_column(String(8), nullable=False, default="USD")
    is_active: Mapped[bool]  = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    __table_args__ = (UniqueConstraint("symbol", "exchange", name="uq_asset_symbol_exchange"),)

    price_bars: Mapped[list[PriceBar]] = relationship(back_populates="asset")
    corporate_actions: Mapped[list[CorporateAction]] = relationship(back_populates="asset")
    fundamental_facts: Mapped[list[FundamentalFact]] = relationship(back_populates="asset")


# ---------------------------------------------------------------------------
# price_bar
# ---------------------------------------------------------------------------

class PriceBar(Base):
    __tablename__ = "price_bar"

    id: Mapped[str]           = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str]     = mapped_column(String(36), ForeignKey("asset.id"), nullable=False)
    timeframe: Mapped[str]    = mapped_column(String(8), nullable=False)   # 1d | 1h | 15m …
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[object]      = mapped_column(EQUITY_NUM)
    high: Mapped[object]      = mapped_column(EQUITY_NUM)
    low: Mapped[object]       = mapped_column(EQUITY_NUM)
    close: Mapped[object]     = mapped_column(EQUITY_NUM)
    adjusted_close: Mapped[object | None] = mapped_column(EQUITY_NUM)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    provider: Mapped[str]     = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint("asset_id", "timeframe", "ts", "provider", name="uq_price_bar"),
    )

    asset: Mapped[Asset] = relationship(back_populates="price_bars")


# ---------------------------------------------------------------------------
# corporate_action
# ---------------------------------------------------------------------------

class CorporateAction(Base):
    __tablename__ = "corporate_action"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str]    = mapped_column(String(36), ForeignKey("asset.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)   # split | dividend | …
    ex_date: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ratio: Mapped[object | None]    = mapped_column(EQUITY_NUM)
    amount: Mapped[object | None]   = mapped_column(EQUITY_NUM)
    currency: Mapped[str | None]    = mapped_column(String(8))
    provider: Mapped[str]           = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    asset: Mapped[Asset] = relationship(back_populates="corporate_actions")


# ---------------------------------------------------------------------------
# fundamental_fact
# ---------------------------------------------------------------------------

class FundamentalFact(Base):
    __tablename__ = "fundamental_fact"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str]    = mapped_column(String(36), ForeignKey("asset.id"), nullable=False)
    period_end: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_type: Mapped[str] = mapped_column(String(8), nullable=False)    # annual | quarterly
    metric: Mapped[str]      = mapped_column(String(64), nullable=False)
    value: Mapped[object | None] = mapped_column(EQUITY_NUM)
    unit: Mapped[str | None] = mapped_column(String(32))
    provider: Mapped[str]    = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint(
            "asset_id", "period_end", "period_type", "metric", "provider",
            name="uq_fundamental_fact",
        ),
    )

    asset: Mapped[Asset] = relationship(back_populates="fundamental_facts")


# ---------------------------------------------------------------------------
# macro_series_observation
# ---------------------------------------------------------------------------

class MacroSeriesObservation(Base):
    __tablename__ = "macro_series_observation"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    series_id: Mapped[str]   = mapped_column(String(64), nullable=False)
    series_name: Mapped[str | None] = mapped_column(String(128))
    ts: Mapped[datetime.datetime]   = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[object | None]    = mapped_column(EQUITY_NUM)
    provider: Mapped[str]           = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint("series_id", "ts", "provider", name="uq_macro_obs"),
    )


# ---------------------------------------------------------------------------
# account
# ---------------------------------------------------------------------------

class Account(Base):
    __tablename__ = "account"

    id: Mapped[str]           = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str]         = mapped_column(String(128), nullable=False)
    broker: Mapped[str | None] = mapped_column(String(64))
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)  # taxable | ira | …
    currency: Mapped[str]     = mapped_column(String(8), nullable=False, default="USD")
    is_active: Mapped[bool]   = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    transactions: Mapped[list[Transaction]] = relationship(back_populates="account")
    position_snapshots: Mapped[list[PositionSnapshot]] = relationship(back_populates="account")


# ---------------------------------------------------------------------------
# transaction
# ---------------------------------------------------------------------------

class Transaction(Base):
    __tablename__ = "transaction"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    account_id: Mapped[str]  = mapped_column(String(36), ForeignKey("account.id"), nullable=False)
    asset_id: Mapped[str]    = mapped_column(String(36), ForeignKey("asset.id"), nullable=False)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action: Mapped[str]      = mapped_column(String(16), nullable=False)   # buy | sell | dividend …
    quantity: Mapped[object] = mapped_column(CRYPTO_NUM, nullable=False)   # use crypto precision for universal support
    price: Mapped[object]    = mapped_column(CRYPTO_NUM, nullable=False)
    fees: Mapped[object | None] = mapped_column(EQUITY_NUM)
    currency: Mapped[str]    = mapped_column(String(8), nullable=False, default="USD")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    account: Mapped[Account] = relationship(back_populates="transactions")
    lots: Mapped[list[Lot]] = relationship(back_populates="open_transaction")


# ---------------------------------------------------------------------------
# lot  (tax lot opened by a buy)
# ---------------------------------------------------------------------------

class Lot(Base):
    __tablename__ = "lot"

    id: Mapped[str]               = mapped_column(String(36), primary_key=True, default=_uuid)
    open_transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transaction.id"), nullable=False
    )
    asset_id: Mapped[str]         = mapped_column(String(36), ForeignKey("asset.id"), nullable=False)
    quantity_opened: Mapped[object] = mapped_column(CRYPTO_NUM, nullable=False)
    quantity_remaining: Mapped[object] = mapped_column(CRYPTO_NUM, nullable=False)
    cost_basis_per_unit: Mapped[object] = mapped_column(CRYPTO_NUM, nullable=False)
    currency: Mapped[str]         = mapped_column(String(8), nullable=False, default="USD")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    open_transaction: Mapped[Transaction] = relationship(back_populates="lots")
    closes: Mapped[list[LotClose]] = relationship(back_populates="lot")


# ---------------------------------------------------------------------------
# lot_close
# ---------------------------------------------------------------------------

class LotClose(Base):
    __tablename__ = "lot_close"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    lot_id: Mapped[str]      = mapped_column(String(36), ForeignKey("lot.id"), nullable=False)
    close_transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transaction.id"), nullable=False
    )
    quantity_closed: Mapped[object] = mapped_column(CRYPTO_NUM, nullable=False)
    proceeds_per_unit: Mapped[object] = mapped_column(CRYPTO_NUM, nullable=False)
    realized_pnl: Mapped[object | None] = mapped_column(EQUITY_NUM)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    lot: Mapped[Lot] = relationship(back_populates="closes")


# ---------------------------------------------------------------------------
# position_snapshot
# ---------------------------------------------------------------------------

class PositionSnapshot(Base):
    __tablename__ = "position_snapshot"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    account_id: Mapped[str]  = mapped_column(String(36), ForeignKey("account.id"), nullable=False)
    asset_id: Mapped[str]    = mapped_column(String(36), ForeignKey("asset.id"), nullable=False)
    snapshot_date: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[object] = mapped_column(CRYPTO_NUM, nullable=False)
    market_value: Mapped[object | None] = mapped_column(EQUITY_NUM)
    unrealized_pnl: Mapped[object | None] = mapped_column(EQUITY_NUM)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    account: Mapped[Account] = relationship(back_populates="position_snapshots")

    __table_args__ = (
        UniqueConstraint("account_id", "asset_id", "snapshot_date", name="uq_position_snapshot"),
    )


# ---------------------------------------------------------------------------
# recommendation
# ---------------------------------------------------------------------------

class Recommendation(Base):
    __tablename__ = "recommendation"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str]      = mapped_column(String(36), ForeignKey("asset.id"), nullable=False)
    generated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    action: Mapped[str]        = mapped_column(String(16), nullable=False)  # buy | sell | hold
    conviction: Mapped[object | None] = mapped_column(EQUITY_NUM)           # 0–100 confidence
    rationale: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(64))
    snapshot_hash: Mapped[str | None] = mapped_column(String(32))
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    evidence: Mapped[list[RecommendationEvidence]] = relationship(back_populates="recommendation")
    outcome: Mapped[RecommendationOutcome | None] = relationship(back_populates="recommendation")

    __table_args__ = (
        Index(
            "ux_recommendation_snap",
            "asset_id", "model_version", "snapshot_hash",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# recommendation_evidence
# ---------------------------------------------------------------------------

class RecommendationEvidence(Base):
    __tablename__ = "recommendation_evidence"

    id: Mapped[str]                 = mapped_column(String(36), primary_key=True, default=_uuid)
    recommendation_id: Mapped[str]  = mapped_column(
        String(36), ForeignKey("recommendation.id"), nullable=False
    )
    evidence_type: Mapped[str]      = mapped_column(String(32), nullable=False)
    source: Mapped[str | None]      = mapped_column(String(256))
    summary: Mapped[str | None]     = mapped_column(Text)
    weight: Mapped[object | None]   = mapped_column(EQUITY_NUM)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    recommendation: Mapped[Recommendation] = relationship(back_populates="evidence")


# ---------------------------------------------------------------------------
# recommendation_outcome
# ---------------------------------------------------------------------------


class RecommendationOutcome(Base):
    __tablename__ = "recommendation_outcome"

    id: Mapped[str]                  = mapped_column(String(36), primary_key=True, default=_uuid)
    recommendation_id: Mapped[str]   = mapped_column(
        String(36), ForeignKey("recommendation.id"), nullable=False, unique=True,
    )
    price_at_recommendation: Mapped[object | None] = mapped_column(EQUITY_NUM)
    price_after_30d: Mapped[object | None]         = mapped_column(EQUITY_NUM)
    price_after_90d: Mapped[object | None]         = mapped_column(EQUITY_NUM)
    realized_30d_return: Mapped[object | None]     = mapped_column(EQUITY_NUM)
    realized_90d_return: Mapped[object | None]     = mapped_column(EQUITY_NUM)
    barrier_label: Mapped[int | None]              = mapped_column(Integer)
    barrier_first_touch_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    barrier_n_bars: Mapped[int | None]             = mapped_column(Integer)
    signal_type: Mapped[str | None]                = mapped_column(String(24))
    suggested_size_pct: Mapped[object | None]      = mapped_column(EQUITY_NUM)
    suggested_stop_price: Mapped[object | None]    = mapped_column(EQUITY_NUM)
    trend_regime: Mapped[str | None]               = mapped_column(String(16))
    volatility_regime: Mapped[str | None]          = mapped_column(String(16))
    drawdown_regime: Mapped[str | None]            = mapped_column(String(16))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    recommendation: Mapped[Recommendation] = relationship(back_populates="outcome")


# ---------------------------------------------------------------------------
# paper_portfolio
# ---------------------------------------------------------------------------


class PaperPortfolio(Base):
    __tablename__ = "paper_portfolio"

    id: Mapped[str]              = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str]            = mapped_column(String(128), nullable=False, unique=True)
    starting_cash: Mapped[object] = mapped_column(EQUITY_NUM, nullable=False)
    cash: Mapped[object]         = mapped_column(EQUITY_NUM, nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool]      = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    positions: Mapped[list[PaperPosition]] = relationship(back_populates="portfolio")
    trades: Mapped[list[PaperTrade]] = relationship(back_populates="portfolio")


# ---------------------------------------------------------------------------
# paper_position
# ---------------------------------------------------------------------------


class PaperPosition(Base):
    __tablename__ = "paper_position"

    id: Mapped[str]              = mapped_column(String(36), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str]    = mapped_column(
        String(36), ForeignKey("paper_portfolio.id"), nullable=False
    )
    asset_id: Mapped[str]        = mapped_column(String(36), ForeignKey("asset.id"), nullable=False)
    quantity: Mapped[object]     = mapped_column(CRYPTO_NUM, nullable=False)
    avg_cost: Mapped[object]     = mapped_column(EQUITY_NUM, nullable=False)
    is_open: Mapped[bool]        = mapped_column(Boolean, nullable=False, default=True)
    opened_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    closed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
    # MP1S — executed-outcome attribution (migration 100). Forward-only,
    # nullable. opened_by_recommendation_id = entry-decision identity (the
    # rec that first opened this position); realized_pnl = executed P&L
    # accumulated at position level; opening/closed trade ids = entry/exit
    # provenance. Real ORM FKs are safe here (targets are in Base.metadata,
    # acyclic) — unlike the options side. Legacy rows stay NULL (no backfill).
    opened_by_recommendation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("recommendation.id", ondelete="SET NULL")
    )
    realized_pnl: Mapped[object | None] = mapped_column(EQUITY_NUM)
    opening_trade_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("paper_trade.id", ondelete="SET NULL")
    )
    closed_by_trade_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("paper_trade.id", ondelete="SET NULL")
    )

    portfolio: Mapped[PaperPortfolio] = relationship(back_populates="positions")

    __table_args__ = (
        Index("ix_paper_position_open",
              "portfolio_id", "asset_id", "is_open"),
        # MP1S attribution lookups (mirror migration 100 indexes).
        Index("ix_paper_position_opened_by_recommendation_id",
              "opened_by_recommendation_id"),
        Index("ix_paper_position_opening_trade_id", "opening_trade_id"),
        Index("ix_paper_position_closed_by_trade_id", "closed_by_trade_id"),
    )


# ---------------------------------------------------------------------------
# paper_trade
# ---------------------------------------------------------------------------


class PaperTrade(Base):
    __tablename__ = "paper_trade"

    id: Mapped[str]              = mapped_column(String(36), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str]    = mapped_column(
        String(36), ForeignKey("paper_portfolio.id"), nullable=False
    )
    asset_id: Mapped[str]        = mapped_column(String(36), ForeignKey("asset.id"), nullable=False)
    side: Mapped[str]            = mapped_column(String(8), nullable=False)   # buy | sell
    quantity: Mapped[object]     = mapped_column(CRYPTO_NUM, nullable=False)
    fill_price: Mapped[object]   = mapped_column(EQUITY_NUM, nullable=False)
    fill_ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    reason: Mapped[str | None]   = mapped_column(Text)
    recommendation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("recommendation.id")
    )
    realized_pnl: Mapped[object | None] = mapped_column(EQUITY_NUM)
    slippage_bps: Mapped[object | None] = mapped_column(Numeric(10, 4))
    commission: Mapped[object]          = mapped_column(
        Numeric(20, 6), nullable=False, default=Decimal("0"),
    )
    # Priority 3 hardening (migration 115) — durable cost-audit stamp: raw +
    # effective fill price, gross/commission/slippage/total/net (Decimal
    # strings) and the cost-model version + config that produced them. NULL
    # on the legacy zero-cost path and for callers baking their own costs.
    execution_cost_json: Mapped[dict | None] = mapped_column(JSON_COL)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    portfolio: Mapped[PaperPortfolio] = relationship(back_populates="trades")

    __table_args__ = (
        Index("ix_paper_trade_portfolio_ts", "portfolio_id", "fill_ts"),
    )


# ---------------------------------------------------------------------------
# paper_equity_snapshot
# ---------------------------------------------------------------------------


class PaperEquitySnapshot(Base):
    """Phase L M079 / P6D.35C — source-tagged equity snapshots.

    Truth contract (see docs/research/M083_CANONICAL_SEMANTIC.md):
      - `source='live'` is canonical truth for user-facing reads
      - replay/backfill/operator_manual are audit-only
      - P6D.35C: ONE row per (portfolio_id, snapshot_date, source);
        the writer UPSERTs (last writer wins within its own cell).
        Replay can never touch live rows — cells are isolated by source.
      - presentation immutability: user-facing readers MUST filter source='live'
    """
    __tablename__ = "paper_equity_snapshot"

    id: Mapped[str]              = mapped_column(String(36), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str]    = mapped_column(
        String(36), ForeignKey("paper_portfolio.id"), nullable=False
    )
    snapshot_date: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    cash: Mapped[object]         = mapped_column(EQUITY_NUM, nullable=False)
    positions_value: Mapped[object] = mapped_column(EQUITY_NUM, nullable=False)
    total_equity: Mapped[object] = mapped_column(EQUITY_NUM, nullable=False)
    unrealized_pnl: Mapped[object | None] = mapped_column(EQUITY_NUM)
    realized_pnl_cumulative: Mapped[object | None] = mapped_column(EQUITY_NUM)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    # Phase L M079: write timestamp (immutability anchor).
    recorded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    # Phase L M079: source discriminator (truth contract).
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="live")

    __table_args__ = (
        # P6D.35C (migration 094): one row per (portfolio, calendar date,
        # source). The writer (snapshot_equity_now) UPSERTs into this key —
        # last writer wins; recorded_at is the latest write time.
        UniqueConstraint(
            "portfolio_id", "snapshot_date", "source",
            name="uq_paper_equity_snapshot",
        ),
    )


# ---------------------------------------------------------------------------
# alert
# ---------------------------------------------------------------------------

class Alert(Base):
    __tablename__ = "alert"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("asset.id"))
    alert_type: Mapped[str]    = mapped_column(String(32), nullable=False)
    condition: Mapped[str]     = mapped_column(Text, nullable=False)        # JSON expression
    is_active: Mapped[bool]    = mapped_column(Boolean, nullable=False, default=True)
    triggered_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


# ---------------------------------------------------------------------------
# job_schedule
# ---------------------------------------------------------------------------

class JobSchedule(Base):
    __tablename__ = "job_schedule"

    id: Mapped[str]              = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str]            = mapped_column(String(128), nullable=False, unique=True)
    cron_expr: Mapped[str]       = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool]        = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    runs: Mapped[list[JobRun]] = relationship(back_populates="job_schedule")


# ---------------------------------------------------------------------------
# job_run
# ---------------------------------------------------------------------------

class JobRun(Base):
    __tablename__ = "job_run"

    id: Mapped[str]                = mapped_column(String(36), primary_key=True, default=_uuid)
    job_schedule_id: Mapped[str]   = mapped_column(
        String(36), ForeignKey("job_schedule.id"), nullable=False
    )
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str]            = mapped_column(String(16), nullable=False, default="running")
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[object | None] = mapped_column(EQUITY_NUM)

    job_schedule: Mapped[JobSchedule] = relationship(back_populates="runs")


# ---------------------------------------------------------------------------
# provider_raw_archive
# ---------------------------------------------------------------------------

class ProviderRawArchive(Base):
    __tablename__ = "provider_raw_archive"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str]      = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str]      = mapped_column(String(512), nullable=False)
    params_hash: Mapped[str]   = mapped_column(String(64), nullable=False)  # sha256 hex of params JSON
    content_hash: Mapped[str]  = mapped_column(String(64), nullable=False)  # sha256 hex of response body
    status_code: Mapped[int]   = mapped_column(Integer, nullable=False)
    payload_blob: Mapped[bytes | None] = mapped_column(Text)                # stored as utf-8 text or base64
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint("provider", "endpoint", "params_hash", "content_hash", name="uq_raw_archive"),
    )


# ---------------------------------------------------------------------------
# universe_membership — stock engine historical, point-in-time membership
# ---------------------------------------------------------------------------


class UniverseMembership(Base):
    __tablename__ = "universe_membership"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True, default=_uuid)
    universe_name: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_id: Mapped[str]      = mapped_column(
        String(36), ForeignKey("asset.id"), nullable=False,
    )
    start_date: Mapped[datetime.date]              = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime.date | None]         = mapped_column(Date)
    reason: Mapped[str | None]                     = mapped_column(String(64))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )

    __table_args__ = (
        Index("ix_um_universe_asset", "universe_name", "asset_id"),
        Index("ix_um_universe_active", "universe_name", "end_date"),
        Index(
            "ux_um_open_member",
            "universe_name", "asset_id",
            unique=True,
            postgresql_where=text("end_date IS NULL"),
        ),
    )


# ---------------------------------------------------------------------------
# regime_snapshot — daily market trend + volatility regime (SPY-driven)
# ---------------------------------------------------------------------------


class RegimeSnapshot(Base):
    __tablename__ = "regime_snapshot"

    as_of_date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    benchmark_symbol: Mapped[str]     = mapped_column(String(16), nullable=False)
    market_trend: Mapped[str]         = mapped_column(String(16), nullable=False)
    vol_regime: Mapped[str]           = mapped_column(String(16), nullable=False)
    breadth_regime: Mapped[str | None] = mapped_column(String(16))
    sma50_over_sma200: Mapped[bool]   = mapped_column(Boolean, nullable=False)
    realized_vol_20d: Mapped[object]  = mapped_column(EQUITY_NUM, nullable=False)
    atr_pctile_1y: Mapped[object]     = mapped_column(EQUITY_NUM, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )


# ---------------------------------------------------------------------------
# factor_snapshot — daily per-asset feature vector (stock engine)
# ---------------------------------------------------------------------------


class FactorSnapshot(Base):
    __tablename__ = "factor_snapshot"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True, default=_uuid)
    as_of_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    asset_id: Mapped[str]      = mapped_column(
        String(36), ForeignKey("asset.id"), nullable=False,
    )
    residual_momentum_20d: Mapped[object | None]   = mapped_column(EQUITY_NUM)
    residual_momentum_60d: Mapped[object | None]   = mapped_column(EQUITY_NUM)
    sector_relative_rank: Mapped[object | None]    = mapped_column(EQUITY_NUM)
    trend_strength_20d: Mapped[object | None]      = mapped_column(EQUITY_NUM)
    price_vs_200sma: Mapped[object | None]         = mapped_column(EQUITY_NUM)
    atr_percent_14: Mapped[object | None]          = mapped_column(EQUITY_NUM)
    earnings_proximity_days: Mapped[int | None]    = mapped_column(Integer)
    avg_dollar_volume_20d: Mapped[object | None]   = mapped_column(Numeric(20, 2))
    feature_set_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    enough_data: Mapped[bool]  = mapped_column(Boolean, nullable=False, default=True)
    stale_data: Mapped[bool]   = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )

    __table_args__ = (
        Index("ux_factor_snapshot", "as_of_date", "asset_id", unique=True),
        Index("ix_factor_snapshot_date", "as_of_date"),
    )


# ---------------------------------------------------------------------------
# candidate_idea — per-asset daily evaluation log (stock engine)
# ---------------------------------------------------------------------------


class CandidateIdea(Base):
    __tablename__ = "candidate_idea"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True, default=_uuid)
    as_of_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    asset_id: Mapped[str]      = mapped_column(
        String(36), ForeignKey("asset.id"), nullable=False,
    )
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    engine: Mapped[str]        = mapped_column(String(32), nullable=False, default="stock_swing")
    status: Mapped[str]        = mapped_column(String(16), nullable=False)
    action: Mapped[str | None] = mapped_column(String(16))
    rejection_reason: Mapped[str | None] = mapped_column(String(64))
    composite_score: Mapped[object | None] = mapped_column(EQUITY_NUM)
    confidence: Mapped[object | None]      = mapped_column(EQUITY_NUM)
    factor_breakdown: Mapped[dict]         = mapped_column(JSON_COL, nullable=False, default=dict)
    regime_snapshot: Mapped[dict]          = mapped_column(JSON_COL, nullable=False, default=dict)
    recommendation_id: Mapped[str | None]  = mapped_column(String(36))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )

    __table_args__ = (
        Index(
            "ux_candidate_idea",
            "as_of_date", "asset_id", "model_version",
            unique=True,
        ),
        Index("ix_candidate_status", "as_of_date", "status"),
        Index(
            "ix_candidate_reject",
            "rejection_reason",
            postgresql_where=text("status = 'rejected'"),
        ),
    )


# ---------------------------------------------------------------------------
# watchlist — lightweight v1 (no user scoping; single-user system)
# ---------------------------------------------------------------------------


class Watchlist(Base):
    __tablename__ = "watchlist"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )


# ---------------------------------------------------------------------------
# app_setting — key/value app configuration persisted across restarts
# ---------------------------------------------------------------------------


class AppSetting(Base):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now,
    )


# ---------------------------------------------------------------------------
# news_item + news_symbol_map — News Intelligence Layer
# ---------------------------------------------------------------------------


class NewsItem(Base):
    __tablename__ = "news_item"

    id: Mapped[str]              = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str]          = mapped_column(String(32), nullable=False)
    url: Mapped[str]             = mapped_column(Text, nullable=False)
    url_hash: Mapped[str]        = mapped_column(String(40), nullable=False)
    title: Mapped[str]           = mapped_column(Text, nullable=False)
    summary: Mapped[str | None]  = mapped_column(Text)
    published_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    category: Mapped[str]        = mapped_column(String(24), nullable=False)
    sentiment: Mapped[str]       = mapped_column(String(16), nullable=False)
    sentiment_score: Mapped[object] = mapped_column(Numeric(6, 3), nullable=False)
    impact_level: Mapped[str]    = mapped_column(String(8), nullable=False)
    impact_score: Mapped[int]    = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSON_COL)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )

    __table_args__ = (
        Index("ux_news_url_hash", "url_hash", unique=True),
        Index("ix_news_published_at", "published_at"),
        Index("ix_news_category", "category"),
    )


class NewsSymbolMap(Base):
    __tablename__ = "news_symbol_map"

    news_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("news_item.id", ondelete="CASCADE"),
        primary_key=True,
    )
    symbol: Mapped[str]  = mapped_column(String(32), primary_key=True)

    __table_args__ = (
        Index("ix_news_symbol_map_symbol", "symbol"),
    )


# ---------------------------------------------------------------------------
# historical_label — ML research phase (Phase 1)
# ---------------------------------------------------------------------------


class HistoricalLabel(Base):
    __tablename__ = "historical_label"

    id: Mapped[str]                 = mapped_column(String(36), primary_key=True, default=_uuid)
    as_of_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    asset_id: Mapped[str]           = mapped_column(
        String(36), ForeignKey("asset.id"), nullable=False,
    )
    symbol: Mapped[str]             = mapped_column(String(32), nullable=False)
    engine_version: Mapped[str]     = mapped_column(String(64), nullable=False)
    action: Mapped[str]             = mapped_column(String(16), nullable=False)
    composite_score: Mapped[object | None] = mapped_column(EQUITY_NUM)
    confidence: Mapped[object | None]      = mapped_column(EQUITY_NUM)

    residual_momentum_20d: Mapped[object | None] = mapped_column(EQUITY_NUM)
    residual_momentum_60d: Mapped[object | None] = mapped_column(EQUITY_NUM)
    sector_relative_rank: Mapped[object | None]  = mapped_column(EQUITY_NUM)
    trend_strength_20d: Mapped[object | None]    = mapped_column(EQUITY_NUM)
    price_vs_200sma: Mapped[object | None]       = mapped_column(EQUITY_NUM)
    atr_percent_14: Mapped[object | None]        = mapped_column(EQUITY_NUM)
    avg_dollar_volume_20d: Mapped[object | None] = mapped_column(Numeric(20, 2))

    market_trend: Mapped[str | None]    = mapped_column(String(16))
    vol_regime: Mapped[str | None]      = mapped_column(String(16))
    realized_vol_20d: Mapped[object | None] = mapped_column(EQUITY_NUM)
    atr_pctile_1y: Mapped[object | None]    = mapped_column(EQUITY_NUM)

    label: Mapped[int]                      = mapped_column(Integer, nullable=False)
    forward_return_pct: Mapped[object]      = mapped_column(EQUITY_NUM, nullable=False)
    barrier_first_touch_bar: Mapped[int | None] = mapped_column(Integer)
    barrier_n_bars: Mapped[int]             = mapped_column(Integer, nullable=False)
    entry_price: Mapped[object]             = mapped_column(EQUITY_NUM, nullable=False)
    exit_price: Mapped[object]              = mapped_column(EQUITY_NUM, nullable=False)
    pt_price: Mapped[object]                = mapped_column(EQUITY_NUM, nullable=False)
    sl_price: Mapped[object]                = mapped_column(EQUITY_NUM, nullable=False)
    sector: Mapped[str | None]              = mapped_column(String(32))
    raw_payload: Mapped[dict | None]        = mapped_column(JSON_COL)
    created_at: Mapped[datetime.datetime]   = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )

    __table_args__ = (
        Index(
            "ux_historical_label",
            "as_of_date", "asset_id", "engine_version",
            unique=True,
        ),
        Index("ix_historical_label_date", "as_of_date"),
        Index("ix_historical_label_symbol", "symbol"),
        Index("ix_historical_label_engine", "engine_version"),
    )


# ---------------------------------------------------------------------------
# daily_run_status — live-forward orchestrator durable run log
# ---------------------------------------------------------------------------


class DailyRunStatus(Base):
    __tablename__ = "daily_run_status"

    run_date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success | failed | skipped | running
    stage_failed: Mapped[str | None] = mapped_column(String(64))
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_json: Mapped[dict | None] = mapped_column(JSON_COL)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now,
    )

    __table_args__ = (
        Index("ix_daily_run_status_status", "status"),
    )


# ---------------------------------------------------------------------------
# action_item — Decision UX v1. Materialized overlay on candidate_idea +
# exit_rules + portfolio state. Read-only from auto_trader's perspective.
# ---------------------------------------------------------------------------


class ActionItem(Base):
    __tablename__ = "action_item"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    as_of_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    kind: Mapped[str]           = mapped_column(String(16), nullable=False)
    asset_id: Mapped[str]       = mapped_column(
        String(36), ForeignKey("asset.id"), nullable=False,
    )
    symbol: Mapped[str]         = mapped_column(String(32), nullable=False)
    sector: Mapped[str | None]  = mapped_column(String(32))
    candidate_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("candidate_idea.id"),
    )
    priority: Mapped[object]    = mapped_column(Numeric(5, 2), nullable=False)
    priority_tier: Mapped[str]  = mapped_column(String(8), nullable=False)
    urgency: Mapped[str]        = mapped_column(String(16), nullable=False)
    confidence: Mapped[object | None]      = mapped_column(Numeric(5, 2))
    composite_score: Mapped[object | None] = mapped_column(Numeric(10, 6))
    rationale_short: Mapped[str]           = mapped_column(Text, nullable=False)
    factor_top: Mapped[list | None]        = mapped_column(JSON_COL)
    impact_estimate: Mapped[dict | None]   = mapped_column(JSON_COL)
    decay_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    dependencies: Mapped[dict]  = mapped_column(JSON_COL, nullable=False, default=dict)
    origin: Mapped[str]         = mapped_column(String(24), nullable=False)
    status: Mapped[str]         = mapped_column(String(16), nullable=False, default="pending")
    acted_trade_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("paper_trade.id"),
    )
    acted_at: Mapped[datetime.datetime | None]     = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    dismiss_reason: Mapped[str | None]             = mapped_column(String(64))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now,
    )

    __table_args__ = (
        Index("ix_action_status_priority", "status", "priority"),
        Index("ix_action_asof_kind", "as_of_date", "kind"),
        Index("ix_action_asset", "asset_id", "status"),
        Index(
            "ux_action_dedup",
            "as_of_date", "asset_id", "kind", "origin",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# signal — canonical multi-model signal table (Phase 1 foundation).
# Write target for model adapters; write-only in Phase 1.
# ---------------------------------------------------------------------------


class Signal(Base):
    __tablename__ = "signal"

    signal_id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    as_of_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    asset_id: Mapped[str]         = mapped_column(
        String(36), ForeignKey("asset.id"), nullable=False,
    )
    symbol: Mapped[str]           = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str]        = mapped_column(String(8), nullable=False, default="1d")
    strategy_id: Mapped[str]      = mapped_column(String(64), nullable=False)
    model_family: Mapped[str]     = mapped_column(String(32), nullable=False)
    model_version: Mapped[str]    = mapped_column(String(64), nullable=False)
    features_version: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_direction: Mapped[str] = mapped_column(String(8), nullable=False)
    signal_strength: Mapped[object] = mapped_column(Numeric(6, 4), nullable=False)
    confidence: Mapped[object]    = mapped_column(Numeric(6, 4), nullable=False)
    expected_return: Mapped[object | None]   = mapped_column(Numeric(10, 6))
    expected_drawdown: Mapped[object | None] = mapped_column(Numeric(10, 6))
    holding_period_bars: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[object | None] = mapped_column(Numeric(6, 4))
    regime_tag: Mapped[str | None]    = mapped_column(String(24))
    raw_payload_ref: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )

    __table_args__ = (
        Index(
            "ux_signal_dedup",
            "as_of_date", "asset_id", "strategy_id", unique=True,
        ),
        Index("ix_signal_as_of_date", "as_of_date"),
        Index("ix_signal_strategy", "strategy_id"),
    )


# ---------------------------------------------------------------------------
# signal_outcome — realized outcome per signal. Phase 1 write-only.
# ---------------------------------------------------------------------------


class SignalOutcome(Base):
    __tablename__ = "signal_outcome"

    id: Mapped[str]               = mapped_column(String(36), primary_key=True, default=_uuid)
    signal_id: Mapped[str]        = mapped_column(
        String(36),
        ForeignKey("signal.signal_id", ondelete="CASCADE"),
        nullable=False,
    )
    signal_direction: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_price: Mapped[object]   = mapped_column(Numeric(20, 6), nullable=False)
    realized_return: Mapped[object] = mapped_column(Numeric(10, 6), nullable=False)
    max_drawdown: Mapped[object | None] = mapped_column(Numeric(10, 6))
    outcome_label: Mapped[str]    = mapped_column(String(16), nullable=False)
    evaluation_timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )

    __table_args__ = (
        Index("ux_signal_outcome_signal", "signal_id", unique=True),
        Index("ix_signal_outcome_eval_ts", "evaluation_timestamp"),
    )


# ---------------------------------------------------------------------------
# model_scorecard — Phase 2 read-only analytics. Ranker ignores.
# ---------------------------------------------------------------------------


class ModelScorecard(Base):
    __tablename__ = "model_scorecard"

    id: Mapped[str]           = mapped_column(String(36), primary_key=True, default=_uuid)
    model_name: Mapped[str]   = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    window_end: Mapped[datetime.date]   = mapped_column(Date, nullable=False)
    total_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_rate: Mapped[object | None]         = mapped_column(Numeric(6, 4))
    avg_return: Mapped[object | None]       = mapped_column(Numeric(10, 6))
    avg_drawdown: Mapped[object | None]     = mapped_column(Numeric(10, 6))
    sharpe_like_metric: Mapped[object | None] = mapped_column(Numeric(10, 4))
    avg_days_to_evaluation: Mapped[object | None] = mapped_column(Numeric(8, 2))
    max_days_to_evaluation: Mapped[int | None]    = mapped_column(Integer)
    pct_within_horizon: Mapped[object | None]     = mapped_column(Numeric(6, 4))
    calibration: Mapped[list | None]              = mapped_column(JSON_COL)
    factor_effectiveness: Mapped[list | None]     = mapped_column(JSON_COL)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )

    __table_args__ = (
        Index(
            "ux_scorecard_dedup",
            "model_name", "window_start", "window_end", unique=True,
        ),
        Index("ix_scorecard_window_end", "window_end"),
    )


# ---------------------------------------------------------------------------
# ranked_signal — Phase 1.5 canonical shadow-ranker output.
# ---------------------------------------------------------------------------


class RankedSignalRow(Base):
    __tablename__ = "ranked_signal"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True, default=_uuid)
    as_of_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    asset_id: Mapped[str]      = mapped_column(String(36), nullable=False)
    symbol: Mapped[str]        = mapped_column(String(32), nullable=False)
    score: Mapped[object]      = mapped_column(Numeric(10, 6), nullable=False)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_id: Mapped[str]   = mapped_column(String(64), nullable=False)
    contributing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict | None] = mapped_column(JSON_COL)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )

    __table_args__ = (
        Index("ix_ranked_signal_as_of_date", "as_of_date"),
        Index(
            "ux_ranked_signal_dedup",
            "as_of_date", "strategy_id", "rank_position",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# shadow_run_log — one row per daily pipeline run, for cutover tracking.
# ---------------------------------------------------------------------------


class ShadowRunLog(Base):
    __tablename__ = "shadow_run_log"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True, default=_uuid)
    as_of_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    signals_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ranked_count: Mapped[int]  = mapped_column(Integer, nullable=False, default=0)
    runtime_ms: Mapped[int | None] = mapped_column(Integer)
    diff_status: Mapped[str | None]   = mapped_column(String(16))      # ok | fail | not_run
    diff_reason: Mapped[str | None]   = mapped_column(String(64))
    reorder_count: Mapped[int | None] = mapped_column(Integer)
    asset_set_match: Mapped[bool | None] = mapped_column(Boolean)
    topn_match: Mapped[bool | None]      = mapped_column(Boolean)
    max_score_delta: Mapped[object | None] = mapped_column(Numeric(10, 6))
    failing_symbols: Mapped[list | None]   = mapped_column(JSON_COL)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )

    __table_args__ = (
        Index("ix_shadow_run_log_as_of_date", "as_of_date"),
        Index("ux_shadow_run_log_day", "as_of_date", unique=True),
    )


# ---------------------------------------------------------------------------
# Phase 10 — event-data infrastructure (raw + normalized + quarantine)
# ---------------------------------------------------------------------------


class RawEarningsIngestion(Base):
    """Raw feed payload for earnings calendar entries. INSERT-only."""
    __tablename__ = "event_raw_earnings"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str]    = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256))
    ingested_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    status: Mapped[str]    = mapped_column(String(16), nullable=False, default="pending")
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON_COL)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    __table_args__ = (
        Index("ix_event_raw_earnings_source", "source"),
        Index("ix_event_raw_earnings_ingested_ts", "ingested_ts"),
        Index("ix_event_raw_earnings_content_hash", "content_hash"),
        UniqueConstraint("source", "external_id",
                         name="ux_event_raw_earnings_source_extid"),
        UniqueConstraint("source", "content_hash",
                         name="ux_event_raw_earnings_source_content_hash"),
    )


class RawSharesIngestion(Base):
    __tablename__ = "event_raw_shares"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str]    = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256))
    ingested_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    status: Mapped[str]    = mapped_column(String(16), nullable=False, default="pending")
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON_COL)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    __table_args__ = (
        Index("ix_event_raw_shares_source", "source"),
        Index("ix_event_raw_shares_ingested_ts", "ingested_ts"),
        Index("ix_event_raw_shares_content_hash", "content_hash"),
        UniqueConstraint("source", "external_id",
                         name="ux_event_raw_shares_source_extid"),
        UniqueConstraint("source", "content_hash",
                         name="ux_event_raw_shares_source_content_hash"),
    )


class RawConsensusIngestion(Base):
    __tablename__ = "event_raw_consensus"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str]    = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256))
    ingested_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    status: Mapped[str]    = mapped_column(String(16), nullable=False, default="pending")
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON_COL)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    __table_args__ = (
        Index("ix_event_raw_consensus_source", "source"),
        Index("ix_event_raw_consensus_ingested_ts", "ingested_ts"),
        Index("ix_event_raw_consensus_content_hash", "content_hash"),
        UniqueConstraint("source", "external_id",
                         name="ux_event_raw_consensus_source_extid"),
        UniqueConstraint("source", "content_hash",
                         name="ux_event_raw_consensus_source_content_hash"),
    )


class EarningsEventRow(Base):
    __tablename__ = "earnings_event"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str]  = mapped_column(String(36), nullable=False)
    symbol: Mapped[str]    = mapped_column(String(32), nullable=False)
    event_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    event_time: Mapped[str] = mapped_column(String(16), nullable=False)
    announcement_timestamp: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    announcement_timestamp_raw: Mapped[str | None] = mapped_column(String(128))
    fiscal_period: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str]    = mapped_column(String(64), nullable=False)
    ingested_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    updated_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now,
    )

    __table_args__ = (
        UniqueConstraint("asset_id", "event_date", name="ux_earnings_event_asset_date"),
        Index("ix_earnings_event_event_date", "event_date"),
        Index("ix_earnings_event_symbol_date", "symbol", "event_date"),
    )


class SharesOutstandingRow(Base):
    __tablename__ = "shares_outstanding"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str]  = mapped_column(String(36), nullable=False)
    symbol: Mapped[str]    = mapped_column(String(32), nullable=False)
    effective_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    filing_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    shares_outstanding: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str]    = mapped_column(String(64), nullable=False)
    ingested_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    updated_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now,
    )

    __table_args__ = (
        UniqueConstraint(
            "asset_id", "effective_date", "source",
            name="ux_shares_outstanding_asset_effective_source",
        ),
        Index("ix_shares_outstanding_symbol_filing", "symbol", "filing_date"),
        Index("ix_shares_outstanding_asset_filing", "asset_id", "filing_date"),
    )


class ConsensusEstimateRow(Base):
    __tablename__ = "consensus_estimate"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str]  = mapped_column(String(36), nullable=False)
    symbol: Mapped[str]    = mapped_column(String(32), nullable=False)
    event_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    metric: Mapped[str]    = mapped_column(String(16), nullable=False)
    estimate_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[object]  = mapped_column(Numeric(20, 6), nullable=False)
    # Phase 10.6: unit metadata (canonical + original preserved for audit)
    value_unit: Mapped[str | None] = mapped_column(String(32))
    original_value: Mapped[object | None] = mapped_column(Numeric(20, 6))
    original_unit: Mapped[str | None] = mapped_column(String(32))
    as_of_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    source: Mapped[str]    = mapped_column(String(64), nullable=False)
    ingested_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    # Phase 10.6: content_hash (informational on normalized; raw-table hash is the dedupe guard)
    content_hash: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint(
            "asset_id", "event_date", "metric", "estimate_type",
            "as_of_date", "source",
            name="ux_consensus_estimate_natural_key",
        ),
        Index(
            "ix_consensus_estimate_lookup",
            "asset_id", "event_date", "metric", "estimate_type", "as_of_date",
        ),
        Index("ix_consensus_estimate_content_hash", "content_hash"),
    )


class EventQuarantine(Base):
    __tablename__ = "event_quarantine"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str]    = mapped_column(String(64), nullable=False)
    raw_ingestion_id: Mapped[str | None] = mapped_column(String(36))
    reason: Mapped[str]    = mapped_column(String(128), nullable=False)
    reason_detail: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON_COL)
    quarantined_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )

    __table_args__ = (
        Index("ix_event_quarantine_source_type", "source_type"),
        Index("ix_event_quarantine_quarantined_ts", "quarantined_ts"),
        Index("ix_event_quarantine_reason", "reason"),
    )


# ---------------------------------------------------------------------------
# V2 promotion-trigger framework — Phase 1 (schema + persistence only)
# Governance layer above the advisory B2 vs V2 comparison framework.
# Read-only audit surface. NEVER touches paper_trade_log, decision_log,
# paper_shadow_log, or any production execution surface.
# Spec: docs/research/V2_PROMOTION_TRIGGER_DESIGN.md
# ---------------------------------------------------------------------------


_V2_PROMOTION_STATES = (
    "NOT_READY",
    "SUSPENDED",
    "WATCH",
    "READY_FOR_REVIEW",
    "STRONG_CANDIDATE",
    "APPROVED_FOR_SHADOW_REPLACEMENT",
)

_V2_PROMOTION_DECISIONS = ("APPROVE", "RESCIND", "RESUME_FROM_SUSPENDED")


class V2PromotionSnapshot(Base):
    """Weekly immutable snapshot of the V2 promotion-trigger state machine."""

    __tablename__ = "v2_promotion_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    as_of_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    iso_year: Mapped[int] = mapped_column(Integer, nullable=False)
    iso_week: Mapped[int] = mapped_column(Integer, nullable=False)
    comparison_bundle_json: Mapped[dict] = mapped_column(
        JSON_COL, nullable=False,
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    prior_state: Mapped[str | None] = mapped_column(Text)
    promotion_confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False,
    )
    gates_json: Mapped[dict] = mapped_column(
        JSON_COL, nullable=False, default=dict,
    )
    verdict_streak: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    readiness_streak: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    rollback_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    # Phase 9A — governance hardening
    snapshot_content_hash: Mapped[str | None] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
    )
    code_version: Mapped[str | None] = mapped_column(Text)
    evaluated_at_utc: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    timezone: Mapped[str | None] = mapped_column(Text)

    approvals: Mapped[list["V2PromotionApproval"]] = relationship(
        back_populates="snapshot",
        cascade="save-update, merge",
        passive_deletes=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "iso_year", "iso_week",
            name="ux_v2_promotion_snapshot_iso_week",
        ),
        Index(
            "ix_v2_promotion_snapshot_as_of_date_desc",
            text("as_of_date DESC"),
        ),
        Index(
            "ix_v2_promotion_snapshot_state",
            "state",
        ),
        Index(
            "ix_v2_promotion_snapshot_content_hash",
            "snapshot_content_hash",
        ),
    )


class V2PromotionApproval(Base):
    """Operator-written approval / rescission row for a snapshot."""

    __tablename__ = "v2_promotion_approval"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "v2_promotion_snapshot.id",
            ondelete="RESTRICT",
            name="fk_v2_promotion_approval_snapshot",
        ),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    approver: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    # Phase 9A — bind approval to exact snapshot evidence
    snapshot_content_hash_at_approval: Mapped[str | None] = mapped_column(
        String(64),
    )

    snapshot: Mapped["V2PromotionSnapshot"] = relationship(
        back_populates="approvals",
    )

    __table_args__ = (
        Index(
            "ix_v2_promotion_approval_snapshot_id",
            "snapshot_id",
        ),
        Index(
            "ix_v2_promotion_approval_approved_at_desc",
            text("approved_at DESC"),
        ),
    )


# ---------------------------------------------------------------------------
# Phase 11P — paper observation labels (forward-return labels for ML)
# Append-only. NEVER references strict-engine tables. NEVER references
# v2_promotion_*, engine_b_*, paper_trade_log, decision_log directly
# (uuid foreign-key column is by id only — no FK constraint to keep
# this table fully isolated from the strict execution path).
# ---------------------------------------------------------------------------

class PaperObservationLabel(Base):
    __tablename__ = "paper_observation_label"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)

    paper_decision_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    paper_trade_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
    )
    options_paper_trade_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
    )
    options_observation_id: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    entry_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    failed_gates: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"),
    )
    gate_snapshot: Mapped[dict] = mapped_column(
        JSON_COL, nullable=False, server_default=text("'{}'::jsonb"),
    )

    entry_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True,
    )

    return_1d:  Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    return_3d:  Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    return_5d:  Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    return_10d: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    return_20d: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)

    max_adverse_excursion: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6), nullable=True,
    )
    max_favorable_excursion: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6), nullable=True,
    )

    outcome_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_threshold_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True,
    )
    label_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True,
    )

    label_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'label-v1.0.0'"),
    )
    computed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )
    is_provisional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        server_default=text("TRUE"),
    )

    __table_args__ = (
        UniqueConstraint(
            "domain", "paper_decision_log_id", "label_version",
            name="uq_paper_observation_label_decision",
        ),
        UniqueConstraint(
            "domain", "paper_trade_id", "label_version",
            name="uq_paper_observation_label_paper_trade",
        ),
        UniqueConstraint(
            "domain", "options_paper_trade_id", "label_version",
            name="uq_paper_observation_label_options_paper_trade",
        ),
        UniqueConstraint(
            "domain", "options_observation_id", "label_version",
            name="uq_paper_observation_label_options_observation",
        ),
        Index(
            "ix_paper_observation_label_entry_date", "entry_date",
        ),
        Index(
            "ix_paper_observation_label_domain_source",
            "domain", "source",
        ),
        Index(
            "ix_paper_observation_label_provisional",
            "is_provisional",
            postgresql_where=text("is_provisional"),
        ),
    )


# ---------------------------------------------------------------------------
# Phase 11R — paper research fast-fill rows.
# Hard-isolated from strict engine. Append-only. NEVER references
# paper_trade / paper_position / decision_log / paper_portfolio.
# CHECK constraints encode isolation invariants.
# ---------------------------------------------------------------------------

class PaperResearchFill(Base):
    __tablename__ = "paper_research_fill"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source: Mapped[str] = mapped_column(
        Text, nullable=False,
        server_default=text("'research_fast_fill'"),
    )
    fill_model: Mapped[str] = mapped_column(
        Text, nullable=False,
        server_default=text("'same_day_research_v1'"),
    )
    label_version: Mapped[str] = mapped_column(
        Text, nullable=False,
        server_default=text("'research-fast-fill-v1.0.0'"),
    )
    ml_label_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE"),
    )
    strict_fill_model_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE"),
    )

    decision_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    as_of_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False,
    )
    underlying: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    engine: Mapped[str | None] = mapped_column(Text, nullable=True)
    side: Mapped[str] = mapped_column(Text, nullable=False)

    fill_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False,
    )
    fill_price_source: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    fill_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    qty: Mapped[Decimal] = mapped_column(
        Numeric(28, 10), nullable=False,
    )

    gate_snapshot: Mapped[dict] = mapped_column(
        JSON_COL, nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    failed_gates: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False,
        server_default=text("'{}'::text[]"),
    )
    audit_jsonl_path: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    computed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "source", "as_of_date", "underlying", "rule_id",
            "side", "fill_model", "label_version",
            name="uq_paper_research_fill_natural_key",
        ),
        Index(
            "ix_paper_research_fill_as_of_date", "as_of_date",
        ),
        Index(
            "ix_paper_research_fill_underlying", "underlying",
        ),
        # Isolation invariants — encoded at DB level.
        CheckConstraint(
            "source = 'research_fast_fill'",
            name="ck_paper_research_fill_source",
        ),
        CheckConstraint(
            "strict_fill_model_used = FALSE",
            name="ck_paper_research_fill_strict_off",
        ),
        CheckConstraint(
            "fill_price_source IN ('open','vwap','close')",
            name="ck_paper_research_fill_price_source",
        ),
        CheckConstraint(
            "side IN ('BUY','SELL')",
            name="ck_paper_research_fill_side",
        ),
    )


# ---------------------------------------------------------------------------
# Phase F4 — Agent insight cache (read-only research).
#
# Isolated cache for /api/insights/{kind} responses. Has NO foreign
# keys to trading / paper / options / decision / replay tables and
# is NEVER referenced by execution paths. Cache hits short-circuit
# the LLM call; misses write a single row only after the response
# passes pre- and post-call safety gates.
# ---------------------------------------------------------------------------

class AgentInsight(Base):
    __tablename__ = "agent_insight"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=_uuid,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    payload_redacted: Mapped[dict] = mapped_column(
        JSON_COL, nullable=False,
    )
    content_markdown: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    source_endpoint: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    banner: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=_now, server_default=text("now()"),
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    safety_version: Mapped[str] = mapped_column(
        Text, nullable=False, default="v1",
        server_default="v1",
    )

    __table_args__ = (
        UniqueConstraint(
            "kind", "payload_hash", "model", "safety_version",
            name="ux_agent_insight_natural_key",
        ),
        CheckConstraint(
            "kind IN ('trade_quality', 'risk_commentary', "
            "'exit_review', 'options_thesis')",
            name="ck_agent_insight_kind",
        ),
        CheckConstraint(
            "banner = 'AI research insight — not execution logic.'",
            name="ck_agent_insight_banner",
        ),
        CheckConstraint(
            "length(content_markdown) > 0",
            name="ck_agent_insight_content_nonempty",
        ),
        Index(
            "ix_agent_insight_lookup",
            "kind", "payload_hash", "model", "safety_version",
        ),
    )


# ---------------------------------------------------------------------------
# pipeline_run — Phase 15i.A canonical operational truth ledger.
#
# One row per (trading_date, stage, run_id). The `run_id` UUID groups all
# stages of a single orchestrator pass; rerunning a stage is modelled by
# issuing a fresh `run_id` (NOT by mutating an existing row).
#
# WRITE STATUS: nothing in production currently writes to this table.
# The class is exposed so future orchestrator code (Phase 15i.B) can
# populate rows without a further schema change. The Phase 15i.C
# `/api/freshness` endpoint reads this ledger plus the existing
# source-of-truth tables (`recommendation`, `paper_run_log`,
# `paper_equity_snapshot`, `ml_model_run`, `options_chain_snapshot`).
# ---------------------------------------------------------------------------


class PipelineRun(Base):
    """Append-only ledger row for one stage of one orchestrator pass.

    See `infra/alembic/versions/065_pipeline_run_ledger.py` for the
    authoritative DDL. This class is the canonical SQLAlchemy view —
    NO production code path writes to this table yet. Reading is
    safe; writing should be confined to a future single orchestrator
    so the `(trading_date, stage, run_id)` invariant holds.
    """

    __tablename__ = "pipeline_run"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False,
    )
    trading_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False,
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    # 'pending' | 'running' | 'success' | 'failed' | 'skipped'
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    # 'cron' | 'tickloop' | 'manual' | 'orchestrator'
    triggered_by: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"),
    )
    error_class: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    input_watermark: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    output_watermark: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    rows_read: Mapped[int | None] = mapped_column(BigInteger)
    rows_written: Mapped[int | None] = mapped_column(BigInteger)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    # SQLAlchemy reserves the `metadata` attribute on declarative
    # classes, so we expose the column as `meta` in Python while
    # mapping to the `metadata` column on disk.
    meta: Mapped[dict] = mapped_column(
        "metadata", JSON_COL,
        nullable=False, default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False, default=_now, server_default=text("now()"),
    )

    __table_args__ = (
        Index(
            "uq_pipeline_run_trading_stage_runid",
            "trading_date", "stage", "run_id",
            unique=True,
        ),
        Index(
            "uq_pipeline_run_idempotency",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_pipeline_run_trading_date",
            text("trading_date DESC"),
        ),
        Index(
            "ix_pipeline_run_stage_status",
            "stage", "status",
        ),
        Index(
            "ix_pipeline_run_run_id",
            "run_id",
        ),
    )


# ---------------------------------------------------------------------------
# Phase 16 Phase 2 — intraday ML shadow layer (data collection only).
# Created by migration 066_intraday_observation.py.
# Writes are gated by INTRADAY_ML_SHADOW_ENABLED (default False).
# Sole writer: apps.api.src.ml.intraday.observation_writer.write_observation().
# No trainer / scorer / UI consume these rows yet.
# ---------------------------------------------------------------------------


def _uuid_str() -> str:
    return str(uuid.uuid4())


class IntradayObservation(Base):
    __tablename__ = "intraday_observation"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid_str,
    )
    recommendation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recommendation.id"), nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_at_15min: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    # Quantitative features
    intraday_change_pct:         Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    vs_open_pct:                 Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    vs_recommendation_entry_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    vs_macro_drift_pct:          Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    intraday_range_pct:          Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    spy_change_pct:              Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    qqq_change_pct:              Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    dia_change_pct:              Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    # Categorical features
    time_of_day_bucket:   Mapped[str] = mapped_column(String(16), nullable=False)
    prior_eod_conviction: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    action_type:          Mapped[str] = mapped_column(String(8), nullable=False)
    position_state:       Mapped[str] = mapped_column(String(16), nullable=False)

    # 60d daily-derived features
    atr_60d_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    vol_60d_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    sector_id:   Mapped[str | None]     = mapped_column(String(64))

    # Provenance
    source:         Mapped[str]                       = mapped_column(String(16), nullable=False)
    delay_minutes:  Mapped[int]                       = mapped_column(Integer, nullable=False)
    quote_ts:       Mapped[datetime.datetime | None]  = mapped_column(DateTime(timezone=True))
    feature_hash:   Mapped[str]                       = mapped_column(String(32), nullable=False)
    created_at:     Mapped[datetime.datetime]         = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint(
            "recommendation_id", "observed_at_15min",
            name="uq_intraday_obs_rec_slot",
        ),
        Index(
            "ix_intraday_obs_symbol_time",
            "symbol", text("observed_at_15min DESC"),
        ),
        Index(
            "ix_intraday_obs_observed",
            text("observed_at_15min DESC"),
        ),
    )


# ---------------------------------------------------------------------------
# MVP — model portfolios ("Ideas you can follow and prove")
# ---------------------------------------------------------------------------

class ModelPortfolio(Base):
    """A curated, follow-able portfolio: a thesis + a set of weighted holdings.
    Track record is computed from the price panel into ModelPortfolioPerf."""
    __tablename__ = "model_portfolio"

    id: Mapped[str]   = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    thesis: Mapped[str | None] = mapped_column(Text)
    risk_label: Mapped[str | None] = mapped_column(String(32))   # conservative | balanced | growth
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    holdings: Mapped[list[ModelPortfolioHolding]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class ModelPortfolioHolding(Base):
    __tablename__ = "model_portfolio_holding"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    model_portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_portfolio.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    weight: Mapped[object] = mapped_column(EQUITY_NUM, nullable=False)   # 0..1 fraction

    portfolio: Mapped[ModelPortfolio] = relationship(back_populates="holdings")

    __table_args__ = (
        UniqueConstraint("model_portfolio_id", "symbol", name="uq_model_holding"),
    )


class ModelPortfolioPerf(Base):
    """Cached daily track record (equity curve) for a model portfolio."""
    __tablename__ = "model_portfolio_perf"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    model_portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_portfolio.id", ondelete="CASCADE"), nullable=False
    )
    d: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    nav: Mapped[object]    = mapped_column(EQUITY_NUM, nullable=False)   # indexed to 1.0 at start
    ret: Mapped[object | None] = mapped_column(EQUITY_NUM)               # daily return
    computed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint("model_portfolio_id", "d", name="uq_model_perf_day"),
        Index("ix_model_perf_pf_day", "model_portfolio_id", text("d DESC")),
    )


class PortfolioFollow(Base):
    """Links a user's paper portfolio to the model portfolio it mirrors."""
    __tablename__ = "portfolio_follow"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(64))   # nullable until auth lands
    model_portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_portfolio.id", ondelete="CASCADE"), nullable=False
    )
    paper_portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("paper_portfolio.id", ondelete="CASCADE"), nullable=False
    )
    followed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        Index("ix_follow_model", "model_portfolio_id"),
        Index("ix_follow_user", "user_id"),
    )



class ResearchRun(Base):
    """Elite ArthOS Sprint 5 — reproducible experiment ledger (migration
    109). Rows freeze once terminal (app-enforced; DB CHECKs pin the
    terminal invariants); promotion decisions live in
    research_run_approval, never as in-place edits."""

    __tablename__ = "research_run"

    id: Mapped[str]           = mapped_column(String(36), primary_key=True, default=_uuid)
    run_uid: Mapped[str]      = mapped_column(String(32), nullable=False, unique=True)
    run_type: Mapped[str]     = mapped_column(String(32), nullable=False)
    name: Mapped[str]         = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str]       = mapped_column(String(16), nullable=False, default="draft")
    git_sha: Mapped[str]      = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64))
    feature_schema_version: Mapped[str | None] = mapped_column(String(64))
    data_start: Mapped[datetime.date | None] = mapped_column(Date)
    data_end: Mapped[datetime.date | None]   = mapped_column(Date)
    data_hash: Mapped[str | None]   = mapped_column(String(64))
    config_hash: Mapped[str]  = mapped_column(String(64), nullable=False)
    random_seed: Mapped[int | None] = mapped_column(BigInteger)
    split_method: Mapped[str | None] = mapped_column(String(32))
    parameters: Mapped[dict]  = mapped_column(JSON_COL, nullable=False, default=dict)
    metrics: Mapped[dict]     = mapped_column(JSON_COL, nullable=False, default=dict)
    artifact_manifest: Mapped[list] = mapped_column(JSON_COL, nullable=False, default=list)
    parent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_run.id", ondelete="RESTRICT")
    )
    promotion_status: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    promoted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime.datetime | None]  = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str]   = mapped_column(String(64), nullable=False, default="owner")
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchRunApproval(Base):
    """Append-only promotion decisions for research runs (migration 109).
    Never UPDATE or DELETE rows — corrections are new rows; FK RESTRICT
    keeps decided-on runs undeletable."""

    __tablename__ = "research_run_approval"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str]    = mapped_column(
        String(36), ForeignKey("research_run.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str]  = mapped_column(String(16), nullable=False)
    approver: Mapped[str]  = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    run_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


# ---------------------------------------------------------------------------
# Thesis Ledger — Elite ArthOS Sprint 6 (migrations 110 + 111)
# ---------------------------------------------------------------------------
# A thesis is one durable, plain-English belief with a MANDATORY falsifier
# (`wrong_if`). Evidence (stance supports|contradicts), catalysts, risks and
# polymorphic links attach to it; every thesis mutation appends an immutable
# ThesisRevision row. Status changes flow through
# apps/api/src/domain/thesis/service.py ONLY (transition table there) — never
# auto-mutated from generated content. All FKs are ON DELETE RESTRICT: no
# cascade path can silently destroy history.
# Spec: docs/architecture/THESIS_LEDGER_SPEC.md

class Thesis(Base):
    """One belief, not a recommendation. `wrong_if` is required at creation
    (DB CHECK: > 10 chars) — ArthOS never holds a belief without a stated
    falsifier. Revived ideas are NEW rows via supersedes_thesis_id; history
    is never rewritten (no un-invalidating, no transition out of closed)."""

    __tablename__ = "thesis"

    id: Mapped[str]              = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("asset.id"))
    scope: Mapped[str]           = mapped_column(String(16), nullable=False, default="company")
    title: Mapped[str]           = mapped_column(String(200), nullable=False)
    statement: Mapped[str]       = mapped_column(Text, nullable=False)
    wrong_if: Mapped[str]        = mapped_column(Text, nullable=False)
    horizon: Mapped[str]         = mapped_column(String(16), nullable=False, default="months")
    status: Mapped[str]          = mapped_column(String(16), nullable=False, default="forming")
    status_reason: Mapped[str | None] = mapped_column(Text)
    status_changed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_reason: Mapped[str | None] = mapped_column(Text)
    supersedes_thesis_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("thesis.id", ondelete="RESTRICT")
    )
    created_by: Mapped[str]      = mapped_column(String(64), nullable=False, default="owner")
    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime.datetime | None]    = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    __table_args__ = (
        CheckConstraint(
            "scope IN ('company','sector','theme','macro')",
            name="ck_thesis_scope",
        ),
        CheckConstraint(
            "status IN ('forming','active','strengthened','weakened',"
            "'invalidated','closed')",
            name="ck_thesis_status",
        ),
        CheckConstraint(
            "horizon IN ('weeks','months','quarters','years')",
            name="ck_thesis_horizon",
        ),
        CheckConstraint(
            "char_length(wrong_if) > 10",
            name="ck_thesis_wrong_if_len",
        ),
        CheckConstraint(
            "status <> 'invalidated' OR invalidated_reason IS NOT NULL",
            name="ck_thesis_invalidated",
        ),
        CheckConstraint(
            "scope <> 'company' OR asset_id IS NOT NULL",
            name="ck_thesis_company_asset",
        ),
        Index("ix_thesis_asset", "asset_id"),
        Index("ix_thesis_status", "status"),
    )

    evidence: Mapped[list[ThesisEvidence]] = relationship(back_populates="thesis")
    catalysts: Mapped[list[ThesisCatalyst]] = relationship(back_populates="thesis")
    risks: Mapped[list[ThesisRisk]] = relationship(back_populates="thesis")
    links: Mapped[list[ThesisLink]] = relationship(back_populates="thesis")
    revisions: Mapped[list[ThesisRevision]] = relationship(back_populates="thesis")


class ThesisEvidence(Base):
    """Durable belief evidence with provenance + human review. Counter-
    evidence is NOT a separate entity — it is a row with
    stance='contradicts'. Generated rows MUST carry source_url and always
    start review_status='pending' (forced server-side); rows are immutable
    after insert except the three review fields. Rejected rows are kept —
    no delete path."""

    __tablename__ = "thesis_evidence"

    id: Mapped[str]         = mapped_column(String(36), primary_key=True, default=_uuid)
    thesis_id: Mapped[str]  = mapped_column(
        String(36), ForeignKey("thesis.id", ondelete="RESTRICT"), nullable=False
    )
    stance: Mapped[str]      = mapped_column(String(16), nullable=False)
    category: Mapped[str]    = mapped_column(String(16), nullable=False)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    summary: Mapped[str]     = mapped_column(Text, nullable=False)
    weight: Mapped[object | None] = mapped_column(Numeric(5, 4))
    provenance: Mapped[str]  = mapped_column(String(16), nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(64))
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint(
            "stance IN ('supports','contradicts')",
            name="ck_thesis_evidence_stance",
        ),
        CheckConstraint(
            "category IN ('price_action','fundamentals','news','analyst',"
            "'macro','other')",
            name="ck_thesis_evidence_category",
        ),
        CheckConstraint(
            "provenance IN ('generated','human')",
            name="ck_thesis_evidence_provenance",
        ),
        CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="ck_thesis_evidence_review",
        ),
        CheckConstraint(
            "weight IS NULL OR (weight >= 0 AND weight <= 1)",
            name="ck_thesis_evidence_weight",
        ),
        # generated evidence must carry a source URL — provenance rule at
        # the DB layer
        CheckConstraint(
            "provenance <> 'generated' OR source_url IS NOT NULL",
            name="ck_thesis_evidence_gen_url",
        ),
        # reviewed rows must say who/when
        CheckConstraint(
            "review_status = 'pending' "
            "OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_thesis_evidence_reviewed",
        ),
        Index("ix_thesis_evidence_thesis", "thesis_id", "review_status"),
        Index(
            "ix_thesis_evidence_pending", "review_status",
            postgresql_where=text("review_status = 'pending'"),
        ),
    )

    thesis: Mapped[Thesis] = relationship(back_populates="evidence")


class ThesisRevision(Base):
    """Immutable revision history — the service appends one row on EVERY
    thesis mutation (create + every status transition). NO update or delete
    path exists anywhere; corrections are new thesis mutations which append
    new revisions. snapshot = {statement, status, wrong_if, status_reason}
    as of the mutation."""

    __tablename__ = "thesis_revision"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    thesis_id: Mapped[str]   = mapped_column(
        String(36), ForeignKey("thesis.id", ondelete="RESTRICT"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict]   = mapped_column(JSON_COL, nullable=False)
    changed_by: Mapped[str]  = mapped_column(String(64), nullable=False, default="owner")
    changed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint("thesis_id", "revision_no", name="uq_thesis_revision_no"),
        CheckConstraint("revision_no >= 1", name="ck_thesis_revision_no"),
        Index("ix_thesis_revision_thesis", "thesis_id", text("revision_no DESC")),
    )

    thesis: Mapped[Thesis] = relationship(back_populates="revisions")


class ThesisCatalyst(Base):
    """What could move this thesis, with an optional expected window.
    No deletes; resolution is data."""

    __tablename__ = "thesis_catalyst"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    thesis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("thesis.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str]     = mapped_column(String(200), nullable=False)
    expected_at: Mapped[datetime.date | None] = mapped_column(Date)
    window_days: Mapped[int | None] = mapped_column(Integer)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="either")
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint(
            "direction IN ('helps','hurts','either')",
            name="ck_thesis_catalyst_direction",
        ),
        Index("ix_thesis_catalyst_thesis", "thesis_id"),
    )

    thesis: Mapped[Thesis] = relationship(back_populates="catalysts")


class ThesisRisk(Base):
    """What could hurt this thesis, severity-tagged. `materialized_at` is
    set when the risk actually happened. No deletes."""

    __tablename__ = "thesis_risk"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    thesis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("thesis.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str]     = mapped_column(String(200), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str]  = mapped_column(String(8), nullable=False, default="medium")
    materialized_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('low','medium','high')",
            name="ck_thesis_risk_severity",
        ),
        Index("ix_thesis_risk_thesis", "thesis_id"),
    )

    thesis: Mapped[Thesis] = relationship(back_populates="risks")


class ThesisLink(Base):
    """Polymorphic link. Deliberately NO hard FK on target_id: targets span
    recommendation / paper_trade / recommendation_outcome today and a future
    `lesson` table (Learning Loop M9). Follows the PaperObservationLabel
    precedent: id-only reference keeps this table isolated from the strict
    execution path. Existence is validated in the service layer at link
    time."""

    __tablename__ = "thesis_link"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    thesis_id: Mapped[str]   = mapped_column(
        String(36), ForeignKey("thesis.id", ondelete="RESTRICT"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[str]   = mapped_column(String(36), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('recommendation','paper_trade','outcome','lesson')",
            name="ck_thesis_link_type",
        ),
        UniqueConstraint("thesis_id", "target_type", "target_id", name="uq_thesis_link"),
        Index("ix_thesis_link_target", "target_type", "target_id"),
    )

    thesis: Mapped[Thesis] = relationship(back_populates="links")


# ---------------------------------------------------------------------------
# Research Inbox — Elite ArthOS (migration 112)
# ---------------------------------------------------------------------------
# A research_task is one durable standing question; every execution delivers
# a versioned, IMMUTABLE research_report. Delivered reports are frozen: the
# only post-delivery writes are the review fields, moved exclusively through
# apps/api/src/domain/research_inbox/service.py. Corrections NEVER edit a
# delivered row — they insert version+1 with supersedes_report_id set.
# Staleness (fresh|stale|superseded) is derived at read time from
# expires_at / citation observed_at age / a superseding row — never stored.
# `schedule_expr` is a cron DEFINITION only; nothing executes it in this
# slice (scheduler wiring is a separate, approval-gated change).
# Spec: docs/architecture/RESEARCH_INBOX_SPEC.md

class ResearchTask(Base):
    """One standing research question (scope = symbols CSV or theme text).
    Follow-up questions link back via follow_up_of_task_id (RESTRICT — the
    provenance chain never breaks). Closing a task keeps it and every
    report forever."""

    __tablename__ = "research_task"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str]         = mapped_column(String(200), nullable=False)
    question: Mapped[str]      = mapped_column(Text, nullable=False)
    scope: Mapped[str | None]  = mapped_column(Text)          # "NVDA,TSM" or theme text
    schedule_expr: Mapped[str | None] = mapped_column(Text)   # cron, DEFINITION ONLY
    status: Mapped[str]        = mapped_column(String(16), nullable=False, default="open")
    created_by: Mapped[str]    = mapped_column(String(64), nullable=False, default="owner")
    follow_up_of_task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_task.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('open','paused','closed')",
            name="ck_research_task_status",
        ),
        Index("ix_research_task_status", "status"),
        Index("ix_research_task_follow_up", "follow_up_of_task_id"),
    )

    reports: Mapped[list[ResearchReport]] = relationship(back_populates="task")


class ResearchReport(Base):
    """One versioned, immutable answer to a research_task. Frozen at
    delivery: only review_status/reviewed_by/reviewed_at ever change after
    insert (service-only path). citations = [{source, url, observed_at}]
    — the service rejects any citation missing url or observed_at.
    Corrections are new rows (version+1, supersedes_report_id); the old
    version stays byte-identical and turns 'superseded' at read time."""

    __tablename__ = "research_report"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str]   = mapped_column(
        String(36), ForeignKey("research_task.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int]   = mapped_column(Integer, nullable=False)
    body: Mapped[str]      = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSON_COL, nullable=False, default=list)
    provenance: Mapped[str] = mapped_column(String(16), nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(64))
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_report_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_report.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint("task_id", "version", name="uq_research_report_task_version"),
        CheckConstraint("version >= 1", name="ck_research_report_version"),
        CheckConstraint(
            "provenance IN ('generated','human')",
            name="ck_research_report_provenance",
        ),
        CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="ck_research_report_review",
        ),
        # reviewed rows must say who/when (thesis_evidence precedent)
        CheckConstraint(
            "review_status = 'pending' "
            "OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_research_report_reviewed",
        ),
        Index("ix_research_report_task", "task_id", text("version DESC")),
        Index("ix_research_report_review", "review_status"),
    )

    task: Mapped[ResearchTask] = relationship(back_populates="reports")


# ---------------------------------------------------------------------------
# Learning Loop — Elite ArthOS Priority 6 (migration 113)
# ---------------------------------------------------------------------------
# One post-outcome learning record tied to the decision it judges. All
# mutations flow through apps/api/src/domain/learning/service.py ONLY:
# the hindsight guard (original_thesis_quote must be a verbatim substring
# of a thesis_revision snapshot at-or-before recommendation.generated_at),
# the censored-outcome guard (unresolved outcomes may only carry
# thesis_effect='none'), and the forced-draft rule for generated lessons
# all live there. Approving a lesson NEVER mutates thesis status — it may
# only attach a thesis_link(target_type='lesson') row.
# Spec: docs/architecture/LEARNING_LOOP_SPEC.md

class Lesson(Base):
    """A human-reviewed lesson from one resolved recommendation outcome.
    `original_thesis_quote` is verbatim as-of-decision-time text (hindsight
    guard); reviewer identity is mandatory on approve/reject (DB CHECK).
    outcome_ref is a soft reference to recommendation_outcome.id
    (thesis_link precedent — service existence-checks it, no hard FK)."""

    __tablename__ = "lesson"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recommendation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("recommendation.id", ondelete="RESTRICT")
    )
    paper_trade_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("paper_trade.id", ondelete="SET NULL")
    )
    outcome_ref: Mapped[str | None] = mapped_column(String(36))
    thesis_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("thesis.id", ondelete="RESTRICT")
    )
    what_happened: Mapped[str] = mapped_column(Text, nullable=False)
    original_thesis_quote: Mapped[str] = mapped_column(Text, nullable=False)
    expectation: Mapped[str | None] = mapped_column(Text)
    evidence_correct: Mapped[list] = mapped_column(
        JSON_COL, nullable=False, default=list
    )
    evidence_misleading: Mapped[list] = mapped_column(
        JSON_COL, nullable=False, default=list
    )
    thesis_effect: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none"
    )
    calibration_note: Mapped[str | None] = mapped_column(Text)
    risk_controls_note: Mapped[str | None] = mapped_column(Text)
    should_change: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(String(16), nullable=False)
    review_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft"
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(64))
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_by: Mapped[str] = mapped_column(
        String(64), nullable=False, default="owner"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint(
            "thesis_effect IN ('strengthened','weakened','invalidated','none')",
            name="ck_lesson_effect",
        ),
        CheckConstraint(
            "provenance IN ('generated','human')",
            name="ck_lesson_provenance",
        ),
        CheckConstraint(
            "review_state IN ('draft','approved','rejected')",
            name="ck_lesson_review",
        ),
        # approved/rejected rows must carry the reviewer trail
        CheckConstraint(
            "review_state = 'draft' "
            "OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_lesson_reviewed",
        ),
        Index("ix_lesson_review_created", "review_state",
              text("created_at DESC")),
        Index("ix_lesson_recommendation", "recommendation_id"),
        Index("ix_lesson_thesis", "thesis_id"),
        Index("ix_lesson_outcome_ref", "outcome_ref"),
    )
