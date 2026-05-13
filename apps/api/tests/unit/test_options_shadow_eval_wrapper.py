"""Phase Opt-B3a Step 4 — wrapper unit tests.

Mocks `apps.api.src.options.shadow_evaluator.evaluate` so tests run
offline. Covers:

  * _resolve_persist matrix
  * run_dry_manual ALWAYS passes persist=False, regardless of flags
  * scheduler entry point skips immediately when OPTIONS_ENABLED=False
  * scheduler entry point invokes evaluate with persist resolved
    from BOTH flags
  * summary dict shape contains required keys
"""

from __future__ import annotations

import asyncio
import datetime as dt
import types
from unittest.mock import patch


def _fake_summary(run_date: dt.date):
    """Build a minimal Summary-like object that evaluator returns."""
    return types.SimpleNamespace(
        run_date=run_date,
        underlying_count=5,
        contracts_evaluated=123,
        would_trade_count=4,
        blocked_reason_counts={"liquidity": 50, "spread": 30},
        freshness_warnings=["stale_chain_SPY"],
        inserted=0,
    )


def _fake_evaluate_factory(captured: dict):
    """Returns an `evaluate(...)` stub that captures kwargs into the
    provided dict so the test can assert on them."""

    def _evaluate(session, *, run_date, underlyings=None, persist=False):
        captured.update({
            "run_date":    run_date,
            "underlyings": underlyings,
            "persist":     persist,
        })
        return _fake_summary(run_date), []

    return _evaluate


# ---------------------------------------------------------------------------
# _resolve_persist
# ---------------------------------------------------------------------------

def test_resolve_persist_both_false_returns_false():
    from apps.worker.src.jobs.options_shadow_eval import _resolve_persist
    with patch("apps.worker.src.jobs.options_shadow_eval.settings",
               types.SimpleNamespace(
                   OPTIONS_ENABLED=False,
                   OPTIONS_SHADOW_EVAL_ENABLED=False,
               )):
        assert _resolve_persist() is False


def test_resolve_persist_master_only_returns_false():
    from apps.worker.src.jobs.options_shadow_eval import _resolve_persist
    with patch("apps.worker.src.jobs.options_shadow_eval.settings",
               types.SimpleNamespace(
                   OPTIONS_ENABLED=True,
                   OPTIONS_SHADOW_EVAL_ENABLED=False,
               )):
        assert _resolve_persist() is False


def test_resolve_persist_shadow_only_returns_false():
    """Shadow flag alone is insufficient — master gate dominates."""
    from apps.worker.src.jobs.options_shadow_eval import _resolve_persist
    with patch("apps.worker.src.jobs.options_shadow_eval.settings",
               types.SimpleNamespace(
                   OPTIONS_ENABLED=False,
                   OPTIONS_SHADOW_EVAL_ENABLED=True,
               )):
        assert _resolve_persist() is False


def test_resolve_persist_both_true_returns_true():
    from apps.worker.src.jobs.options_shadow_eval import _resolve_persist
    with patch("apps.worker.src.jobs.options_shadow_eval.settings",
               types.SimpleNamespace(
                   OPTIONS_ENABLED=True,
                   OPTIONS_SHADOW_EVAL_ENABLED=True,
               )):
        assert _resolve_persist() is True


# ---------------------------------------------------------------------------
# run_dry_manual — always persist=False
# ---------------------------------------------------------------------------

def test_run_dry_manual_forces_persist_false_even_when_flags_on():
    """Even with both flags True, run_dry_manual must call evaluate
    with persist=False."""
    captured: dict = {}
    fake_evaluate = _fake_evaluate_factory(captured)

    with patch("apps.worker.src.jobs.options_shadow_eval.settings",
               types.SimpleNamespace(
                   OPTIONS_ENABLED=True,
                   OPTIONS_SHADOW_EVAL_ENABLED=True,
                   OPTIONS_DATA_PROVIDER="tradier",
               )), patch(
                   "apps.worker.src.jobs.options_shadow_eval.evaluate",
                   fake_evaluate):
        from apps.worker.src.jobs.options_shadow_eval import run_dry_manual
        out = run_dry_manual(run_date=dt.date(2026, 5, 4))

    assert captured["persist"] is False, captured
    assert captured["run_date"] == dt.date(2026, 5, 4)
    assert out["persist"] is False
    assert out["contracts_evaluated"] == 123
    assert out["would_trade_count"] == 4
    assert out["inserted"] == 0
    assert out["options_data_provider"] == "tradier"
    # required summary keys
    for key in ("run_date", "underlying_count", "contracts_evaluated",
                "would_trade_count", "blocked_reason_counts",
                "freshness_warnings", "inserted", "persist",
                "options_enabled", "options_shadow_eval_enabled",
                "options_data_provider", "elapsed_ms"):
        assert key in out, f"missing key: {key}"


def test_run_dry_manual_respects_underlyings_arg():
    captured: dict = {}
    with patch("apps.worker.src.jobs.options_shadow_eval.settings",
               types.SimpleNamespace(
                   OPTIONS_ENABLED=False,
                   OPTIONS_SHADOW_EVAL_ENABLED=False,
                   OPTIONS_DATA_PROVIDER="tradier",
               )), patch(
                   "apps.worker.src.jobs.options_shadow_eval.evaluate",
                   _fake_evaluate_factory(captured)):
        from apps.worker.src.jobs.options_shadow_eval import run_dry_manual
        run_dry_manual(run_date=dt.date(2026, 5, 4),
                       underlyings=["SPY", "QQQ"])
    assert captured["underlyings"] == ["SPY", "QQQ"]


# ---------------------------------------------------------------------------
# Scheduler entry point
# ---------------------------------------------------------------------------

def test_scheduler_entry_skips_when_options_enabled_false():
    """When OPTIONS_ENABLED=False, evaluate must NEVER be invoked."""
    captured: dict = {}

    def _should_not_be_called(*a, **kw):
        captured["CALLED"] = True
        return _fake_summary(dt.date.today()), []

    with patch("apps.worker.src.jobs.options_shadow_eval.settings",
               types.SimpleNamespace(
                   OPTIONS_ENABLED=False,
                   OPTIONS_SHADOW_EVAL_ENABLED=False,
                   OPTIONS_DATA_PROVIDER="tradier",
               )), patch(
                   "apps.worker.src.jobs.options_shadow_eval.evaluate",
                   _should_not_be_called):
        from apps.worker.src.jobs.options_shadow_eval import (
            run_options_shadow_eval_job)
        asyncio.run(run_options_shadow_eval_job())

    assert "CALLED" not in captured, "evaluate must NOT run when master flag is off"


def test_scheduler_entry_runs_dry_when_only_master_flag_on():
    captured: dict = {}
    with patch("apps.worker.src.jobs.options_shadow_eval.settings",
               types.SimpleNamespace(
                   OPTIONS_ENABLED=True,
                   OPTIONS_SHADOW_EVAL_ENABLED=False,
                   OPTIONS_DATA_PROVIDER="tradier",
               )), patch(
                   "apps.worker.src.jobs.options_shadow_eval.evaluate",
                   _fake_evaluate_factory(captured)):
        from apps.worker.src.jobs.options_shadow_eval import (
            run_options_shadow_eval_job)
        asyncio.run(run_options_shadow_eval_job())

    assert captured["persist"] is False


def test_scheduler_entry_runs_persisted_when_both_flags_on():
    captured: dict = {}
    with patch("apps.worker.src.jobs.options_shadow_eval.settings",
               types.SimpleNamespace(
                   OPTIONS_ENABLED=True,
                   OPTIONS_SHADOW_EVAL_ENABLED=True,
                   OPTIONS_DATA_PROVIDER="tradier",
               )), patch(
                   "apps.worker.src.jobs.options_shadow_eval.evaluate",
                   _fake_evaluate_factory(captured)):
        from apps.worker.src.jobs.options_shadow_eval import (
            run_options_shadow_eval_job)
        asyncio.run(run_options_shadow_eval_job())

    assert captured["persist"] is True


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------

def test_registry_contains_options_shadow_eval():
    from apps.worker.src.jobs.registry import REGISTRY
    assert "options_shadow_eval" in REGISTRY
    # Same callable as wrapper module export
    from apps.worker.src.jobs.options_shadow_eval import (
        run_options_shadow_eval_job)
    assert REGISTRY["options_shadow_eval"] is run_options_shadow_eval_job
