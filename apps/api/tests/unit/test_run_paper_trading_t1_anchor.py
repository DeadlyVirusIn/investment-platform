"""Phase 11V - submitted_at anchoring tests for the live paper job.

The cron-fired live run must anchor `submitted_at` to <today>@15:00
UTC so the strict next-bar-fill rule (`bar.ts > submitted_at` with
`bar.ts = trading-day 00:00 UTC`) eventually finds a future bar.

Historical replay convention is unchanged (it already anchored at
15:00 UTC).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.worker.src.jobs import run_paper_trading as job


# ---------------------------------------------------------------------------
# Source-level guards
# ---------------------------------------------------------------------------

def test_source_uses_combine_now_date_15_utc():
    """Source-level invariant: live mode anchors at 15:00 UTC of
    today's date, not run-time."""
    src = Path(job.__file__).read_text(encoding="utf-8")
    assert "dt.time(15, 0)" in src
    assert "datetime.now(dt.timezone.utc).date()" in src
    # Historical replay branch must remain
    assert "dt.datetime.combine(as_of, dt.time(15, 0)" in src


def test_source_does_not_use_now_directly_for_live_submitted_at():
    """The bare `dt.datetime.now(dt.timezone.utc)` (without `.date()`)
    must not be assigned to `now` in the else branch any more."""
    src = Path(job.__file__).read_text(encoding="utf-8")
    # Find the `else:` block following the `if as_of` and verify it
    # does NOT contain `now = dt.datetime.now(dt.timezone.utc)` as a
    # bare assignment (must use `.date()` first).
    flat = src
    bad_pattern = "now = dt.datetime.now(dt.timezone.utc)\n"
    assert bad_pattern not in flat, (
        "live mode must not anchor submitted_at to run-time"
    )


def test_source_does_not_change_fill_condition():
    """Strict next-bar SQL stays at `ts > :after_ts` in the
    paper_execution module."""
    repo_root = Path(__file__).resolve().parents[4]
    exec_src = (
        repo_root / "apps" / "api" / "src" / "domain"
        / "paper_trading" / "paper_execution.py"
    ).read_text(encoding="utf-8")
    assert "PriceBar.ts > after_ts" in exec_src
    # Forbid loosening to >=
    assert "PriceBar.ts >= after_ts" not in exec_src


# ---------------------------------------------------------------------------
# Behavioural assertion — submitted_at anchored at 15:00 UTC
# ---------------------------------------------------------------------------

class _PortfolioStub:
    id = "stub-portfolio"
    is_active = True


class _CapturingSession:
    """Stub session that yields one stub portfolio so the runner
    constructs `submitted_at` and calls `auto_trade_portfolio`. The
    monkeypatched `auto_trade_portfolio` captures `now` for assertion."""

    def __init__(self, captured: list):
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def scalars(self, _stmt):
        class _R:
            def __iter__(self_inner):
                return iter([_PortfolioStub])
        return _R()

    def get(self, _model, _id):
        return _PortfolioStub


def test_live_mode_submitted_at_is_today_15_utc(monkeypatch):
    """Run live; capture the `now` value passed to
    `auto_trade_portfolio`."""
    captured: dict = {}

    def fake_auto_trade(session, portfolio, cfg, *, now=None, as_of=None):
        captured["now"] = now
        captured["as_of"] = as_of

        class _Result:
            decisions: list = []
            executed: list = []
            rejected: list = []
            buy_skips: list = []
        return _Result()

    monkeypatch.setattr(job, "auto_trade_portfolio", fake_auto_trade)
    monkeypatch.setattr(
        job, "SessionLocal", lambda: _CapturingSession(captured),
    )
    monkeypatch.setattr(
        job, "snapshot_equity_now", lambda *a, **kw: None,
    )
    asyncio.run(job.run_paper_trading())

    submitted = captured.get("now")
    assert isinstance(submitted, dt.datetime)
    assert submitted.tzinfo == dt.timezone.utc
    assert submitted.hour == 15
    assert submitted.minute == 0
    assert submitted.second == 0
    today = dt.datetime.now(dt.timezone.utc).date()
    assert submitted.date() == today
    assert captured.get("as_of") is None


def test_historical_replay_branch_unchanged(monkeypatch):
    captured: dict = {}

    def fake_auto_trade(session, portfolio, cfg, *, now=None, as_of=None):
        captured["now"] = now
        captured["as_of"] = as_of

        class _Result:
            decisions: list = []
            executed: list = []
            rejected: list = []
            buy_skips: list = []
        return _Result()

    monkeypatch.setattr(job, "auto_trade_portfolio", fake_auto_trade)
    monkeypatch.setattr(
        job, "SessionLocal", lambda: _CapturingSession(captured),
    )
    monkeypatch.setattr(
        job, "snapshot_equity_now", lambda *a, **kw: None,
    )
    target = dt.date(2026, 2, 25)
    asyncio.run(job.run_paper_trading(as_of=target))

    submitted = captured.get("now")
    assert submitted == dt.datetime.combine(
        target, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )
    assert captured.get("as_of") == target


def test_no_threshold_change_in_paper_trading_module():
    """Sanity: no constant value changed in this module."""
    src = Path(job.__file__).read_text(encoding="utf-8")
    # SKIPS_DIR is the only module-level constant; ensure it's intact.
    assert 'SKIPS_DIR = Path("artifacts/paper_trading_skips")' in src


def test_no_scheduler_change():
    """REGISTRY size and entries unchanged."""
    from apps.worker.src.jobs.registry import REGISTRY
    assert len(REGISTRY) == 13
    assert "run_paper_trading" in REGISTRY


def test_anchor_constants_are_15_00_utc():
    """Sanity: this test would fail if someone bumped the hour."""
    # Direct invariant: the live-mode submitted_at uses time(15, 0).
    src = Path(job.__file__).read_text(encoding="utf-8")
    assert "dt.time(15, 0)" in src


# ---------------------------------------------------------------------------
# T+1 invariant (documentation-style assertion)
# ---------------------------------------------------------------------------

def test_t1_invariant_today_bar_does_not_qualify():
    """Today's bar (`ts = today 00:00 UTC`) must NOT satisfy
    `ts > submitted_at` when submitted_at = today 15:00 UTC."""
    today = dt.date(2026, 4, 29)
    submitted_at = dt.datetime.combine(
        today, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )
    today_bar = dt.datetime.combine(
        today, dt.time(0, 0), tzinfo=dt.timezone.utc,
    )
    assert not (today_bar > submitted_at)


def test_t1_invariant_tomorrow_bar_qualifies():
    """Tomorrow's bar (`ts = tomorrow 00:00 UTC`) MUST satisfy
    `ts > submitted_at` when submitted_at = today 15:00 UTC."""
    today = dt.date(2026, 4, 29)
    submitted_at = dt.datetime.combine(
        today, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )
    tomorrow_bar = dt.datetime.combine(
        today + dt.timedelta(days=1), dt.time(0, 0),
        tzinfo=dt.timezone.utc,
    )
    assert tomorrow_bar > submitted_at
