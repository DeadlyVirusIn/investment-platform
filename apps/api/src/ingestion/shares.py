"""Shares-outstanding ingestion pipeline.

Input shape (parser-ready dict):
    {
        "asset_id":           str,
        "symbol":             str,
        "effective_date":     date | "YYYY-MM-DD",
        "filing_date":        date | "YYYY-MM-DD",
        "shares_outstanding": int | str,
        "source":             str,
        "external_id":        str | None,
    }

Rejects: missing required field, negative shares, filing_date < effective_date,
unparseable dates.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable

from loguru import logger
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    RawSharesIngestion,
    SharesOutstandingRow,
)
from apps.api.src.domain.data.shares.models import SharesOutstandingRecord
from apps.api.src.domain.data.shares.sql_repo import SqlSharesRepo
from apps.api.src.ingestion.common import IngestionResult, quarantine_row
from apps.api.src.ingestion.content_hash import (
    payload_content_hash,
    shares_content_hash,
)

_SOURCE_TYPE = "shares"
_REQUIRED = (
    "asset_id", "symbol", "effective_date", "filing_date",
    "shares_outstanding", "source",
)


def _parse_date(v) -> dt.date:
    if isinstance(v, dt.date) and not isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, str):
        return dt.date.fromisoformat(v)
    raise ValueError(f"unparseable date: {v!r}")


def _parse_shares(v) -> int:
    if isinstance(v, bool):  # bool is subclass of int — reject
        raise ValueError(f"bool not accepted: {v!r}")
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        return int(s)
    raise ValueError(f"unparseable shares: {v!r}")


def ingest_shares(
    session: Session,
    records: Iterable[dict],
    *,
    dry_run: bool = False,
) -> IngestionResult:
    result = IngestionResult(source_type=_SOURCE_TYPE)
    repo = SqlSharesRepo(session)

    for rec in records:
        result.total_in += 1
        source = str(rec.get("source") or "unknown")
        external_id = rec.get("external_id")

        # Raw-table content hash: payload + source (idempotent).
        raw_hash = payload_content_hash(source, dict(rec))
        from sqlalchemy import select as _select
        existing_raw = session.execute(
            _select(RawSharesIngestion).where(
                RawSharesIngestion.source == source,
                RawSharesIngestion.content_hash == raw_hash,
            )
        ).scalar_one_or_none()
        if existing_raw is not None:
            raw = existing_raw
        else:
            raw = RawSharesIngestion(
                source=source, external_id=external_id, payload=dict(rec),
                content_hash=raw_hash, status="pending",
            )
            session.add(raw)
            session.flush()
            result.raw_inserted += 1
        # Required fields
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
            eff = _parse_date(rec["effective_date"])
            fil = _parse_date(rec["filing_date"])
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
            shares = _parse_shares(rec["shares_outstanding"])
        except (ValueError, TypeError) as exc:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="bad_shares_value", reason_detail=str(exc),
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"; raw.rejection_reason = "bad_shares"
            result.quarantined += 1
            result.quarantine_reasons["bad_shares_value"] += 1
            continue

        # Domain invariants (these will also be re-checked by the dataclass
        # but we produce explicit quarantine reasons before constructing)
        if shares < 0:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="negative_shares", reason_detail=f"{shares}",
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"; raw.rejection_reason = "negative_shares"
            result.quarantined += 1
            result.quarantine_reasons["negative_shares"] += 1
            continue
        if fil < eff:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="filing_before_effective",
                reason_detail=f"filing={fil} effective={eff}",
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"
            raw.rejection_reason = "filing_before_effective"
            result.quarantined += 1
            result.quarantine_reasons["filing_before_effective"] += 1
            continue

        record = SharesOutstandingRecord(
            symbol=str(rec["symbol"]).upper(),
            asset_id=str(rec["asset_id"]),
            effective_date=eff, filing_date=fil,
            shares_outstanding=shares, source=source,
        )

        if dry_run:
            raw.status = "pending"
            continue

        # Determine insert vs update for result accounting
        from sqlalchemy import select
        had = session.execute(
            select(SharesOutstandingRow).where(
                SharesOutstandingRow.asset_id == record.asset_id,
                SharesOutstandingRow.effective_date == record.effective_date,
                SharesOutstandingRow.source == record.source,
            )
        ).scalar_one_or_none() is not None

        try:
            repo.upsert(record)
            raw.status = "normalized"
            result.updated += 1 if had else 0
            result.inserted += 0 if had else 1
        except Exception as exc:  # noqa: BLE001
            logger.error("[ingest.shares] upsert failed: {}", exc)
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
    logger.info("[ingest.shares] {}", result.as_dict())
    return result
