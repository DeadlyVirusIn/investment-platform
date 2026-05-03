"""SQL-backed ConsensusRepo.

Preserves Phase 9 semantics exactly:
  - unique (asset_id, event_date, metric, estimate_type, as_of_date, source)
  - revisions stored as new rows (never overwritten)
  - get_consensus: strict `as_of_date < as_of`, latest wins
  - get_actual: latest revision (across all as_of_dates)
  - get_actual_as_of: `as_of_date <= as_of`, latest wins
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import ConsensusEstimateRow
from apps.api.src.domain.data.consensus.models import (
    ConsensusRecord,
    EstimateType,
    Metric,
)


def _row_to_domain(row: ConsensusEstimateRow) -> ConsensusRecord:
    return ConsensusRecord(
        symbol=row.symbol,
        asset_id=row.asset_id,
        event_date=row.event_date,
        metric=Metric(row.metric),
        estimate_type=EstimateType(row.estimate_type),
        value=float(row.value),
        as_of_date=row.as_of_date,
        source=row.source,
        value_unit=row.value_unit,
        original_value=(
            float(row.original_value) if row.original_value is not None else None
        ),
        original_unit=row.original_unit,
    )


class SqlConsensusRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_consensus(
        self, symbol: str, event_date: dt.date,
        metric: Metric, as_of: dt.date,
    ) -> ConsensusRecord | None:
        row = self.session.execute(
            select(ConsensusEstimateRow).where(
                ConsensusEstimateRow.symbol == symbol,
                ConsensusEstimateRow.event_date == event_date,
                ConsensusEstimateRow.metric == metric.value,
                ConsensusEstimateRow.estimate_type == EstimateType.CONSENSUS.value,
                ConsensusEstimateRow.as_of_date < as_of,   # STRICT <
            ).order_by(
                ConsensusEstimateRow.as_of_date.desc(),
            ).limit(1)
        ).scalar_one_or_none()
        return _row_to_domain(row) if row else None

    def get_actual(
        self, symbol: str, event_date: dt.date, metric: Metric,
    ) -> ConsensusRecord | None:
        row = self.session.execute(
            select(ConsensusEstimateRow).where(
                ConsensusEstimateRow.symbol == symbol,
                ConsensusEstimateRow.event_date == event_date,
                ConsensusEstimateRow.metric == metric.value,
                ConsensusEstimateRow.estimate_type == EstimateType.ACTUAL.value,
            ).order_by(
                ConsensusEstimateRow.as_of_date.desc(),
            ).limit(1)
        ).scalar_one_or_none()
        return _row_to_domain(row) if row else None

    def get_actual_as_of(
        self, symbol: str, event_date: dt.date,
        metric: Metric, as_of: dt.date,
    ) -> ConsensusRecord | None:
        row = self.session.execute(
            select(ConsensusEstimateRow).where(
                ConsensusEstimateRow.symbol == symbol,
                ConsensusEstimateRow.event_date == event_date,
                ConsensusEstimateRow.metric == metric.value,
                ConsensusEstimateRow.estimate_type == EstimateType.ACTUAL.value,
                ConsensusEstimateRow.as_of_date <= as_of,
            ).order_by(
                ConsensusEstimateRow.as_of_date.desc(),
            ).limit(1)
        ).scalar_one_or_none()
        return _row_to_domain(row) if row else None

    def upsert(self, record: ConsensusRecord) -> None:
        existing = self.session.execute(
            select(ConsensusEstimateRow).where(
                ConsensusEstimateRow.asset_id == record.asset_id,
                ConsensusEstimateRow.event_date == record.event_date,
                ConsensusEstimateRow.metric == record.metric.value,
                ConsensusEstimateRow.estimate_type == record.estimate_type.value,
                ConsensusEstimateRow.as_of_date == record.as_of_date,
                ConsensusEstimateRow.source == record.source,
            )
        ).scalar_one_or_none()
        # Coerce ValueUnit enum -> str for DB column
        vu = record.value_unit
        if vu is not None and hasattr(vu, "value"):
            vu = vu.value
        ou = record.original_unit
        if ou is not None and hasattr(ou, "value"):
            ou = ou.value

        if existing is None:
            row = ConsensusEstimateRow(
                asset_id=record.asset_id,
                symbol=record.symbol,
                event_date=record.event_date,
                metric=record.metric.value,
                estimate_type=record.estimate_type.value,
                value=record.value,
                value_unit=vu,
                original_value=record.original_value,
                original_unit=ou,
                as_of_date=record.as_of_date,
                source=record.source,
            )
            self.session.add(row)
        else:
            # Value corrections on the same natural-key row
            existing.symbol = record.symbol
            existing.value = record.value
            existing.value_unit = vu
            existing.original_value = record.original_value
            existing.original_unit = ou
        self.session.flush()

    def bulk_upsert(self, records: Iterable[ConsensusRecord]) -> None:
        for r in records:
            self.upsert(r)
