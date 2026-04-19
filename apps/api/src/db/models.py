"""SQLAlchemy 2 ORM models for the investment-intelligence platform."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
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
    conviction: Mapped[object | None] = mapped_column(EQUITY_NUM)           # 0–1 score
    rationale: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    evidence: Mapped[list[RecommendationEvidence]] = relationship(back_populates="recommendation")


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
