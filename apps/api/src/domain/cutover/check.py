"""Cutover readiness check — Phase 1.6 hardened edition.

Additions over Phase 1.5:
  - Strict consecutive-business-day enforcement (no gaps between weekdays)
  - Signal-count variance detection (warning only; non-blocking)
  - Diff stability metrics: max & avg score delta across window
  - Explicit per-day failure log lines
  - Structured summary with consecutive_days_ok, max/avg_score_delta,
    signal_count_variance
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass, field
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import ShadowRunLog

REQUIRED_CONSECUTIVE_DAYS = 7
CONSISTENCY_MAX_SPIKE = 5.0              # hard block (spike factor vs median)
SIGNAL_COUNT_VARIANCE_WARN_RATIO = 0.5   # warn if |day-median| > 50% of median


@dataclass
class CutoverReport:
    ready: bool
    required_days: int

    # Block-level reasons (cause ready=False)
    reasons: list[str] = field(default_factory=list)

    # Detailed state
    rows_examined: int = 0
    missing_days: list[str] = field(default_factory=list)
    failing_days: list[str] = field(default_factory=list)
    non_consecutive: bool = False

    # Phase 1.6 enriched summary
    consecutive_days_ok: int = 0
    max_score_delta: float = 0.0
    avg_score_delta: float = 0.0
    signal_count_variance: str = "stable"   # stable | warn | unknown

    # Raw data
    signals_counts: list[int] = field(default_factory=list)
    ranked_counts: list[int] = field(default_factory=list)

    # Warnings (non-blocking)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "required_days": self.required_days,
            "reasons": self.reasons,
            "warnings": self.warnings,
            "rows_examined": self.rows_examined,
            "missing_days": self.missing_days,
            "failing_days": self.failing_days,
            "non_consecutive": self.non_consecutive,
            "consecutive_days_ok": self.consecutive_days_ok,
            "max_score_delta": self.max_score_delta,
            "avg_score_delta": self.avg_score_delta,
            "signal_count_variance": self.signal_count_variance,
            "signals_counts": self.signals_counts,
            "ranked_counts": self.ranked_counts,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _business_days_back(end: dt.date, n: int) -> list[dt.date]:
    """Last N business days (Mon-Fri) ending at `end` inclusive. Sorted asc."""
    out: list[dt.date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return sorted(out)


def _next_business_day(d: dt.date) -> dt.date:
    step = d + dt.timedelta(days=1)
    while step.weekday() >= 5:
        step += dt.timedelta(days=1)
    return step


def _is_consecutive_business(prev: dt.date, curr: dt.date) -> bool:
    """True iff `curr` is the next business day after `prev`. Gaps → False."""
    return _next_business_day(prev) == curr


def _detect_non_consecutive(days: list[dt.date]) -> bool:
    """Return True if any adjacent pair in sorted `days` is not consecutive."""
    for a, b in zip(days, days[1:]):
        if not _is_consecutive_business(a, b):
            return True
    return False


def _trailing_streak(present: list[dt.date], today: dt.date) -> int:
    """Length of trailing streak of consecutive business days ending at/before
    `today` (and present in `present`). Stops at first gap."""
    if not present:
        return 0
    last = present[-1]
    # If the most recent present day isn't today OR a prior business day contiguous
    # to today, we still count backwards from last.
    streak = 1
    prev = last
    for d in reversed(present[:-1]):
        if _is_consecutive_business(d, prev):
            streak += 1
            prev = d
        else:
            break
    return streak


def _spike_block(values: list[int]) -> bool:
    non_zero = [v for v in values if v > 0]
    if len(non_zero) < 3:
        return False
    non_zero.sort()
    median = non_zero[len(non_zero) // 2]
    if median <= 0:
        return False
    return max(non_zero) > CONSISTENCY_MAX_SPIKE * median


def _variance_warn(values: list[int]) -> tuple[str, list[str]]:
    """Returns (label, warnings). 'stable' | 'warn' | 'unknown'."""
    non_zero = [v for v in values if v > 0]
    if len(non_zero) < 3:
        return "unknown", []
    non_zero.sort()
    median = non_zero[len(non_zero) // 2]
    if median <= 0:
        return "unknown", []
    warnings: list[str] = []
    for v in values:
        if v == 0:
            continue
        if abs(v - median) > SIGNAL_COUNT_VARIANCE_WARN_RATIO * median:
            warnings.append(
                f"signal_count_outlier value={v} median={median}"
            )
    return ("warn" if warnings else "stable"), warnings


def _dec_to_float(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------


def check_cutover_ready(
    session: Session,
    *,
    today: dt.date | None = None,
    required_days: int = REQUIRED_CONSECUTIVE_DAYS,
) -> CutoverReport:
    today = today or dt.date.today()
    window = _business_days_back(today, required_days)

    stmt = (
        select(ShadowRunLog)
        .where(ShadowRunLog.as_of_date.in_(window))
        .order_by(ShadowRunLog.as_of_date.asc())
    )
    rows = list(session.scalars(stmt))
    by_day = {r.as_of_date: r for r in rows}

    report = CutoverReport(ready=True, required_days=required_days)
    report.rows_examined = len(rows)

    # Rule 1: no missing runs
    for d in window:
        if d not in by_day:
            report.ready = False
            report.missing_days.append(d.isoformat())
    if report.missing_days:
        report.reasons.append(
            f"missing_runs={len(report.missing_days)}/{required_days}"
        )

    # Rule 2: every row has diff_status == 'ok'
    for r in rows:
        if r.diff_status != "ok":
            report.ready = False
            report.failing_days.append(r.as_of_date.isoformat())
            logger.error(
                "[cutover] FAILURE as_of={} diff_status={} reason={} "
                "asset_set_match={} topn_match={} reorder_count={}",
                r.as_of_date, r.diff_status,
                r.diff_reason, r.asset_set_match, r.topn_match,
                r.reorder_count,
            )
    if report.failing_days:
        report.reasons.append(f"diff_failures={len(report.failing_days)}")

    # Rule 3: consecutive business days
    present_days = sorted(by_day.keys())
    if len(present_days) >= 2 and _detect_non_consecutive(present_days):
        report.ready = False
        report.non_consecutive = True
        report.reasons.append("non_consecutive_days_detected")
    report.consecutive_days_ok = _trailing_streak(present_days, today)

    # Rule 4: hard spike blocks
    report.signals_counts = [r.signals_count for r in rows]
    report.ranked_counts = [r.ranked_count for r in rows]
    if _spike_block(report.signals_counts):
        report.ready = False
        report.reasons.append("signals_count_spike_detected")
    if _spike_block(report.ranked_counts):
        report.ready = False
        report.reasons.append("ranked_count_spike_detected")

    # Rule 5: non-empty sanity — at least 1 signal on majority of days
    positive_days = sum(1 for c in report.signals_counts if c > 0)
    if rows and positive_days < (required_days // 2):
        report.ready = False
        report.reasons.append(
            f"too_many_empty_days positive={positive_days}/{required_days}"
        )

    # Phase 1.6: soft variance warn (50% deviation from median)
    variance_label, variance_warnings = _variance_warn(report.signals_counts)
    report.signal_count_variance = variance_label
    report.warnings.extend(variance_warnings)
    if variance_warnings:
        for w in variance_warnings:
            logger.warning("[cutover] WARNING {}", w)

    # Phase 1.6: diff stability metrics
    deltas = [
        _dec_to_float(r.max_score_delta)
        for r in rows if r.max_score_delta is not None
    ]
    if deltas:
        report.max_score_delta = round(max(deltas), 6)
        report.avg_score_delta = round(statistics.fmean(deltas), 6)

    return report
