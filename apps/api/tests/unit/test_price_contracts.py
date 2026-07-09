"""Sprint 4 — dataset-level ingest data contracts.

Pins the three-verdict semantics:
  * one malformed row → QUARANTINE_AND_CONTINUE (pipeline survives);
  * widespread corruption → ABORT_DATASET (fail closed, zero rows out);
  * quarantined rows never appear in the accepted list (never reach
    inference);
  * no silent auto-repair (suspicious rows are excluded, not mutated);
  * structured report is JSON-safe with provenance and no secrets.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.prices.canonical import CanonicalBar
from apps.api.src.domain.prices.contracts import (
    ContractThresholds,
    DatasetVerdict,
    evaluate_dataset,
)

NOW = dt.datetime(2026, 7, 9, 12, 0, tzinfo=dt.timezone.utc)


def _bar(
    date: str, *, close: str = "100", open_: str = "100", high: str = "101",
    low: str = "99", symbol: str = "TEST", adjusted: str | None = "100",
    volume: int | None = 1000, fetched_at: dt.datetime | None = NOW,
) -> CanonicalBar:
    return CanonicalBar(
        symbol=symbol,
        trade_date=dt.date.fromisoformat(date),
        open=Decimal(open_), high=Decimal(high), low=Decimal(low),
        close=Decimal(close),
        adjusted_close=Decimal(adjusted) if adjusted is not None else None,
        volume=volume,
        source="test-provider",
        fetched_at=fetched_at,
    )


def _clean_week() -> list[CanonicalBar]:
    return [_bar(f"2026-07-0{d}") for d in range(6, 10)]  # Mon 6 – Thu 9


def test_clean_dataset_accepts_everything() -> None:
    accepted, report = evaluate_dataset(
        _clean_week(), symbol="TEST", provider="test-provider", now=NOW,
    )
    assert report.verdict is DatasetVerdict.ACCEPT
    assert len(accepted) == 4
    assert report.rows_quarantined == 0
    assert report.issues == []


def test_single_malformed_row_quarantines_and_continues() -> None:
    bars = _clean_week()
    bars.append(_bar("2026-07-03", close="-5", open_="-5"))  # negative close
    accepted, report = evaluate_dataset(
        bars, symbol="TEST", provider="test-provider", now=NOW,
        thresholds=ContractThresholds(abort_reject_fraction=0.5),
    )
    assert report.verdict is DatasetVerdict.QUARANTINE_AND_CONTINUE
    assert len(accepted) == 4                     # pipeline survives
    assert report.rows_quarantined == 1
    assert any(i.rule == "bar_invalid" for i in report.issues)
    # quarantined row never reaches the accepted list
    assert all(b.close > 0 for b in accepted)


def test_widespread_corruption_fails_closed() -> None:
    bars = [_bar(f"2026-07-0{d}", close="-1", open_="-1") for d in range(1, 8)]
    bars.append(_bar("2026-07-08"))
    accepted, report = evaluate_dataset(
        bars, symbol="TEST", provider="test-provider", now=NOW,
    )
    assert report.verdict is DatasetVerdict.ABORT_DATASET
    assert accepted == []                          # nothing may be written
    assert "fraction" in (report.abort_reason or "")


def test_future_dated_rows_quarantined_and_escalate() -> None:
    bars = _clean_week() + [_bar("2026-07-20")]
    accepted, report = evaluate_dataset(
        bars, symbol="TEST", provider="test-provider", now=NOW,
    )
    assert report.verdict is DatasetVerdict.QUARANTINE_AND_CONTINUE
    assert all(b.trade_date <= NOW.date() for b in accepted)

    many_future = _clean_week() + [
        _bar(f"2026-08-0{d}") for d in range(1, 6)
    ]
    accepted2, report2 = evaluate_dataset(
        many_future, symbol="TEST", provider="test-provider", now=NOW,
    )
    assert report2.verdict is DatasetVerdict.ABORT_DATASET
    assert accepted2 == []


def test_duplicate_dates_quarantined() -> None:
    bars = _clean_week() + [_bar("2026-07-08", close="200", open_="200",
                                 high="201", low="199")]
    accepted, report = evaluate_dataset(
        bars, symbol="TEST", provider="test-provider", now=NOW,
    )
    assert len([b for b in accepted if b.trade_date == dt.date(2026, 7, 8)]) == 1
    assert any(i.rule == "duplicate_bar" for i in report.issues)


def test_extreme_jump_quarantined_not_repaired() -> None:
    bars = [_bar("2026-07-06"), _bar("2026-07-07")]
    bars.append(_bar("2026-07-08", close="500", open_="500", high="501", low="499"))
    accepted, report = evaluate_dataset(
        bars, symbol="TEST", provider="test-provider", now=NOW,
    )
    assert any(i.rule == "extreme_jump" for i in report.issues)
    # the suspicious row is EXCLUDED — its values are never altered
    assert all(b.close != Decimal("500") for b in accepted)


def test_symbol_mismatch_and_naive_timestamp_rejected() -> None:
    bars = _clean_week()
    bars.append(_bar("2026-07-03", symbol="OTHER"))
    bars.append(_bar("2026-07-02", fetched_at=NOW.replace(tzinfo=None)))
    accepted, report = evaluate_dataset(
        bars, symbol="TEST", provider="test-provider", now=NOW,
        thresholds=ContractThresholds(abort_reject_fraction=0.6),
    )
    rules = {i.rule for i in report.issues}
    assert "symbol_mismatch" in rules
    assert "naive_fetched_at" in rules
    assert len(accepted) == 4


def test_staleness_flag_when_provider_outage() -> None:
    old = [_bar("2026-06-22"), _bar("2026-06-23")]
    accepted, report = evaluate_dataset(
        old, symbol="TEST", provider="test-provider", now=NOW,
    )
    assert report.verdict is DatasetVerdict.QUARANTINE_AND_CONTINUE
    assert any(f.startswith("stale_provider") for f in report.dataset_flags)
    assert len(accepted) == 2                      # stale ≠ invalid


def test_null_budget_flag() -> None:
    bars = [_bar(f"2026-07-0{d}", adjusted=None) for d in range(6, 10)]
    _, report = evaluate_dataset(
        bars, symbol="TEST", provider="test-provider", now=NOW,
    )
    assert any(
        f.startswith("null_budget_adjusted_close") for f in report.dataset_flags
    )


def test_empty_dataset_aborts() -> None:
    accepted, report = evaluate_dataset(
        [], symbol="TEST", provider="test-provider", now=NOW,
    )
    assert report.verdict is DatasetVerdict.ABORT_DATASET
    assert accepted == []


def test_report_is_json_safe_with_provenance_and_bounded() -> None:
    import json

    bars = _clean_week() + [
        _bar("2026-07-03", close="-1", open_="-1") for _ in range(60)
    ]
    _, report = evaluate_dataset(
        bars, symbol="TEST", provider="test-provider", now=NOW,
        thresholds=ContractThresholds(abort_reject_fraction=0.99),
    )
    payload = report.to_dict()
    encoded = json.dumps(payload)                  # must not raise
    assert payload["provider"] == "test-provider"
    assert payload["evaluated_at"] == NOW.isoformat()
    assert len(payload["issues"]) <= 50            # bounded
    assert payload["issues_truncated"] >= 0
    assert "password" not in encoded and "secret" not in encoded
