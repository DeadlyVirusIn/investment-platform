"""SQL-backed SharesRepo.

Preserves Phase 9 semantics exactly:
  - unique (asset_id, effective_date, source)
  - UPSERT on natural key (restatements replace; multi-source kept)
  - lookup filters `filing_date <= as_of`, orders latest wins on
    (filing_date DESC, effective_date DESC)
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import SharesOutstandingRow
from apps.api.src.domain.data.shares.models import SharesOutstandingRecord


def _row_to_domain(row: SharesOutstandingRow) -> SharesOutstandingRecord:
    return SharesOutstandingRecord(
        symbol=row.symbol,
        asset_id=row.asset_id,
        effective_date=row.effective_date,
        filing_date=row.filing_date,
        shares_outstanding=int(row.shares_outstanding),
        source=row.source,
    )


class SqlSharesRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_as_of(
        self, symbol: str, as_of: dt.date,
    ) -> SharesOutstandingRecord | None:
        row = self.session.execute(
            select(SharesOutstandingRow).where(
                SharesOutstandingRow.symbol == symbol,
                SharesOutstandingRow.filing_date <= as_of,
            ).order_by(
                SharesOutstandingRow.filing_date.desc(),
                SharesOutstandingRow.effective_date.desc(),
            ).limit(1)
        ).scalar_one_or_none()
        return _row_to_domain(row) if row else None

    def get_history(self, symbol: str) -> list[SharesOutstandingRecord]:
        rows = self.session.execute(
            select(SharesOutstandingRow).where(
                SharesOutstandingRow.symbol == symbol,
            ).order_by(
                SharesOutstandingRow.filing_date,
                SharesOutstandingRow.effective_date,
            )
        ).scalars().all()
        return [_row_to_domain(r) for r in rows]

    def upsert(self, record: SharesOutstandingRecord) -> None:
        existing = self.session.execute(
            select(SharesOutstandingRow).where(
                SharesOutstandingRow.asset_id == record.asset_id,
                SharesOutstandingRow.effective_date == record.effective_date,
                SharesOutstandingRow.source == record.source,
            )
        ).scalar_one_or_none()
        if existing is None:
            row = SharesOutstandingRow(
                asset_id=record.asset_id,
                symbol=record.symbol,
                effective_date=record.effective_date,
                filing_date=record.filing_date,
                shares_outstanding=record.shares_outstanding,
                source=record.source,
            )
            self.session.add(row)
        else:
            existing.symbol = record.symbol
            existing.filing_date = record.filing_date
            existing.shares_outstanding = record.shares_outstanding
        self.session.flush()

    def bulk_upsert(
        self, records: Iterable[SharesOutstandingRecord],
    ) -> None:
        for r in records:
            self.upsert(r)
