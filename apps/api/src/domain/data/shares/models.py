"""Shares-outstanding domain types."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class SharesOutstandingRecord:
    """One disclosed shares-outstanding measurement.

    CRITICAL for point-in-time reasoning:
      - `effective_date` is the fiscal date the count was measured at
        (e.g. "March 31, 2026" — quarter-end).
      - `filing_date` is when the disclosure was made public (e.g. 10-Q
        filed May 15). The trader did NOT know the March 31 count until
        May 15.

    Point-in-time lookups MUST filter by `filing_date <= as_of`, never by
    `effective_date`, or forward information leaks in.
    """

    symbol: str
    asset_id: str
    effective_date: dt.date
    filing_date: dt.date
    shares_outstanding: int
    source: str = ""

    def __post_init__(self) -> None:
        if self.shares_outstanding < 0:
            raise ValueError(
                f"shares_outstanding must be non-negative, "
                f"got {self.shares_outstanding}"
            )
        if self.filing_date < self.effective_date:
            # Filing MUST be on or after the as-of measurement
            raise ValueError(
                f"filing_date={self.filing_date} before "
                f"effective_date={self.effective_date} — impossible"
            )
