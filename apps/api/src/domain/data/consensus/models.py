"""Consensus / actual EPS + revenue domain types."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum


class Metric(str, Enum):
    EPS = "eps"
    REVENUE = "revenue"


class EstimateType(str, Enum):
    CONSENSUS = "consensus"   # mean / median analyst estimate
    ACTUAL = "actual"         # reported value post-announcement


@dataclass(frozen=True)
class ConsensusRecord:
    """One (metric, estimate_type, as-of) data point for one event.

    PIT semantics hinges on `as_of_date`:
      - For CONSENSUS rows: the date the estimate was PUBLISHED / CURRENT.
        A lookup "what did the market expect as of date T?" uses the
        LATEST consensus with `as_of_date < T` (strict less-than; the
        day of T is the event day itself and could include post-announce
        revisions).
      - For ACTUAL rows: the date the value was DISCLOSED. Lookups return
        the latest (possibly-restated) actual. For strict PIT you can
        filter by `as_of_date <= T`.

    `value` units are source-dependent:
      - EPS:     currency per share (USD for US equities)
      - Revenue: currency (USD) — often reported in millions; keep units
                 consistent at the ingestion layer.
    """

    symbol: str
    asset_id: str
    event_date: dt.date
    metric: Metric
    estimate_type: EstimateType
    value: float                                # normalized (canonical unit)
    as_of_date: dt.date
    source: str = ""
    # Phase 10.6 audit trail (optional for Phase 9 backward-compat)
    value_unit: object | None = None            # ValueUnit | str | None
    original_value: float | None = None
    original_unit: object | None = None         # ValueUnit | str | None

    def __post_init__(self) -> None:
        if not isinstance(self.metric, Metric):
            raise TypeError(f"metric must be Metric, got {type(self.metric).__name__}")
        if not isinstance(self.estimate_type, EstimateType):
            raise TypeError(
                f"estimate_type must be EstimateType, "
                f"got {type(self.estimate_type).__name__}"
            )
