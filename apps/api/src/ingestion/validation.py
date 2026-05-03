"""Post-ingest validation / audit report.

Reads normalized + raw + quarantine tables and produces a structured
summary: counts, completeness percentages, duplicate conflicts, missing
join partners. Idempotent; safe to run anywhere.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    ConsensusEstimateRow,
    EarningsEventRow,
    EventQuarantine,
    RawConsensusIngestion,
    RawEarningsIngestion,
    RawSharesIngestion,
    SharesOutstandingRow,
)


@dataclass
class ValidationReport:
    # Counts per normalized table
    earnings_events: int = 0
    shares_records: int = 0
    consensus_records: int = 0
    # Counts per raw table (by status)
    raw_earnings_by_status: dict[str, int] = field(default_factory=dict)
    raw_shares_by_status: dict[str, int] = field(default_factory=dict)
    raw_consensus_by_status: dict[str, int] = field(default_factory=dict)
    # Quarantine
    quarantine_by_reason: dict[str, int] = field(default_factory=dict)
    quarantine_by_source_type: dict[str, int] = field(default_factory=dict)
    # Completeness percentages across normalized earnings_event rows
    pct_with_eps_actual: float = 0.0
    pct_with_eps_consensus: float = 0.0
    pct_with_revenue_actual: float = 0.0
    pct_with_revenue_consensus: float = 0.0
    pct_with_shares: float = 0.0
    # Integrity flags
    invalid_chronology_count: int = 0           # shares filing < effective
    orphan_events_without_actual: int = 0        # no EPS actual nor rev actual
    # Phase 10.6 expanded orphan / integrity counters
    events_with_actual_no_consensus: int = 0     # actual reported but no pre-event consensus
    events_with_consensus_no_actual: int = 0     # consensus published but no actual
    events_missing_shares: int = 0               # no shares_outstanding filing ≤ event_date
    events_impossible_timing: int = 0            # e.g., before_open w/ ts > event_date 09:30 ET
    events_naive_timestamp_rejected: int = 0     # from quarantine (reason=naive_timestamp)
    events_ambiguous_unit_rejected: int = 0      # from quarantine (reason=ambiguous_unit)
    events_unit_metric_mismatch: int = 0         # from quarantine
    # Provenance
    distinct_sources_earnings: list[str] = field(default_factory=list)
    distinct_sources_shares: list[str] = field(default_factory=list)
    distinct_sources_consensus: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "earnings_events": self.earnings_events,
            "shares_records": self.shares_records,
            "consensus_records": self.consensus_records,
            "raw_earnings_by_status": self.raw_earnings_by_status,
            "raw_shares_by_status": self.raw_shares_by_status,
            "raw_consensus_by_status": self.raw_consensus_by_status,
            "quarantine_by_reason": self.quarantine_by_reason,
            "quarantine_by_source_type": self.quarantine_by_source_type,
            "completeness_pct": {
                "eps_actual": round(self.pct_with_eps_actual, 4),
                "eps_consensus": round(self.pct_with_eps_consensus, 4),
                "revenue_actual": round(self.pct_with_revenue_actual, 4),
                "revenue_consensus": round(self.pct_with_revenue_consensus, 4),
                "shares": round(self.pct_with_shares, 4),
            },
            "integrity": {
                "invalid_chronology_shares": self.invalid_chronology_count,
                "orphan_events_without_actual": self.orphan_events_without_actual,
                "events_with_actual_no_consensus": self.events_with_actual_no_consensus,
                "events_with_consensus_no_actual": self.events_with_consensus_no_actual,
                "events_missing_shares": self.events_missing_shares,
                "events_impossible_timing": self.events_impossible_timing,
                "events_naive_timestamp_rejected": self.events_naive_timestamp_rejected,
                "events_ambiguous_unit_rejected": self.events_ambiguous_unit_rejected,
                "events_unit_metric_mismatch": self.events_unit_metric_mismatch,
            },
            "distinct_sources": {
                "earnings": self.distinct_sources_earnings,
                "shares": self.distinct_sources_shares,
                "consensus": self.distinct_sources_consensus,
            },
        }


def _count_by_status(session: Session, model) -> dict[str, int]:
    rows = session.execute(
        select(model.status, func.count(model.id)).group_by(model.status)
    ).all()
    return {s: int(c) for s, c in rows}


def _distinct_sources(session: Session, model) -> list[str]:
    rows = session.execute(
        select(model.source).distinct().order_by(model.source)
    ).all()
    return [r[0] for r in rows]


def _completeness_pct(
    session: Session, event_rows: list[EarningsEventRow],
) -> dict[str, float]:
    """For each earnings event, check PIT-available consensus+actual+shares.

    Uses simple presence check (has ANY row matching natural key) — this
    mirrors the PITDataContext.build_event_record semantics from the
    ingestion-auditor's perspective. Does NOT apply PIT cutoffs here; we
    are measuring catalog completeness, not lookup correctness.
    """
    if not event_rows:
        return {
            "eps_actual": 0.0, "eps_consensus": 0.0,
            "revenue_actual": 0.0, "revenue_consensus": 0.0, "shares": 0.0,
        }

    counts = Counter()
    total = len(event_rows)

    for e in event_rows:
        # eps actual / consensus
        for metric, est in (
            ("eps", "actual"), ("eps", "consensus"),
            ("revenue", "actual"), ("revenue", "consensus"),
        ):
            present = session.execute(
                select(ConsensusEstimateRow.id).where(
                    ConsensusEstimateRow.asset_id == e.asset_id,
                    ConsensusEstimateRow.event_date == e.event_date,
                    ConsensusEstimateRow.metric == metric,
                    ConsensusEstimateRow.estimate_type == est,
                ).limit(1)
            ).scalar_one_or_none() is not None
            if present:
                counts[f"{metric}_{est}"] += 1
        # shares: any filing on or before event_date
        shares_present = session.execute(
            select(SharesOutstandingRow.id).where(
                SharesOutstandingRow.asset_id == e.asset_id,
                SharesOutstandingRow.filing_date <= e.event_date,
            ).limit(1)
        ).scalar_one_or_none() is not None
        if shares_present:
            counts["shares"] += 1

    return {
        "eps_actual": counts["eps_actual"] / total,
        "eps_consensus": counts["eps_consensus"] / total,
        "revenue_actual": counts["revenue_actual"] / total,
        "revenue_consensus": counts["revenue_consensus"] / total,
        "shares": counts["shares"] / total,
    }


def run_validation(session: Session) -> ValidationReport:
    report = ValidationReport()

    # Normalized counts
    report.earnings_events = int(
        session.execute(select(func.count(EarningsEventRow.id))).scalar_one()
    )
    report.shares_records = int(
        session.execute(select(func.count(SharesOutstandingRow.id))).scalar_one()
    )
    report.consensus_records = int(
        session.execute(select(func.count(ConsensusEstimateRow.id))).scalar_one()
    )

    # Raw counts by status
    report.raw_earnings_by_status = _count_by_status(session, RawEarningsIngestion)
    report.raw_shares_by_status = _count_by_status(session, RawSharesIngestion)
    report.raw_consensus_by_status = _count_by_status(session, RawConsensusIngestion)

    # Quarantine breakdown
    q_reason = session.execute(
        select(EventQuarantine.reason, func.count(EventQuarantine.id))
        .group_by(EventQuarantine.reason)
    ).all()
    report.quarantine_by_reason = {r: int(c) for r, c in q_reason}
    q_src = session.execute(
        select(EventQuarantine.source_type, func.count(EventQuarantine.id))
        .group_by(EventQuarantine.source_type)
    ).all()
    report.quarantine_by_source_type = {s: int(c) for s, c in q_src}

    # Distinct sources
    report.distinct_sources_earnings = _distinct_sources(session, EarningsEventRow)
    report.distinct_sources_shares = _distinct_sources(session, SharesOutstandingRow)
    report.distinct_sources_consensus = _distinct_sources(session, ConsensusEstimateRow)

    # Completeness
    event_rows = list(session.execute(select(EarningsEventRow)).scalars().all())
    pcts = _completeness_pct(session, event_rows)
    report.pct_with_eps_actual = pcts["eps_actual"]
    report.pct_with_eps_consensus = pcts["eps_consensus"]
    report.pct_with_revenue_actual = pcts["revenue_actual"]
    report.pct_with_revenue_consensus = pcts["revenue_consensus"]
    report.pct_with_shares = pcts["shares"]

    # Integrity: shares filing < effective (SHOULD be zero — ingestion rejects)
    bad_chron = session.execute(
        select(func.count(SharesOutstandingRow.id)).where(
            SharesOutstandingRow.filing_date < SharesOutstandingRow.effective_date,
        )
    ).scalar_one()
    report.invalid_chronology_count = int(bad_chron)

    # Orphan events — no actual recorded at all
    if event_rows:
        orphans = 0
        actual_no_cons = 0
        cons_no_actual = 0
        missing_shares = 0
        impossible_timing = 0
        for e in event_rows:
            actual_seen = session.execute(
                select(ConsensusEstimateRow.id).where(
                    ConsensusEstimateRow.asset_id == e.asset_id,
                    ConsensusEstimateRow.event_date == e.event_date,
                    ConsensusEstimateRow.estimate_type == "actual",
                ).limit(1)
            ).scalar_one_or_none() is not None
            cons_seen = session.execute(
                select(ConsensusEstimateRow.id).where(
                    ConsensusEstimateRow.asset_id == e.asset_id,
                    ConsensusEstimateRow.event_date == e.event_date,
                    ConsensusEstimateRow.estimate_type == "consensus",
                ).limit(1)
            ).scalar_one_or_none() is not None

            if not actual_seen:
                orphans += 1
            if actual_seen and not cons_seen:
                actual_no_cons += 1
            if cons_seen and not actual_seen:
                cons_no_actual += 1

            # Missing shares as of event_date
            shares_seen = session.execute(
                select(SharesOutstandingRow.id).where(
                    SharesOutstandingRow.asset_id == e.asset_id,
                    SharesOutstandingRow.filing_date <= e.event_date,
                ).limit(1)
            ).scalar_one_or_none() is not None
            if not shares_seen:
                missing_shares += 1

            # Impossible timing checks. SQLite/Postgres round-trip may
            # produce naive datetimes; coerce to UTC for comparison.
            ts = e.announcement_timestamp
            if ts is not None:
                if ts.tzinfo is None:
                    import datetime as _dt
                    ts = ts.replace(tzinfo=_dt.timezone.utc)
                import datetime as _dt
                if e.event_time == "before_open":
                    cutoff = _dt.datetime.combine(
                        e.event_date, _dt.time(15, 0), _dt.timezone.utc,
                    )
                    if ts > cutoff:
                        impossible_timing += 1
                elif e.event_time == "after_close":
                    cutoff = _dt.datetime.combine(
                        e.event_date, _dt.time(19, 30), _dt.timezone.utc,
                    )
                    if ts < cutoff:
                        impossible_timing += 1

        report.orphan_events_without_actual = orphans
        report.events_with_actual_no_consensus = actual_no_cons
        report.events_with_consensus_no_actual = cons_no_actual
        report.events_missing_shares = missing_shares
        report.events_impossible_timing = impossible_timing

    # Phase 10.6 reason counters (pulled from quarantine table)
    report.events_naive_timestamp_rejected = (
        report.quarantine_by_reason.get("naive_timestamp", 0)
    )
    report.events_ambiguous_unit_rejected = (
        report.quarantine_by_reason.get("ambiguous_unit", 0)
    )
    report.events_unit_metric_mismatch = (
        report.quarantine_by_reason.get("unit_metric_mismatch", 0)
    )

    return report
