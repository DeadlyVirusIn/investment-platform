"""Dataset-level ingest data contracts (Elite ArthOS Sprint 4).

Sits ON TOP of the existing per-bar layer (`normalize.to_canonical` →
`validate.validate_bar`): those decide whether a single bar is sane; this
module decides whether the DATASET a provider returned is trustworthy
enough to write, and produces a structured, Trust-Center-ready report.

Three verdicts (the contract's whole point):

  * ACCEPT                  — write the accepted rows.
  * QUARANTINE_AND_CONTINUE — write the accepted rows; quarantined rows are
                              excluded (they must never reach model
                              inference) and the report says exactly why.
                              One malformed row must not kill the nightly
                              pipeline.
  * ABORT_DATASET           — write NOTHING. Widespread corruption fails
                              closed (e.g. a provider regression returning
                              garbage for every row must not poison
                              price_bar via 200 individually-plausible
                              upserts).

Design rules:
  * No silent auto-repair — suspicious values are quarantined, never
    "fixed". (Repairing hides provider regressions; the 2026-06 Polygon
    split-only-adjusted bug would have been INVISIBLE under auto-repair.)
  * Structured report with provider + timestamp provenance, JSON-safe via
    ``to_dict()`` for the future Admin/Trust Center surfaces. No secrets
    ever enter reports (symbols, dates, counts, rule names only).
  * Pure functions, no DB, no I/O — unit-testable without fixtures.

Why not pandera (evaluated per the external review): pandera validates
DataFrames all-or-error per check; the required row-quarantine +
dataset-abort escalation semantics would have to be built around it
anyway, our ingest deals in lists of CanonicalBar dataclasses (not
DataFrames), and this keeps prod dependencies at zero. Revisit pandera if
ingest ever becomes DataFrame-shaped.
"""

from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from apps.api.src.domain.prices.canonical import CanonicalBar
from apps.api.src.domain.prices.validate import validate_bar


class DatasetVerdict(str, enum.Enum):
    ACCEPT = "accept"
    QUARANTINE_AND_CONTINUE = "quarantine_and_continue"
    ABORT_DATASET = "abort_dataset"


@dataclass(frozen=True)
class ContractThresholds:
    """Tunable budgets. Defaults are deliberately conservative."""

    # Fraction of rows failing hard validation at/above which the whole
    # dataset is untrustworthy → ABORT (fail closed).
    abort_reject_fraction: float = 0.10
    # Newest bar older than this (vs `now`) → provider staleness flag.
    max_stale_trading_days: int = 5
    # Fraction of rows missing adjusted_close/volume above which the
    # dataset is flagged (nulls quarantine nothing by themselves — the
    # per-bar layer already warns — but a blown budget means a provider
    # regression, not noise).
    null_budget_fraction: float = 0.20
    # Bars dated in the future are always quarantined; more than this many
    # means the provider's clock/feed is broken → ABORT.
    abort_future_rows: int = 3
    # Day-over-day move at/above this quarantines the row (the per-bar
    # layer only WARNS at 30%). Real halts/splits exist, so this is high.
    quarantine_jump_fraction: Decimal = Decimal("0.80")


@dataclass
class RowIssue:
    rule: str
    symbol: str
    trade_date: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "symbol": self.symbol,
            "trade_date": self.trade_date,
            "detail": self.detail,
        }


@dataclass
class DatasetContractReport:
    symbol: str
    provider: str
    evaluated_at: str
    rows_total: int = 0
    rows_accepted: int = 0
    rows_quarantined: int = 0
    verdict: DatasetVerdict = DatasetVerdict.ACCEPT
    abort_reason: str | None = None
    dataset_flags: list[str] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe, secret-free; shaped for Admin/Trust Center storage."""
        return {
            "symbol": self.symbol,
            "provider": self.provider,
            "evaluated_at": self.evaluated_at,
            "rows_total": self.rows_total,
            "rows_accepted": self.rows_accepted,
            "rows_quarantined": self.rows_quarantined,
            "verdict": self.verdict.value,
            "abort_reason": self.abort_reason,
            "dataset_flags": list(self.dataset_flags),
            "issues": [i.to_dict() for i in self.issues[:50]],  # bounded
            "issues_truncated": max(0, len(self.issues) - 50),
        }


def _is_tz_aware(ts: dt.datetime | None) -> bool:
    return ts is not None and ts.tzinfo is not None


def evaluate_dataset(
    bars: list[CanonicalBar],
    *,
    symbol: str,
    provider: str,
    now: dt.datetime,
    thresholds: ContractThresholds | None = None,
) -> tuple[list[CanonicalBar], DatasetContractReport]:
    """Apply the dataset contract. Returns (accepted_bars, report).

    Caller rule: when ``report.verdict is ABORT_DATASET`` the returned
    accepted list is EMPTY by construction — nothing may be written.
    Quarantined rows are excluded from the returned list in every verdict.
    """
    t = thresholds or ContractThresholds()
    report = DatasetContractReport(
        symbol=symbol.upper(),
        provider=provider,
        evaluated_at=now.isoformat(),
        rows_total=len(bars),
    )

    if not bars:
        report.verdict = DatasetVerdict.ABORT_DATASET
        report.abort_reason = "empty dataset"
        return [], report

    today = now.date()
    ordered = sorted(bars, key=lambda b: (b.trade_date, b.symbol))

    accepted: list[CanonicalBar] = []
    hard_rejects = 0
    future_rows = 0
    null_adjusted = 0
    null_volume = 0
    seen_dates: set[dt.date] = set()
    prior_close: Decimal | None = None

    for bar in ordered:
        date_str = bar.trade_date.isoformat() if bar.trade_date else "?"

        # symbol normalized + consistent with the dataset's symbol
        if not bar.symbol or bar.symbol.upper() != report.symbol:
            hard_rejects += 1
            report.issues.append(RowIssue(
                "symbol_mismatch", bar.symbol or "?", date_str,
                f"row symbol {bar.symbol!r} != dataset {report.symbol}",
            ))
            continue

        # timezone consistency of provenance timestamp
        if not _is_tz_aware(bar.fetched_at):
            report.issues.append(RowIssue(
                "naive_fetched_at", bar.symbol, date_str,
                "fetched_at missing timezone — provenance untrustworthy",
            ))
            hard_rejects += 1
            continue

        # future-dated rows are always quarantined
        if bar.trade_date and bar.trade_date > today:
            future_rows += 1
            report.issues.append(RowIssue(
                "future_dated", bar.symbol, date_str,
                f"trade_date {date_str} > as-of {today.isoformat()}",
            ))
            continue

        # primary-key duplicate inside the dataset (post-dedupe defense)
        if bar.trade_date in seen_dates:
            report.issues.append(RowIssue(
                "duplicate_bar", bar.symbol, date_str,
                "second row for the same trade_date",
            ))
            continue

        # existing per-bar layer: OHLC positivity/ordering etc.
        res = validate_bar(bar, prior_close=prior_close)
        if not res.ok:
            hard_rejects += 1
            report.issues.append(RowIssue(
                "bar_invalid", bar.symbol, date_str, res.reject_reason or "?",
            ))
            continue

        # extreme jump → quarantine the row (per-bar layer only warns)
        if prior_close is not None and prior_close > 0:
            change = abs(bar.close - prior_close) / prior_close
            if change >= t.quarantine_jump_fraction:
                report.issues.append(RowIssue(
                    "extreme_jump", bar.symbol, date_str,
                    f"|Δclose| {change:.1%} >= {t.quarantine_jump_fraction:.0%}",
                ))
                # do NOT advance prior_close: the jump row is suspect
                continue

        if bar.adjusted_close is None:
            null_adjusted += 1
        if bar.volume is None:
            null_volume += 1

        seen_dates.add(bar.trade_date)
        prior_close = bar.close
        accepted.append(bar)

    report.rows_accepted = len(accepted)
    report.rows_quarantined = report.rows_total - report.rows_accepted

    # ---- dataset-level escalation (fail closed on widespread problems) ----
    reject_fraction = hard_rejects / report.rows_total
    if reject_fraction >= t.abort_reject_fraction:
        report.verdict = DatasetVerdict.ABORT_DATASET
        report.abort_reason = (
            f"hard-reject fraction {reject_fraction:.1%} >= "
            f"{t.abort_reject_fraction:.0%} — dataset untrustworthy"
        )
        return [], report

    if future_rows > t.abort_future_rows:
        report.verdict = DatasetVerdict.ABORT_DATASET
        report.abort_reason = (
            f"{future_rows} future-dated rows > {t.abort_future_rows} — "
            "provider clock/feed broken"
        )
        return [], report

    if not accepted:
        report.verdict = DatasetVerdict.ABORT_DATASET
        report.abort_reason = "no rows survived the contract"
        return [], report

    # ---- dataset flags (quarantine-level, pipeline continues) ----
    newest = max(b.trade_date for b in accepted)
    stale_days = _weekdays_between(newest, today)
    if stale_days > t.max_stale_trading_days:
        report.dataset_flags.append(
            f"stale_provider: newest bar {newest.isoformat()} is "
            f"{stale_days} weekdays old (budget {t.max_stale_trading_days})"
        )

    if null_adjusted / len(accepted) > t.null_budget_fraction:
        report.dataset_flags.append(
            f"null_budget_adjusted_close: {null_adjusted}/{len(accepted)}"
        )
    if null_volume / len(accepted) > t.null_budget_fraction:
        report.dataset_flags.append(
            f"null_budget_volume: {null_volume}/{len(accepted)}"
        )

    if report.rows_quarantined or report.dataset_flags:
        report.verdict = DatasetVerdict.QUARANTINE_AND_CONTINUE
    else:
        report.verdict = DatasetVerdict.ACCEPT
    return accepted, report


def _weekdays_between(start: dt.date, end: dt.date) -> int:
    """Weekday count in (start, end] — cheap staleness proxy (no holiday
    calendar; a holiday-aware budget just means a slightly larger
    ``max_stale_trading_days``)."""
    if end <= start:
        return 0
    days = 0
    cur = start
    while cur < end:
        cur += dt.timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days
