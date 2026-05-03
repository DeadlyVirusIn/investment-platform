"""Behavioral signal base — schema, provider ABC, shared data containers.

Separate schema (BehavioralSignal) adjacent to the core Signal model. Both
are normalized and share the Direction / Timeframe / unit-interval
constraints. Kept separate for Phase B1 so model-family signals and
behavioral signals can be evaluated independently (different
`source_type`), then combined later without schema churn.

NO DB coupling. Providers are pure functions of (as_of_date, universe,
market_context). DB access lives in the integrator.
"""

from __future__ import annotations

import datetime as dt
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Re-use core-signal enums for consistency
Direction = Literal["long", "short", "neutral"]
Timeframe = Literal["1d", "1h", "15m"]
SourceType = Literal["behavioral"]

DIRECTION_LONG: Direction = "long"
DIRECTION_SHORT: Direction = "short"
DIRECTION_NEUTRAL: Direction = "neutral"


# ---------------------------------------------------------------------------
# Behavioral signal (schema)
# ---------------------------------------------------------------------------


class BehavioralSignal(BaseModel):
    """One behavioral-family signal for one symbol on one date.

    Invariants (validated):
      - signal_strength ∈ [0, 1]
      - confidence      ∈ [0, 1]
      - signal_direction ∈ {long, short, neutral}
      - source_type     = "behavioral"
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    timestamp: dt.datetime
    timeframe: Timeframe = "1d"
    source_type: SourceType = "behavioral"
    strategy_id: str
    signal_direction: Direction
    signal_strength: float
    confidence: float
    explanation: str
    metadata: dict = Field(default_factory=dict)

    @field_validator("signal_strength", "confidence")
    @classmethod
    def _in_unit_interval(cls, v: float) -> float:
        if v is None:
            raise ValueError("field must not be None")
        if 0.0 <= float(v) <= 1.0:
            return float(v)
        raise ValueError(f"must be in [0, 1], got {v}")


# ---------------------------------------------------------------------------
# Input containers — decoupled from DB
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bar:
    """Single OHLCV bar. Pure value type."""
    ts: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class AssetHistory:
    """Trailing bar history for one asset, ascending by ts (as_of last)."""
    symbol: str
    asset_id: str
    bars: list[Bar]

    @property
    def latest(self) -> Bar | None:
        return self.bars[-1] if self.bars else None

    def closes(self, n: int | None = None) -> list[float]:
        if n is None:
            return [b.close for b in self.bars]
        return [b.close for b in self.bars[-n:]]

    def volumes(self, n: int | None = None) -> list[float]:
        if n is None:
            return [b.volume for b in self.bars]
        return [b.volume for b in self.bars[-n:]]


@dataclass(frozen=True)
class MarketContext:
    """Market-level aggregates computed once per as_of date.

    Fields are optional — providers MUST degrade gracefully to neutral / no
    signal when a required field is None (e.g. breadth unavailable because
    universe too sparse).
    """
    as_of_date: dt.date
    pct_above_ma50: float | None = None   # breadth proxy [0, 1]
    universe_size: int = 0
    market_trend_label: str | None = None


# ---------------------------------------------------------------------------
# Provider ABC
# ---------------------------------------------------------------------------


class BehavioralSignalProvider(ABC):
    """Provider contract. Each concrete provider declares its strategy_id.

    Implementations MUST:
      - be pure functions of the inputs (no DB, no I/O, no mutable state)
      - return a list of BehavioralSignal (possibly empty)
      - never raise on degenerate inputs — return [] instead
      - set source_type="behavioral" (enforced by schema default)
    """

    strategy_id: str = ""   # subclasses MUST override

    @abstractmethod
    def generate(
        self,
        as_of_date: dt.date,
        universe: list[AssetHistory],
        market_context: MarketContext,
    ) -> list[BehavioralSignal]:
        ...


# ---------------------------------------------------------------------------
# Tiny numerical helpers (no numpy dependency at this layer)
# ---------------------------------------------------------------------------


def safe_mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def safe_std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = safe_mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def daily_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        p = closes[i - 1]
        if p <= 0:
            continue
        out.append((closes[i] - p) / p)
    return out
