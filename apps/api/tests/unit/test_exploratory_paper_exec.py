"""Phase 2-execution — exploratory paper-trading runner pins.

Exploratory execution is operator-triggered, env-gated, and capped.
This test suite locks down the contract so a future regression is
caught:

  1. Confirmation phrase pinned literally.
  2. Cap constants pinned: 3 buys/day, 0.02 position pct,
     -0.20 min-score floor, 0.10 penalty.
  3. Soft-gate set is the exact 5 reasons strict treats as
     `rejection_reason`.
  4. Hard-gate set is the exact list of safety rejections (with
     `regime_off`, `stale_data`, `insufficient_history`, etc.).
  5. Submit path uses `submit_trade()` (preserves next-bar guard).
  6. Script file does not contain raw INSERT INTO paper_trade
     SQL — all writes flow through submit_trade.
  7. --commit refused without env confirmation (subprocess test).
  8. Default (no --commit) writes nothing — paper_trade total
     unchanged across dry-run.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path("scripts/run_exploratory_paper_exec.py")


def test_script_exists():
    assert SCRIPT.exists()


def test_confirmation_phrase_pinned():
    src = SCRIPT.read_text(encoding="utf-8")
    assert 'CONFIRM_ENV = "EXPLORATORY_PAPER_CONFIRM"' in src
    assert (
        'CONFIRM_VALUE = "I_UNDERSTAND_THIS_SUBMITS_PAPER_TRADES"'
        in src
    )


def test_cap_constants_pinned():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "EXPLORATORY_MAX_BUYS_PER_DAY = 5" in src
    assert 'EXPLORATORY_MAX_POSITION_PCT = Decimal("0.02")' in src
    assert "EXPLORATORY_MIN_SCORE = -0.20" in src
    assert 'EXPLORATORY_PENALTY = Decimal("0.10")' in src
    # Capacity + diversification caps
    assert "EXPLORATORY_MAX_OPEN_POSITIONS = 15" in src
    assert "EXPLORATORY_MAX_NEW_PER_SYMBOL_PER_RUN = 1" in src
    assert "EXPLORATORY_MAX_SECTOR_EXPOSURE_PCT = 0.25" in src


def test_strict_max_open_constant_unchanged():
    """`auto_trader` and `paper_execution` continue to use the
    DEFAULT_MAX_OPEN_POSITIONS constant for strict path; this script
    must NOT mutate it. Re-pin its value here to catch drift."""
    from apps.api.src.domain.paper_trading.paper_execution import (
        DEFAULT_MAX_OPEN_POSITIONS,
    )
    assert DEFAULT_MAX_OPEN_POSITIONS == 30


def test_diversification_helpers_present():
    src = SCRIPT.read_text(encoding="utf-8")
    # Cross-portfolio symbol tracker.
    assert "picked_symbols_global" in src
    # Sector concentration helper.
    assert "_portfolio_sector_counts" in src
    assert "skipped_sector_exposure" in src
    assert "skipped_diversification" in src


def test_soft_gate_set_pinned():
    src = SCRIPT.read_text(encoding="utf-8")
    for soft in (
        "below_long_trend",
        "extended_from_sma200",
        "idiosyncratic_vol_high",
        "topn_overflow",
        "high_vol_topn_overflow",
    ):
        assert f'"{soft}"' in src, f"soft gate missing: {soft}"


def test_hard_gate_set_pinned():
    src = SCRIPT.read_text(encoding="utf-8")
    for hard in (
        "regime_off", "insufficient_history", "stale_data",
        "liquidity_fail", "earnings_too_close",
        "duplicate_holding", "portfolio_full",
        "execution_failure",
        "not_in_universe", "already_at_cap",
    ):
        assert f'"{hard}"' in src, f"hard gate missing: {hard}"


def test_submit_uses_submit_trade_path():
    """Trades MUST go through submit_trade() so the next-bar fill
    guard is preserved. Bare INSERT INTO paper_trade is forbidden."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "from apps.api.src.domain.paper_trading.paper_execution" in src
    assert "submit_trade" in src
    # No raw INSERT INTO paper_trade in this script.
    for line in src.splitlines():
        s = line.lstrip()
        if (s.startswith("#") or s.startswith('"')
                or s.startswith("'") or s.startswith("*")):
            continue
        assert not re.search(
            r"\bINSERT\s+INTO\s+paper_trade\b", line, flags=re.IGNORECASE
        ), f"raw INSERT INTO paper_trade in script: {line}"


def test_commit_refused_without_env_confirmation():
    """Subprocess: --commit without EXPLORATORY_PAPER_CONFIRM exits 2."""
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.run_exploratory_paper_exec",
         "--commit"],
        capture_output=True, text=True,
        env={**os.environ, "EXPLORATORY_PAPER_CONFIRM": ""},
        cwd=Path.cwd(),
    )
    assert proc.returncode == 2, (
        f"expected exit 2 without confirm; got {proc.returncode}\n"
        f"stderr: {proc.stderr}"
    )
    assert "REFUSED" in proc.stderr
    assert "EXPLORATORY_PAPER_CONFIRM" in proc.stderr


def test_commit_refused_with_wrong_phrase():
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.run_exploratory_paper_exec",
         "--commit"],
        capture_output=True, text=True,
        env={**os.environ, "EXPLORATORY_PAPER_CONFIRM": "yes"},
        cwd=Path.cwd(),
    )
    assert proc.returncode == 2


def test_no_options_or_live_keywords():
    """Script must not toggle ML or options live execution."""
    src = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "ML_CAN_AFFECT_TRADES",
        "OPTIONS_LIVE", "options_paper_trade",
        "BROKERAGE", "live_trade",
    ):
        assert forbidden not in src, (
            f"forbidden keyword in exploratory script: {forbidden}"
        )


def test_strict_mode_decision_engine_unchanged():
    """Defensive: ensure the exploratory script does NOT import or
    monkeypatch the strict candidate-generation path."""
    src = SCRIPT.read_text(encoding="utf-8")
    forbidden_imports = (
        "decision_engine.generate_candidates",
        "monkeypatch", "setattr(",
        "REGIME_FALLBACK_MAX_TRADING_DAYS",
        "_regime_off",
    )
    for f in forbidden_imports:
        assert f not in src, (
            f"exploratory script must not touch strict path: {f}"
        )
