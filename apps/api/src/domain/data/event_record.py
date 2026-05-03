"""Canonical EventRecord — the unified point-in-time snapshot.

Assembled by `pit_lookup.PITDataContext.build_event_record`. Caller decides
whether to tolerate missing fields (e.g. missing consensus) via `require_*`
flags. This dataclass is the contract used by downstream behavioral
providers (e.g. Buyback Blackout Re-bid, Messy Beat PEAD).

Phase 10 addition: completeness flags + deterministic quality indicator
(FULL / PARTIAL / SPARSE). Strictly informational — do NOT silently
override `require_*` behavior.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from apps.api.src.domain.data.completeness import (
    CompletenessFlags,
    EventQuality,
)
from apps.api.src.domain.data.time import EventTime


@dataclass(frozen=True)
class EventRecord:
    """Unified view of (symbol, event_date) at a specific knowledge cutoff.

    `consensus_as_of` records the cutoff used for CONSENSUS lookups so
    the record's PIT provenance is auditable. For the canonical assembly
    `consensus_as_of = event_date` (strict less-than when filtered).
    `shares_as_of` records the cutoff used for shares lookup
    (filing_date <= shares_as_of).

    Unknown / unavailable fields are `None` — NEVER zero or silently
    filled — so consumers can decide between skip / abstain / error.
    """

    symbol: str
    asset_id: str
    event_date: dt.date
    event_time: EventTime
    tradable_date: dt.date
    announcement_timestamp: dt.datetime | None
    announcement_timestamp_raw: str | None      # Phase 10: preserve the
                                                #   original-feed timestamp
                                                #   text for audit
    fiscal_period: str | None
    # Consensus / actual
    eps_actual: float | None
    eps_consensus: float | None
    revenue_actual: float | None
    revenue_consensus: float | None
    # Structural
    shares_outstanding_as_of_event: int | None
    # Provenance / cutoffs (auditable)
    consensus_as_of: dt.date
    shares_as_of: dt.date
    source_earnings: str
    source_shares: str | None
    source_consensus_eps: str | None
    source_consensus_revenue: str | None
    # Phase 10 additions — completeness + quality (deterministic; informational)
    completeness: CompletenessFlags
    quality: EventQuality
