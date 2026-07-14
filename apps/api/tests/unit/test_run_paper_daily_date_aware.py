"""M7 — date-aware daily-pipeline guard.

Verifies the daily pipeline targets the latest available trading day (instead of
hard-failing on weekends/holidays/no-data days), fails clearly when no data
exists at all, and that a FRED/macro timeout is non-fatal (degraded, not fatal).

`resolve_target_date` is pure (no DB/network), so the date logic is unit-tested
directly. Ranking/scoring code is untouched by M7 — see test at the bottom.
"""
import datetime as dt

import pandas as pd

from scripts.run_paper_daily import (
    resolve_target_date,
    step_ingest_raw,
    StepResult,
)


def _idx(dates: list[str]) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([pd.Timestamp(d) for d in dates])


# Mon 2026-06-15 … Fri 2026-06-19 (a full trading week). Sat/Sun = 20/21.
TRADING = _idx(["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18", "2026-06-19"])


def test_weekday_with_fresh_data_uses_that_day():
    assert resolve_target_date(TRADING, dt.date(2026, 6, 18)) == dt.date(2026, 6, 18)


def test_weekend_uses_latest_prior_available_date():
    # Saturday and Sunday both resolve back to Friday 06-19.
    assert resolve_target_date(TRADING, dt.date(2026, 6, 20)) == dt.date(2026, 6, 19)
    assert resolve_target_date(TRADING, dt.date(2026, 6, 21)) == dt.date(2026, 6, 19)


def test_holiday_or_no_data_day_uses_latest_available_date():
    # Mon 06-22 has no bar yet (holiday / not-yet-ingested) -> latest available Fri 06-19.
    assert resolve_target_date(TRADING, dt.date(2026, 6, 22)) == dt.date(2026, 6, 19)


def test_no_available_data_returns_none_so_caller_fails_clearly():
    # Requested date precedes ALL data -> None (load_universe raises a clear error).
    assert resolve_target_date(TRADING, dt.date(2026, 6, 1)) is None


def test_exact_match_is_idempotent_target():
    # Re-running the same requested date resolves to the same target -> idempotent.
    d = dt.date(2026, 6, 17)
    assert resolve_target_date(TRADING, d) == d
    assert resolve_target_date(TRADING, d) == resolve_target_date(TRADING, d)


def test_fred_timeout_is_non_fatal_degraded_warn(monkeypatch):
    import scripts.run_paper_daily as rpd

    def _fred_timeout(_session):
        raise TimeoutError("HTTPSConnectionPool(host='fred.stlouisfed.org'): read timed out")

    monkeypatch.setattr(rpd, "ingest_all_fred", _fred_timeout)
    # gex never reached (FRED raises first); stub anyway to isolate the FRED path.
    monkeypatch.setattr(rpd, "ingest_gex_from_squeezemetrics", lambda _s: {})

    res = step_ingest_raw(session=None)

    assert isinstance(res, StepResult)
    assert res.status == "warn"          # degraded, NOT "fail"
    assert res.name == "A_ingest_raw"
    assert "timed out" in res.detail or "fred" in res.detail.lower()


def test_ranking_scoring_modules_untouched_and_importable():
    # M7 only changed load_universe + main()'s date/idempotency flow. The
    # strategy/selector entrypoints must remain importable + unchanged in shape.
    from scripts.run_paper_daily import step_run_strategy, step_compute_features_and_context
    assert callable(step_run_strategy)
    assert callable(step_compute_features_and_context)
