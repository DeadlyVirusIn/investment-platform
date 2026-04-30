"""Phase 11V - run_turnover_report CLI unit tests."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.run_turnover_report as runner
from scripts.run_turnover_report import (
    NEUTRAL_PLEDGE,
    REPORT_VERSION,
    TurnoverReportError,
    _parse_args,
    explain,
    report_path,
    write_report,
)


# ---------------------------------------------------------------------------
# Frozen constants + pledge
# ---------------------------------------------------------------------------

def test_report_version_frozen():
    assert REPORT_VERSION == "turnover-report-v1.0.0"


def test_pledge_includes_offline_diagnostic_language():
    assert "offline diagnostic" in NEUTRAL_PLEDGE.lower()
    assert "not advice" in NEUTRAL_PLEDGE.lower()


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------

def test_parse_args_defaults_lookback_to_30():
    ns = _parse_args([])
    assert ns.lookback_days == 30
    assert ns.dry_run is False
    assert ns.explain is False


def test_parse_args_parses_iso_date():
    ns = _parse_args(["--as-of-date", "2026-04-29"])
    assert ns.as_of_date == dt.date(2026, 4, 29)


def test_parse_args_dry_run_explain_lookback():
    ns = _parse_args([
        "--as-of-date", "2026-04-29",
        "--lookback-days", "60",
        "--dry-run", "--explain",
    ])
    assert ns.lookback_days == 60
    assert ns.dry_run is True
    assert ns.explain is True


def test_parse_args_rejects_bad_date():
    with pytest.raises(SystemExit):
        _parse_args(["--as-of-date", "2026/04/29"])


# ---------------------------------------------------------------------------
# report_path filename
# ---------------------------------------------------------------------------

def test_report_path_format(tmp_path: Path):
    p = report_path(
        as_of=dt.date(2026, 4, 29), lookback_days=30,
        output_dir=tmp_path,
    )
    assert p.name == "turnover_2026-04-29_30d.json"
    assert p.parent == tmp_path


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------

def _stub_report() -> dict:
    return {
        "report_version": REPORT_VERSION,
        "generated_at": "2026-04-29T15:00:00+00:00",
        "as_of": "2026-04-29T15:00:00+00:00",
        "lookback_days": 30,
        "portfolios": [],
        "next_cycle_prediction": [],
        "data_collection_health": {},
        "neutral_language_pledge": NEUTRAL_PLEDGE,
    }


def test_write_report_creates_output_dir(tmp_path: Path):
    target = tmp_path / "fresh"
    p = write_report(
        _stub_report(),
        as_of=dt.date(2026, 4, 29),
        lookback_days=30,
        output_dir=target,
    )
    assert p.exists()
    assert p.parent == target


def test_write_report_refuses_to_overwrite(tmp_path: Path):
    p = write_report(
        _stub_report(),
        as_of=dt.date(2026, 4, 29), lookback_days=30,
        output_dir=tmp_path,
    )
    assert p.exists()
    with pytest.raises(TurnoverReportError, match="overwrite"):
        write_report(
            _stub_report(),
            as_of=dt.date(2026, 4, 29), lookback_days=30,
            output_dir=tmp_path,
        )


def test_write_report_emits_valid_json(tmp_path: Path):
    p = write_report(
        _stub_report(),
        as_of=dt.date(2026, 4, 29), lookback_days=30,
        output_dir=tmp_path,
    )
    body = json.loads(p.read_text(encoding="utf-8"))
    assert body["report_version"] == REPORT_VERSION
    assert body["lookback_days"] == 30


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------

def test_explain_handles_empty_portfolios():
    rep = _stub_report()
    rep["data_collection_health"] = {
        "price_bar": {
            "fresh_count": 0, "stale_count": 0, "missing_count": 0,
        },
        "context_daily": {
            "all_present": True, "missing_gates": [],
        },
        "recommendations": {"total": 0, "by_action": {}},
        "candidate_ideas": {"total": 0, "days_with_data": 0},
    }
    out = explain(rep)
    assert "no active portfolios" in out


def test_explain_renders_portfolio_summary():
    rep = _stub_report()
    rep["portfolios"] = [{
        "portfolio_id": "pid-1",
        "portfolio_name": "main",
        "open_positions_count": 10,
        "max_open_positions": 10,
        "free_slots": 0,
        "pending_exits_count": 4,
        "expected_slots_after_next_run": 4,
        "blocked_buys_reason": "portfolio_full",
        "pending_exits": [],
        "lookback_window": {
            "buys_count": 5, "sells_count": 7,
            "turnover_ratio": 0.5,
            "realized_pnl_total": "100",
        },
    }]
    rep["data_collection_health"] = {
        "price_bar": {
            "fresh_count": 10, "stale_count": 0, "missing_count": 0,
        },
        "context_daily": {
            "all_present": True, "missing_gates": [],
        },
        "recommendations": {"total": 5, "by_action": {"Buy": 5}},
        "candidate_ideas": {"total": 5, "days_with_data": 5},
    }
    out = explain(rep)
    assert "main" in out
    assert "pending_exits=4" in out
    assert "blocked_buys: portfolio_full" in out


# ---------------------------------------------------------------------------
# Source-level guards
# ---------------------------------------------------------------------------

def test_runner_has_no_db_writes():
    src = Path(runner.__file__).read_text(encoding="utf-8")
    for tok in (
        "INSERT INTO", "UPDATE ", "DELETE FROM",
        "session.commit", "session.add(",
    ):
        assert tok not in src, f"forbidden token {tok!r}"


def test_runner_does_not_import_execution_paths():
    src = Path(runner.__file__).read_text(encoding="utf-8")
    for tok in (
        "submit_trade", "auto_trade_portfolio",
        "live_", "broker_", "order_router",
    ):
        assert tok not in src, f"forbidden import {tok!r}"


def test_runner_writes_only_under_reports_dir_by_default():
    src = Path(runner.__file__).read_text(encoding="utf-8")
    assert 'REPORTS_DIR = Path("reports")' in src
