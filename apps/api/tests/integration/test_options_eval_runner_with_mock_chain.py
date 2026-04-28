"""Phase 11O.1 - Full runner pipeline using --mock-chain-from path.

Confirms a mock JSON file -> options_chain_snapshot rows -> qualified
observations -> dry-run renders / commit opens trades when explicitly
allowed.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.config import settings
from apps.api.src.db.options_models import (  # noqa: F401 — register on Base
    OptionsAssignmentEvent,
    OptionsExpirationEvent,
    OptionsPaperTrade,
    OptionsPaperTradeLeg,
    OptionsTradeLifecycleEvent,
)
from scripts import run_options_paper_eval as cli


pytestmark = pytest.mark.integration


def _today() -> datetime.date:
    return datetime.date(2026, 4, 27)


def _expiry() -> datetime.date:
    return _today() + datetime.timedelta(days=30)


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )


@pytest.fixture
def options_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OPTIONS_ENABLED", True)
    monkeypatch.setattr(settings, "OPTIONS_PAPER_ONLY", True)
    monkeypatch.setattr(settings, "OPTIONS_ML_CAN_AFFECT_TRADES", False)


def _write_mock_payload(tmp_path: Path) -> Path:
    expiry = _expiry().isoformat()
    payload = {
        "snapshot_at_utc": (
            f"{_today().isoformat()}T14:00:00Z"
        ),
        "rows": [
            {
                "underlying": "SPY", "expiry": expiry, "strike": 440,
                "option_type": "PUT",
                "option_symbol": "SPY260527P00440000",
                "bid": 1.20, "ask": 1.25, "mid": 1.225, "last": 1.20,
                "volume": 100, "open_interest": 1000,
                "delta": -0.30, "gamma": 0.02, "theta": -0.05,
                "vega": 0.10, "iv": 0.20, "quote_age_seconds": 2,
            },
            {
                "underlying": "SPY", "expiry": expiry, "strike": 435,
                "option_type": "PUT",
                "option_symbol": "SPY260527P00435000",
                "bid": 0.55, "ask": 0.60, "mid": 0.575, "last": 0.55,
                "volume": 80, "open_interest": 1000,
                "delta": -0.18, "gamma": 0.018, "theta": -0.04,
                "vega": 0.09, "iv": 0.21, "quote_age_seconds": 2,
            },
            {
                "underlying": "SPY", "expiry": expiry, "strike": 430,
                "option_type": "PUT",
                "option_symbol": "SPY260527P00430000",
                "bid": 0.30, "ask": 0.35, "mid": 0.325, "last": 0.30,
                "volume": 50, "open_interest": 1000,
                "delta": -0.12, "gamma": 0.014, "theta": -0.03,
                "vega": 0.08, "iv": 0.22, "quote_age_seconds": 3,
            },
            {
                "underlying": "SPY", "expiry": expiry, "strike": 450,
                "option_type": "PUT",
                "option_symbol": "SPY260527P00450000",
                "bid": 4.10, "ask": 4.15, "mid": 4.125, "last": 4.10,
                "volume": 120, "open_interest": 1500,
                "delta": -0.55, "gamma": 0.024, "theta": -0.06,
                "vega": 0.11, "iv": 0.19, "quote_age_seconds": 2,
            },
        ],
    }
    path = tmp_path / "mock.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _patch_session_local(monkeypatch, session_factory):
    """Redirect both the CLI's mock seeder and the runner orchestrator
    to the integration session factory."""
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    from apps.api.src.options.paper import eval_runner
    monkeypatch.setattr(eval_runner, "SessionLocal", session_factory)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_runner_with_mock_chain_produces_qualified_observation(
    pg_session, session_factory, options_enabled, monkeypatch,
    tmp_path, capsys,
):
    _patch_session_local(monkeypatch, session_factory)
    mock_path = _write_mock_payload(tmp_path)
    rc = cli.main([
        "--date", _today().isoformat(),
        "--underlyings", "SPY",
        "--mock-chain-from", str(mock_path),
        "--dry-run",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[mock] inserted" in out
    assert "qualified=" in out
    n_rows = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_chain_snapshot "
        "WHERE provider = 'mock_local'"
    )).scalar_one()
    assert n_rows == 4


def test_runner_with_mock_chain_dry_run_writes_no_paper_trades(
    pg_session, session_factory, options_enabled, monkeypatch,
    tmp_path, capsys,
):
    _patch_session_local(monkeypatch, session_factory)
    mock_path = _write_mock_payload(tmp_path)
    rc = cli.main([
        "--date", _today().isoformat(),
        "--underlyings", "SPY",
        "--mock-chain-from", str(mock_path),
        "--dry-run",
    ])
    assert rc == 0
    n_trades = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_paper_trade"
    )).scalar_one()
    assert n_trades == 0


def test_runner_with_mock_chain_commit_with_allow_mock_commit_writes_trades(
    pg_session, session_factory, options_enabled, monkeypatch,
    tmp_path, capsys,
):
    _patch_session_local(monkeypatch, session_factory)
    mock_path = _write_mock_payload(tmp_path)
    # Redirect audit log so it does not pollute the working tree
    from apps.api.src.options.paper import eval_runner
    monkeypatch.setattr(eval_runner, "JSONL_LOG_DIR", tmp_path)
    rc = cli.main([
        "--date", _today().isoformat(),
        "--underlyings", "SPY",
        "--mock-chain-from", str(mock_path),
        "--commit", "--confirm-commit", "YES",
        "--allow-mock-commit", "--max-open", "3",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "COMMIT" in out
    n_trades = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_paper_trade WHERE paper_only = TRUE"
    )).scalar_one()
    assert n_trades >= 1
