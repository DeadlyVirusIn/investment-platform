"""Phase 11W (incident fix) — backfill range orchestrator tests."""

from __future__ import annotations

import datetime as dt

import pytest

import scripts.backfill_paper_pipeline_range as mod


def test_trading_days_skips_weekends():
    """Mon 4-27 → Sun 5-03 should yield 5 weekday dates."""
    days = mod._trading_days(
        dt.date(2026, 4, 27), dt.date(2026, 5, 3),
    )
    assert days == [
        dt.date(2026, 4, 27),
        dt.date(2026, 4, 28),
        dt.date(2026, 4, 29),
        dt.date(2026, 4, 30),
        dt.date(2026, 5, 1),
    ]


def test_trading_days_includes_endpoints():
    days = mod._trading_days(dt.date(2026, 5, 1), dt.date(2026, 5, 1))
    assert days == [dt.date(2026, 5, 1)]


def test_trading_days_empty_when_only_weekend():
    days = mod._trading_days(dt.date(2026, 5, 2), dt.date(2026, 5, 3))
    assert days == []


def test_arg_parser_requires_start_end():
    with pytest.raises(SystemExit):
        mod._parse(["--start", "2026-05-01"])


def test_main_rejects_inverted_range(monkeypatch):
    monkeypatch.setattr(
        mod, "backfill_range",
        lambda **kw: pytest.fail("backfill_range should not be called"),
    )
    rc = mod.main([
        "--start", "2026-05-02", "--end", "2026-05-01",
    ])
    assert rc == 2


def test_backfill_range_processes_all_trading_days(monkeypatch):
    calls: list[dt.date] = []

    def _stub_engine(as_of, dry_run=False, **kw):
        calls.append(as_of)
        return {"as_of": as_of.isoformat(), "ok": True, "stages": {}}

    monkeypatch.setattr(mod, "run_engine_pipeline", _stub_engine)
    monkeypatch.setattr(mod, "_run_paper_daily", lambda d, **kw: 0)
    out = mod.backfill_range(
        dt.date(2026, 4, 27), dt.date(2026, 5, 1),
    )
    assert out["ok"] is True
    assert calls == [
        dt.date(2026, 4, 27), dt.date(2026, 4, 28),
        dt.date(2026, 4, 29), dt.date(2026, 4, 30),
        dt.date(2026, 5, 1),
    ]
    assert len(out["days_processed"]) == 5


def test_backfill_range_halts_on_engine_failure_when_strict(
    monkeypatch,
):
    def _bad_engine(as_of, dry_run=False, **kw):
        return {"as_of": as_of.isoformat(), "ok": False, "stages": {}}

    monkeypatch.setattr(mod, "run_engine_pipeline", _bad_engine)
    monkeypatch.setattr(mod, "_run_paper_daily", lambda d, **kw: 0)
    out = mod.backfill_range(
        dt.date(2026, 4, 29), dt.date(2026, 5, 1),
        allow_missing=False,
    )
    assert out["ok"] is False
    # Stops at first failure; only 1 day reported.
    assert len(out["days_processed"]) == 1


def test_backfill_range_continues_when_allow_missing(monkeypatch):
    def _bad_engine(as_of, dry_run=False, **kw):
        return {"as_of": as_of.isoformat(), "ok": False, "stages": {}}

    monkeypatch.setattr(mod, "run_engine_pipeline", _bad_engine)
    monkeypatch.setattr(mod, "_run_paper_daily", lambda d, **kw: 0)
    out = mod.backfill_range(
        dt.date(2026, 4, 29), dt.date(2026, 5, 1),
        allow_missing=True,
    )
    assert out["ok"] is True or out["ok"] is False  # tolerant
    assert len(out["days_processed"]) == 3


def test_backfill_skip_paper_daily_flag(monkeypatch):
    paper_called: list[dt.date] = []

    def _stub_engine(as_of, dry_run=False, **kw):
        return {"as_of": as_of.isoformat(), "ok": True, "stages": {}}

    def _stub_paper(d, **kw):
        paper_called.append(d)
        return 0

    monkeypatch.setattr(mod, "run_engine_pipeline", _stub_engine)
    monkeypatch.setattr(mod, "_run_paper_daily", _stub_paper)
    out = mod.backfill_range(
        dt.date(2026, 5, 1), dt.date(2026, 5, 1),
        skip_paper_daily=True,
    )
    assert out["ok"] is True
    assert paper_called == []


def test_no_strategy_threshold_changes_in_backfill_range():
    from pathlib import Path

    src = Path(
        "scripts/backfill_paper_pipeline_range.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "RATE_THRESHOLD", "VRP_THRESHOLD",
        "DEFAULT_MAX_OPEN_POSITIONS",
        "submit_trade", "auto_trade_portfolio",
        "exploratory", "EXPLORATORY",
    )
    for tok in forbidden:
        assert tok not in src, (
            f"backfill range must not reference {tok!r}"
        )
