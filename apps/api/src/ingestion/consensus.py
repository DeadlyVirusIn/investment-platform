"""Consensus / actual ingestion pipeline — STRICT unit handling (Phase 10.6).

Input shape (parser-ready dict):
    {
        "asset_id":      str,
        "symbol":        str,
        "event_date":    date | "YYYY-MM-DD",
        "metric":        "eps" | "revenue",
        "estimate_type": "consensus" | "actual",
        "value":         float | str,
        "value_unit":    "usd_per_share" | "usd_raw" | "usd_millions"
                         | "usd_billions" | "usd_thousands"   (REQUIRED P10.6)
        "as_of_date":    date | "YYYY-MM-DD",
        "source":        str,
        "external_id":   str | None,
    }

PHASE 10.6 RULES:
  - `value_unit` is REQUIRED. Missing → quarantine `missing_value_unit`.
  - Unit must be allowed for the metric (EPS must be `usd_per_share`;
    Revenue must be one of the USD scales). Mismatch → quarantine
    `unit_metric_mismatch`.
  - `value` is STORED NORMALIZED (canonical unit per metric). Original
    input preserved in `original_value` + `original_unit`.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Iterable

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    ConsensusEstimateRow,
    RawConsensusIngestion,
)
from apps.api.src.domain.data.consensus.models import (
    ConsensusRecord,
    EstimateType,
    Metric,
)
from apps.api.src.domain.data.consensus.sql_repo import SqlConsensusRepo
from apps.api.src.ingestion.common import IngestionResult, quarantine_row
from apps.api.src.ingestion.content_hash import (
    consensus_content_hash,
    payload_content_hash,
)
from apps.api.src.ingestion.units import (
    UnitError,
    ValueUnit,
    normalize_to_canonical,
    parse_unit,
)

_SOURCE_TYPE = "consensus"
_REQUIRED = (
    "asset_id", "symbol", "event_date", "metric", "estimate_type",
    "value", "value_unit", "as_of_date", "source",
)


def _parse_date(v) -> dt.date:
    if isinstance(v, dt.date) and not isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, str):
        return dt.date.fromisoformat(v)
    raise ValueError(f"unparseable date: {v!r}")


def _parse_value(v) -> float:
    if isinstance(v, bool):
        raise ValueError(f"bool not accepted: {v!r}")
    if isinstance(v, (int, float)):
        f = float(v)
    elif isinstance(v, str):
        f = float(v.replace(",", "").strip())
    else:
        raise ValueError(f"unparseable value: {v!r}")
    if math.isnan(f) or math.isinf(f):
        raise ValueError(f"non-finite value: {v!r}")
    return f


def ingest_consensus(
    session: Session,
    records: Iterable[dict],
    *,
    dry_run: bool = False,
) -> IngestionResult:
    result = IngestionResult(source_type=_SOURCE_TYPE)
    repo = SqlConsensusRepo(session)

    for rec in records:
        result.total_in += 1
        source = str(rec.get("source") or "unknown")
        external_id = rec.get("external_id")

        # Raw-table content hash: payload + source (idempotent).
        raw_hash = payload_content_hash(source, dict(rec))
        from sqlalchemy import select as _select
        existing_raw = session.execute(
            _select(RawConsensusIngestion).where(
                RawConsensusIngestion.source == source,
                RawConsensusIngestion.content_hash == raw_hash,
            )
        ).scalar_one_or_none()
        if existing_raw is not None:
            raw = existing_raw
        else:
            raw = RawConsensusIngestion(
                source=source, external_id=external_id, payload=dict(rec),
                content_hash=raw_hash, status="pending",
            )
            session.add(raw)
            session.flush()
            result.raw_inserted += 1

        missing = [k for k in _REQUIRED if k not in rec or rec[k] in (None, "")]
        if missing:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="missing_required_field",
                reason_detail=f"missing: {missing}",
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"; raw.rejection_reason = "missing"
            result.quarantined += 1
            result.quarantine_reasons["missing_required_field"] += 1
            continue

        try:
            metric = Metric(rec["metric"])
        except ValueError:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="bad_metric", reason_detail=f"value={rec['metric']!r}",
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"; raw.rejection_reason = "bad_metric"
            result.quarantined += 1
            result.quarantine_reasons["bad_metric"] += 1
            continue

        try:
            estimate_type = EstimateType(rec["estimate_type"])
        except ValueError:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="bad_estimate_type",
                reason_detail=f"value={rec['estimate_type']!r}",
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"; raw.rejection_reason = "bad_estimate_type"
            result.quarantined += 1
            result.quarantine_reasons["bad_estimate_type"] += 1
            continue

        try:
            event_date = _parse_date(rec["event_date"])
            as_of_date = _parse_date(rec["as_of_date"])
        except (ValueError, TypeError) as exc:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="bad_date", reason_detail=str(exc),
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"; raw.rejection_reason = "bad_date"
            result.quarantined += 1
            result.quarantine_reasons["bad_date"] += 1
            continue

        try:
            original_value = _parse_value(rec["value"])
        except (ValueError, TypeError) as exc:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="bad_value", reason_detail=str(exc),
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"; raw.rejection_reason = "bad_value"
            result.quarantined += 1
            result.quarantine_reasons["bad_value"] += 1
            continue

        # Parse value_unit STRICT (Phase 10.6)
        try:
            original_unit = parse_unit(rec.get("value_unit"))
        except UnitError as exc:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="ambiguous_unit", reason_detail=str(exc),
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"; raw.rejection_reason = "ambiguous_unit"
            result.quarantined += 1
            result.quarantine_reasons["ambiguous_unit"] += 1
            continue

        # Normalize to canonical unit per metric
        try:
            normalized_value, canonical_unit = normalize_to_canonical(
                metric.value, original_value, original_unit,
            )
        except UnitError as exc:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="unit_metric_mismatch", reason_detail=str(exc),
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"
            raw.rejection_reason = "unit_metric_mismatch"
            result.quarantined += 1
            result.quarantine_reasons["unit_metric_mismatch"] += 1
            continue

        record = ConsensusRecord(
            symbol=str(rec["symbol"]).upper(),
            asset_id=str(rec["asset_id"]),
            event_date=event_date, metric=metric,
            estimate_type=estimate_type,
            value=normalized_value,
            original_value=original_value,
            original_unit=original_unit,
            value_unit=canonical_unit,
            as_of_date=as_of_date, source=source,
        )

        if dry_run:
            raw.status = "pending"
            continue

        had = session.execute(
            select(ConsensusEstimateRow).where(
                ConsensusEstimateRow.asset_id == record.asset_id,
                ConsensusEstimateRow.event_date == record.event_date,
                ConsensusEstimateRow.metric == record.metric.value,
                ConsensusEstimateRow.estimate_type == record.estimate_type.value,
                ConsensusEstimateRow.as_of_date == record.as_of_date,
                ConsensusEstimateRow.source == record.source,
            )
        ).scalar_one_or_none() is not None

        try:
            repo.upsert(record)
            raw.status = "normalized"
            result.updated += 1 if had else 0
            result.inserted += 0 if had else 1
        except Exception as exc:  # noqa: BLE001
            logger.error("[ingest.consensus] upsert failed: {}", exc)
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="upsert_failed", reason_detail=str(exc),
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"; raw.rejection_reason = "upsert_failed"
            result.quarantined += 1
            result.quarantine_reasons["upsert_failed"] += 1

    if not dry_run:
        session.commit()
    else:
        session.rollback()
    logger.info("[ingest.consensus] {}", result.as_dict())
    return result
