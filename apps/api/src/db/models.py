"""SQLAlchemy 2 ORM models for the investment-intelligence platform."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
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

    portfolio: Mapped[PaperPortfolio] = relationship(back_populates="positions")

    __table_args__ = (
        Index("ix_paper_position_open",
              "portfolio_id", "asset_id", "is_open"),
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

    __table_args__ = (
        UniqueConstraint("portfolio_id", "snapshot_date", name="uq_paper_equity_snapshot"),
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

