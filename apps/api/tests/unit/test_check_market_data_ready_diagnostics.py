"""Phase 11W (incident fix) — precheck diagnostics tests."""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock

import pytest

import scripts.check_market_data_ready as mod


class _StubResult:
    def __init__(self, mapping):
        self._mapping = mapping

    def mappings(self):
        return self

    def first(self):
        return self._mapping


class _StubSession:
    def __init__(self, *, stage_dates, price_row, ctx_row):
        self._stage = stage_dates
        self._price = price_row
        self._ctx = ctx_row
        self.calls: list[str] = []

    def execute(self, sql, params=None):
        sql_text = str(sql).lower()
        self.calls.append(sql_text)
        # Diagnostic _stage_max_dates query first.
        if "max(ts)::date" in sql_text and "as price_bar" in sql_text:
            return _StubResult(self._stage)
        if "from price_bar p" in sql_text:
            return _StubResult(self._price)
        if "from context_daily" in sql_text:
            return _StubResult(self._ctx)
        return _StubResult(None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _stub_session_local(session):
    return MagicMock(__enter__=lambda *_: session,
                     __exit__=lambda *_: False)


def test_ready_returns_full_stage_dates(monkeypatch):
    """When all stages have advanced, info dict carries explicit
    per-stage max-dates."""
    s = _StubSession(
        stage_dates={
            "price_bar": dt.date(2026, 5, 1),
            "context_daily": dt.date(2026, 5, 1),
            "regime": dt.date(2026, 5, 1),
            "factor": dt.date(2026, 5, 1),
            "candidate": dt.date(2026, 5, 1),
        },
        price_row={"bar_date": dt.date(2026, 5, 1)},
        ctx_row={"bar_date": dt.date(2026, 5, 1)},
    )
    monkeypatch.setattr(
        mod, "SessionLocal", lambda: _stub_session_local(s),
    )
    ready, info = mod.check_ready(
        instrument="ES",
        as_of=dt.date(2026, 5, 1),
        max_age_days=4,
    )
    assert ready is True
    assert info["latest_price_bar_date"] == "2026-05-01"
    assert info["latest_context_daily_date"] == "2026-05-01"
    assert info["latest_regime_date"] == "2026-05-01"
    assert info["latest_factor_date"] == "2026-05-01"
    assert info["latest_candidate_date"] == "2026-05-01"


def test_stale_macro_context_blocks_ready(monkeypatch):
    """price_bar advanced past context_daily → NOT ready with
    explicit reason='macro_context_stale'."""
    s = _StubSession(
        stage_dates={
            "price_bar": dt.date(2026, 5, 1),
            "context_daily": dt.date(2026, 4, 28),
            "regime": dt.date(2026, 4, 17),
            "factor": dt.date(2026, 4, 17),
            "candidate": dt.date(2026, 4, 17),
        },
        price_row={"bar_date": dt.date(2026, 5, 1)},
        ctx_row={"bar_date": dt.date(2026, 4, 28)},
    )
    monkeypatch.setattr(
        mod, "SessionLocal", lambda: _stub_session_local(s),
    )
    ready, info = mod.check_ready(
        instrument="ES",
        as_of=dt.date(2026, 5, 1),
        max_age_days=4,
    )
    assert ready is False
    assert info["reason"] == "macro_context_stale"
    assert info["context_daily_lag_days"] == 3
    assert info["latest_price_bar_date"] == "2026-05-01"
    assert info["latest_context_daily_date"] == "2026-04-28"


def test_no_price_bar_returns_not_ready(monkeypatch):
    s = _StubSession(
        stage_dates={
            "price_bar": None, "context_daily": None,
            "regime": None, "factor": None, "candidate": None,
        },
        price_row=None,
        ctx_row=None,
    )
    monkeypatch.setattr(
        mod, "SessionLocal", lambda: _stub_session_local(s),
    )
    ready, info = mod.check_ready(
        instrument="ES",
        as_of=dt.date(2026, 5, 1),
        max_age_days=4,
    )
    assert ready is False
    assert info["reason"] == "no_price_bar_found"


def test_too_old_bar_returns_not_ready(monkeypatch):
    s = _StubSession(
        stage_dates={
            "price_bar": dt.date(2026, 4, 1),
            "context_daily": dt.date(2026, 4, 1),
            "regime": None, "factor": None, "candidate": None,
        },
        price_row={"bar_date": dt.date(2026, 4, 1)},
        ctx_row={"bar_date": dt.date(2026, 4, 1)},
    )
    monkeypatch.setattr(
        mod, "SessionLocal", lambda: _stub_session_local(s),
    )
    ready, info = mod.check_ready(
        instrument="ES",
        as_of=dt.date(2026, 5, 1),
        max_age_days=4,
    )
    assert ready is False
    assert info["reason"] == "bar_too_stale"


def test_db_error_returns_error_info(monkeypatch):
    class _BoomSession:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a, **kw):
            raise RuntimeError("simulated db down")

    monkeypatch.setattr(
        mod, "SessionLocal", lambda: _BoomSession(),
    )
    ready, info = mod.check_ready(
        instrument="ES",
        as_of=dt.date(2026, 5, 1),
        max_age_days=4,
    )
    assert ready is False
    assert "error" in info
    assert "simulated db down" in info["error"]
