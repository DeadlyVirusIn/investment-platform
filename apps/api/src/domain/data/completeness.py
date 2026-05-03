"""Deterministic event-data completeness + quality indicator.

NO ML. No weighting tricks. Pure field-presence arithmetic. Transparent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from apps.api.src.domain.data.time import EventTime


class EventQuality(str, Enum):
    """Coarse, explicit, deterministic quality bucket.

    FULL    = all 5 completeness flags True AND event_time != UNKNOWN
    PARTIAL = 3 or 4 flags True, or (5 flags True but event_time=UNKNOWN)
    SPARSE  = 0 to 2 flags True
    """

    FULL = "full"
    PARTIAL = "partial"
    SPARSE = "sparse"


@dataclass(frozen=True)
class CompletenessFlags:
    has_eps_actual: bool
    has_eps_consensus: bool
    has_revenue_actual: bool
    has_revenue_consensus: bool
    has_shares_outstanding: bool

    @property
    def count(self) -> int:
        return sum([
            self.has_eps_actual,
            self.has_eps_consensus,
            self.has_revenue_actual,
            self.has_revenue_consensus,
            self.has_shares_outstanding,
        ])


def compute_completeness(
    *,
    eps_actual: float | None,
    eps_consensus: float | None,
    revenue_actual: float | None,
    revenue_consensus: float | None,
    shares_outstanding: int | None,
) -> CompletenessFlags:
    return CompletenessFlags(
        has_eps_actual=eps_actual is not None,
        has_eps_consensus=eps_consensus is not None,
        has_revenue_actual=revenue_actual is not None,
        has_revenue_consensus=revenue_consensus is not None,
        has_shares_outstanding=shares_outstanding is not None,
    )


def derive_quality(
    flags: CompletenessFlags, event_time: EventTime,
) -> EventQuality:
    n = flags.count
    if n == 5 and event_time != EventTime.UNKNOWN:
        return EventQuality.FULL
    if n >= 3:
        return EventQuality.PARTIAL
    return EventQuality.SPARSE
