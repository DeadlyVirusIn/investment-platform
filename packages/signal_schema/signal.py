"""Canonical Signal schema — mirrors the `signal` DB table.

All adapters MUST output Signal objects. Ranker + downstream consume
these exclusively. Pydantic validation enforces bounds on [0, 1] fields.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Direction = Literal["long", "short", "neutral"]
Timeframe = Literal["1d", "1h", "15m"]
ModelFamily = Literal[
    "deterministic",
    "ml_classifier",
    "rl",
    "quant_factor",
    "meta_label",
]

DIRECTION_LONG: Direction = "long"
DIRECTION_SHORT: Direction = "short"
DIRECTION_NEUTRAL: Direction = "neutral"


class Signal(BaseModel):
    """Single model output for a single asset on a single date.

    Invariants:
      - signal_strength, confidence, risk_score ∈ [0, 1]
      - holding_period_bars > 0
      - direction ∈ {long, short, neutral}
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Identity
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    symbol: str

    # Timing
    timestamp: dt.datetime            # when model produced this (alias: generated_at)
    as_of_date: dt.date               # bar date the signal is for
    timeframe: Timeframe = "1d"

    # Lineage
    strategy_id: str                  # e.g., "stock_swing_v1"
    model_family: ModelFamily
    model_version: str
    features_version: str

    # Decision payload
    signal_direction: Direction
    signal_strength: Decimal          # 0..1 abs conviction
    confidence: Decimal               # 0..1 calibration
    expected_return: Decimal | None = None
    expected_drawdown: Decimal | None = None
    holding_period_bars: int = Field(gt=0)
    risk_score: Decimal | None = None
    regime_tag: str | None = None

    # Trace
    raw_payload_ref: str | None = None
    generated_by_run_id: str | None = None   # MLflow/Prefect run id, optional

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("signal_strength", "confidence")
    @classmethod
    def _in_unit_interval(cls, v: Decimal) -> Decimal:
        if v is None:
            raise ValueError("field must not be None")
        if Decimal(0) <= v <= Decimal(1):
            return v
        raise ValueError(f"must be in [0, 1], got {v}")

    @field_validator("risk_score")
    @classmethod
    def _risk_in_unit_interval(cls, v: Decimal | None) -> Decimal | None:
        if v is None:
            return None
        if Decimal(0) <= v <= Decimal(1):
            return v
        raise ValueError(f"risk_score must be in [0, 1], got {v}")
