"""Earnings ingestion pipeline — STRICT timezone handling (Phase 10.6).

Input shape (dict per record — feed-parser produces these):
    {
        "asset_id":            str,    required
        "symbol":              str,    required
        "event_date":          date | "YYYY-MM-DD",   required
        "event_time":          "before_open" | "after_close" | "during_hours" | "unknown",
        "announcement_timestamp":       datetime | ISO-8601 str | None,
        "announcement_timestamp_raw":   str | None  (original feed text),
        "fiscal_period":       str | None,
        "external_id":         str | None,
    }

PHASE 10.6 RULES:
  - Naive `announcement_timestamp` is REJECTED unless the caller explicitly
    passes `source_timezone=ZoneInfo(...)` — in which case the naive value
    is interpreted in that zone and converted to UTC.
  - Aware timestamps pass through (converted to UTC for storage).
  - No silent UTC assumption. Quarantine reason: `naive_timestamp`.

Rejects: missing required field, unparseable timestamp, unknown event_time,
naive timestamp without source_timezone.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    EarningsEventRow,
    RawEarningsIngestion,
)
from apps.api.src.domain.data.earnings.models import EarningsEvent
from apps.api.src.domain.data.earnings.sql_repo import SqlEarningsRepo
from apps.api.src.domain.data.time import EventTime
from apps.api.src.ingestion.common import IngestionResult, quarantine_row
from apps.api.src.ingestion.content_hash import payload_content_hash


_SOURCE_TYPE = "earnings"
_REQUIRED = ("asset_id", "symbol", "event_date", "event_time", "source")


class NaiveTimestampError(ValueError):
    """Raised when a naive datetime arrives without source_timezone."""


def _parse_date(v) -> dt.date:
    if isinstance(v, dt.date) and not isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, str):
        return dt.date.fromisoformat(v)
    raise ValueError(f"unparseable date: {v!r}")


def _parse_ts(
    v, *, source_timezone: ZoneInfo | None = None,
) -> dt.datetime | None:
    """Strict parser. Returns UTC-aware datetime or None.

    - None                                -> None
    - aware datetime                      -> converted to UTC
    - naive datetime + source_timezone    -> localized then converted to UTC
    - naive datetime + NO source_timezone -> raises NaiveTimestampError
    - ISO-8601 string (with or without tz) -> same rules as datetime
    - anything else                       -> raises ValueError
    """
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        if v.tzinfo is None:
            if source_timezone is None:
                raise NaiveTimestampError(
                    "naive datetime without source_timezone"
                )
            return v.replace(tzinfo=source_timezone).astimezone(dt.timezone.utc)
        return v.astimezone(dt.timezone.utc)
    if isinstance(v, str):
        parsed = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            if source_timezone is None:
                raise NaiveTimestampError(
                    "naive ISO-8601 string without source_timezone"
                )
            return (
                parsed.replace(tzinfo=source_timezone).astimezone(dt.timezone.utc)
            )
        return parsed.astimezone(dt.timezone.utc)
    raise ValueError(f"unparseable timestamp: {v!r}")


def ingest_earnings(
    session: Session,
    records: Iterable[dict],
    *,
    source_timezone: ZoneInfo | None = None,
    dry_run: bool = False,
) -> IngestionResult:
    """Ingest earnings. Idempotent per natural key (asset_id, event_date).

    `source_timezone`: when provided, naive announcement_timestamps are
    interpreted in this zone. When None, naive timestamps are quarantined.
    """
    result = IngestionResult(source_type=_SOURCE_TYPE)
    repo = SqlEarningsRepo(session)

    for rec in records:
        result.total_in += 1

        source = str(rec.get("source") or "unknown")
        external_id = rec.get("external_id")

        # Raw-table content hash — deterministic over payload. Precheck
        # for existence (idempotent re-ingest → no-op at raw level).
        # JSON-safe payload copy (stringify datetimes/dates for the jsonb column).
        payload_jsonsafe = {
            k: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v)
            for k, v in rec.items()
        }
        raw_content_hash = payload_content_hash(source, payload_jsonsafe)
        existing_raw = session.execute(
            select(RawEarningsIngestion).where(
                RawEarningsIngestion.source == source,
                RawEarningsIngestion.content_hash == raw_content_hash,
            )
        ).scalar_one_or_none()
        if existing_raw is not None:
            raw = existing_raw
        else:
            raw = RawEarningsIngestion(
                source=source, external_id=external_id,
                payload=payload_jsonsafe,
                content_hash=raw_content_hash, status="pending",
            )
            session.add(raw)
            session.flush()
            result.raw_inserted += 1

        # Validate required fields
        missing = [k for k in _REQUIRED if not rec.get(k)]
        if missing:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="missing_required_field",
                reason_detail=f"missing: {missing}",
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"
            raw.rejection_reason = f"missing: {missing}"
            result.quarantined += 1
            result.quarantine_reasons["missing_required_field"] += 1
            continue

        try:
            event_date = _parse_date(rec["event_date"])
        except (ValueError, TypeError) as exc:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="bad_event_date", reason_detail=str(exc),
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"; raw.rejection_reason = "bad_event_date"
            result.quarantined += 1
            result.quarantine_reasons["bad_event_date"] += 1
            continue

        event_time_raw = rec["event_time"]
        try:
            event_time = EventTime(event_time_raw)
        except ValueError:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="bad_event_time",
                reason_detail=f"unknown value: {event_time_raw!r}",
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"; raw.rejection_reason = "bad_event_time"
            result.quarantined += 1
            result.quarantine_reasons["bad_event_time"] += 1
            continue

        try:
            ts = _parse_ts(
                rec.get("announcement_timestamp"),
                source_timezone=source_timezone,
            )
        except NaiveTimestampError as exc:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="naive_timestamp",
                reason_detail=str(exc),
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"
            raw.rejection_reason = "naive_timestamp"
            result.quarantined += 1
            result.quarantine_reasons["naive_timestamp"] += 1
            continue
        except (ValueError, TypeError) as exc:
            quarantine_row(
                session, source_type=_SOURCE_TYPE, source=source,
                reason="bad_announcement_timestamp",
                reason_detail=str(exc),
                raw_ingestion_id=raw.id, payload=dict(rec),
            )
            raw.status = "rejected"
            raw.rejection_reason = "bad_announcement_timestamp"
            result.quarantined += 1
            result.quarantine_reasons["bad_announcement_timestamp"] += 1
            continue

        event = EarningsEvent(
            symbol=str(rec["symbol"]).upper(),
            asset_id=str(rec["asset_id"]),
            event_date=event_date,
            event_time=event_time,
            announcement_timestamp=ts,
            announcement_timestamp_raw=rec.get("announcement_timestamp_raw"),
            fiscal_period=rec.get("fiscal_period"),
            source=source,
        )

        had_existing = repo.get_event(event.symbol, event.event_date) is not None

        if dry_run:
            raw.status = "pending"
            continue

        try:
            repo.upsert(event)
            raw.status = "normalized"
            if had_existing:
                result.updated += 1
            else:
                result.inserted += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("[ingest.earnings] upsert failed: {}", exc)
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
    logger.info("[ingest.earnings] {}", result.as_dict())
    return result
