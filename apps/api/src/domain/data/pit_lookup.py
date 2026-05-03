"""Point-in-time lookup API — the public surface of Phase 9.

All queries take an explicit `as_of` or derive one from the event date.
Missing data returns None (or raises PointInTimeDataError if caller
opts into strict mode). No silent fallbacks. No future-data leakage.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from apps.api.src.domain.data.completeness import (
    compute_completeness,
    derive_quality,
)
from apps.api.src.domain.data.consensus.models import (
    ConsensusRecord,
    EstimateType,
    Metric,
)
from apps.api.src.domain.data.consensus.repo import ConsensusRepo
from apps.api.src.domain.data.earnings.models import EarningsEvent
from apps.api.src.domain.data.earnings.repo import EarningsRepo
from apps.api.src.domain.data.event_record import EventRecord
from apps.api.src.domain.data.shares.models import SharesOutstandingRecord
from apps.api.src.domain.data.shares.repo import SharesRepo


class PointInTimeDataError(RuntimeError):
    """Raised when required PIT data is missing or ambiguous."""


@dataclass
class PITDataContext:
    """Composes the three repositories + exposes the public API.

    Holds no state beyond the injected repos. Safe to instantiate per
    request or per evaluation-day. Thread-safe only insofar as the
    underlying repos are.
    """

    earnings: EarningsRepo
    shares: SharesRepo
    consensus: ConsensusRepo

    # ------------------------------------------------------------------
    # Earnings
    # ------------------------------------------------------------------

    def get_events_on(self, date: dt.date) -> list[EarningsEvent]:
        """Return every earnings event where `event_date == date`."""
        return self.earnings.get_events_on(date)

    def get_event(
        self, symbol: str, event_date: dt.date,
    ) -> EarningsEvent | None:
        """Return the event for (symbol, event_date) or None."""
        return self.earnings.get_event(symbol, event_date)

    # ------------------------------------------------------------------
    # Shares outstanding
    # ------------------------------------------------------------------

    def get_shares_outstanding(
        self, symbol: str, as_of_date: dt.date,
    ) -> SharesOutstandingRecord | None:
        """Latest disclosed shares outstanding with `filing_date <= as_of`."""
        return self.shares.get_as_of(symbol, as_of_date)

    # ------------------------------------------------------------------
    # Consensus / actual
    # ------------------------------------------------------------------

    def get_consensus(
        self, symbol: str, event_date: dt.date,
        metric: Metric, as_of_date: dt.date,
    ) -> ConsensusRecord | None:
        """Latest consensus estimate with `as_of_date < as_of` (STRICT)."""
        return self.consensus.get_consensus(
            symbol, event_date, metric, as_of_date,
        )

    def get_actual(
        self, symbol: str, event_date: dt.date, metric: Metric,
    ) -> ConsensusRecord | None:
        """Latest actual (may be a restatement). For strict PIT callers,
        use `get_actual_as_of`."""
        return self.consensus.get_actual(symbol, event_date, metric)

    def get_actual_as_of(
        self, symbol: str, event_date: dt.date,
        metric: Metric, as_of_date: dt.date,
    ) -> ConsensusRecord | None:
        """Latest actual with `as_of_date <= as_of`."""
        return self.consensus.get_actual_as_of(
            symbol, event_date, metric, as_of_date,
        )

    # ------------------------------------------------------------------
    # Unified assembly
    # ------------------------------------------------------------------

    def build_event_record(
        self,
        symbol: str,
        event_date: dt.date,
        *,
        require_consensus: bool = False,
        require_shares: bool = False,
    ) -> EventRecord:
        """Assemble the canonical EventRecord.

        Cutoffs:
          - CONSENSUS (EPS + REVENUE): as_of_date < event_date
            (strictly pre-event).
          - ACTUAL (EPS + REVENUE): latest revision available (no
            cutoff; caller is assumed to be post-announcement).
          - SHARES: filing_date <= event_date (PIT).

        Raises PointInTimeDataError if:
          - no earnings event exists for (symbol, event_date)
          - `require_consensus=True` and either consensus is missing
          - `require_shares=True` and shares record is missing
        """
        event = self.earnings.get_event(symbol, event_date)
        if event is None:
            raise PointInTimeDataError(
                f"no earnings event for symbol={symbol} event_date={event_date}"
            )

        eps_cons = self.consensus.get_consensus(
            symbol, event_date, Metric.EPS, event_date,
        )
        rev_cons = self.consensus.get_consensus(
            symbol, event_date, Metric.REVENUE, event_date,
        )
        eps_actual = self.consensus.get_actual(symbol, event_date, Metric.EPS)
        rev_actual = self.consensus.get_actual(
            symbol, event_date, Metric.REVENUE,
        )
        shares = self.shares.get_as_of(symbol, event_date)

        if require_consensus and (eps_cons is None or rev_cons is None):
            raise PointInTimeDataError(
                f"missing consensus for {symbol} on {event_date}: "
                f"eps={'yes' if eps_cons else 'MISSING'} "
                f"revenue={'yes' if rev_cons else 'MISSING'}"
            )
        if require_shares and shares is None:
            raise PointInTimeDataError(
                f"missing shares_outstanding for {symbol} as of {event_date}"
            )

        eps_actual_v = eps_actual.value if eps_actual else None
        eps_cons_v = eps_cons.value if eps_cons else None
        rev_actual_v = rev_actual.value if rev_actual else None
        rev_cons_v = rev_cons.value if rev_cons else None
        shares_v = shares.shares_outstanding if shares else None

        flags = compute_completeness(
            eps_actual=eps_actual_v, eps_consensus=eps_cons_v,
            revenue_actual=rev_actual_v, revenue_consensus=rev_cons_v,
            shares_outstanding=shares_v,
        )
        quality = derive_quality(flags, event.event_time)

        return EventRecord(
            symbol=event.symbol,
            asset_id=event.asset_id,
            event_date=event.event_date,
            event_time=event.event_time,
            tradable_date=event.tradable_date,
            announcement_timestamp=event.announcement_timestamp,
            announcement_timestamp_raw=event.announcement_timestamp_raw,
            fiscal_period=event.fiscal_period,
            eps_actual=eps_actual_v,
            eps_consensus=eps_cons_v,
            revenue_actual=rev_actual_v,
            revenue_consensus=rev_cons_v,
            shares_outstanding_as_of_event=shares_v,
            consensus_as_of=event_date,
            shares_as_of=event_date,
            source_earnings=event.source,
            source_shares=shares.source if shares else None,
            source_consensus_eps=eps_cons.source if eps_cons else None,
            source_consensus_revenue=rev_cons.source if rev_cons else None,
            completeness=flags,
            quality=quality,
        )
