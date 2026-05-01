"""Phase 11X — safe_gate_evolution_shadow evaluator unit tests.

Pure-fn tests with stubbed session. Covers eligibility logic,
hard-cap behavior (favorable=0, production-trade-opened, max-1).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.api.src.data.strategy import safe_gate_evolution_shadow as mod


# ---------------------------------------------------------------------------
# Helper: build a stub session keyed by SQL substring → mapping result
# ---------------------------------------------------------------------------


class _Mappings:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _Mappings(self._rows)

    def scalar_one(self):
        return self._rows[0] if self._rows else 0


class _StubSession:
    def __init__(self, plan: dict[str, list]):
        self._plan = plan
        self.commits = 0

    def execute(self, sql, params=None):
        text = str(sql)
        for needle, payload in self._plan.items():
            if needle in text:
                if isinstance(payload, list):
                    return _Result(payload)
                # for scalar paths the value is wrapped in a list of one
                return _Result([payload])
        return _Result([])

    def commit(self):
        self.commits += 1


def _gates_rows(true_set: set[str]):
    return [
        {"context_name": n, "value_bool": (n in true_set)}
        for n in mod.PRODUCTION_GATE_NAMES
    ]


# ---------------------------------------------------------------------------
# Hard cap 1: favorable=0
# ---------------------------------------------------------------------------


def test_zero_favorable_records_summary_only():
    s = _StubSession({
        "FROM context_daily": _gates_rows(set()),
        "FROM regime_snapshot": [{
            "benchmark_symbol": "SPY", "market_trend": "uptrend",
            "vol_regime": "low", "sma50_over_sma200": True,
            "realized_vol_20d": Decimal("0.09"), "atr_pctile_1y": Decimal("0.20"),
        }],
        "FROM decision_log": [{"reason": "stress=True ..."}],
    })
    out = mod.evaluate(s, dt.date(2026, 4, 29))
    assert out.would_trade is False
    assert out.symbol is None
    assert out.macro_favorable_count == 0
    assert sorted(out.failed_macro_gates) == sorted(
        list(mod.PRODUCTION_GATE_NAMES)
    )
    assert out.shadow_reason == "macro_favorable_count_zero"


# ---------------------------------------------------------------------------
# Hard cap 2: production trade already opened
# ---------------------------------------------------------------------------


def test_production_trade_opened_records_summary_only():
    s = _StubSession({
        "FROM context_daily": _gates_rows({"rates_calm", "credit_stable"}),
        "FROM regime_snapshot": [{
            "benchmark_symbol": "SPY", "market_trend": "uptrend",
            "vol_regime": "low", "sma50_over_sma200": True,
            "realized_vol_20d": Decimal("0.09"),
            "atr_pctile_1y": Decimal("0.20"),
        }],
        "FROM paper_trade_log": [3],
        "FROM paper_trade": [0],
        "FROM decision_log": [{"reason": "production fired"}],
    })
    out = mod.evaluate(s, dt.date(2026, 4, 29))
    assert out.would_trade is False
    assert out.shadow_reason == "production_trade_opened"


# ---------------------------------------------------------------------------
# Spec rule: at least one of rates_calm or credit_stable must be True
# ---------------------------------------------------------------------------


def test_neither_rates_nor_credit_records_summary_only():
    # 2 favorable but neither is rates_calm or credit_stable.
    s = _StubSession({
        "FROM context_daily": _gates_rows({
            "vrp_supportive", "liquidity_expanding",
        }),
        "FROM regime_snapshot": [{
            "benchmark_symbol": "SPY", "market_trend": "uptrend",
            "vol_regime": "low", "sma50_over_sma200": True,
            "realized_vol_20d": Decimal("0.09"),
            "atr_pctile_1y": Decimal("0.20"),
        }],
        "FROM paper_trade_log": [0],
        "FROM paper_trade": [0],
        "FROM decision_log": [{"reason": "..."}],
    })
    out = mod.evaluate(s, dt.date(2026, 4, 29))
    assert out.would_trade is False
    assert out.shadow_reason == "neither_rates_calm_nor_credit_stable"


# ---------------------------------------------------------------------------
# Price regime checks
# ---------------------------------------------------------------------------


def test_unfavorable_trend_blocks_eligibility():
    s = _StubSession({
        "FROM context_daily": _gates_rows({"rates_calm"}),
        "FROM regime_snapshot": [{
            "benchmark_symbol": "SPY", "market_trend": "downtrend",
            "vol_regime": "low", "sma50_over_sma200": True,
            "realized_vol_20d": Decimal("0.09"),
            "atr_pctile_1y": Decimal("0.20"),
        }],
        "FROM paper_trade_log": [0],
        "FROM paper_trade": [0],
        "FROM decision_log": [{"reason": "..."}],
    })
    out = mod.evaluate(s, dt.date(2026, 4, 29))
    assert out.would_trade is False
    assert out.shadow_reason == "price_regime_unfavorable"


def test_unfavorable_vol_regime_blocks():
    s = _StubSession({
        "FROM context_daily": _gates_rows({"credit_stable"}),
        "FROM regime_snapshot": [{
            "benchmark_symbol": "SPY", "market_trend": "uptrend",
            "vol_regime": "elevated", "sma50_over_sma200": True,
            "realized_vol_20d": Decimal("0.20"),
            "atr_pctile_1y": Decimal("0.40"),
        }],
        "FROM paper_trade_log": [0],
        "FROM paper_trade": [0],
        "FROM decision_log": [{"reason": "..."}],
    })
    out = mod.evaluate(s, dt.date(2026, 4, 29))
    assert out.would_trade is False
    assert out.shadow_reason == "price_regime_unfavorable"


def test_sma50_below_sma200_blocks():
    s = _StubSession({
        "FROM context_daily": _gates_rows({"credit_stable"}),
        "FROM regime_snapshot": [{
            "benchmark_symbol": "SPY", "market_trend": "uptrend",
            "vol_regime": "low", "sma50_over_sma200": False,
            "realized_vol_20d": Decimal("0.09"),
            "atr_pctile_1y": Decimal("0.20"),
        }],
        "FROM paper_trade_log": [0],
        "FROM paper_trade": [0],
        "FROM decision_log": [{"reason": "..."}],
    })
    out = mod.evaluate(s, dt.date(2026, 4, 29))
    assert out.would_trade is False
    assert out.shadow_reason == "price_regime_unfavorable"


# ---------------------------------------------------------------------------
# Happy path — eligible top-decile buy above median confidence
# ---------------------------------------------------------------------------


def _accepted_buys(rows):
    """Build mapping rows shaped like the SELECT in
    `_read_top_decile_buy_above_median`."""
    return [
        {
            "id": f"id-{i}", "symbol": s, "composite_score": Decimal(str(sc)),
            "confidence": Decimal(str(c)),
        }
        for i, (s, sc, c) in enumerate(rows)
    ]


def test_happy_path_eligible_top_decile_buy():
    # 10 accepted buys (so top decile = 1). Top buy has score 0.6
    # confidence 80; median confidence = (60+62)/2 = 61.
    rows = [
        ("UNH", 0.60, 80),
        ("QQQ", 0.50, 70),
        ("AMZN", 0.45, 68),
        ("XLK", 0.40, 65),
        ("SPY", 0.38, 62),
        ("NVDA", 0.36, 60),
        ("AVGO", 0.32, 55),
        ("MS", 0.30, 50),
        ("NEE", 0.28, 48),
        ("KO", 0.27, 45),
    ]
    s = _StubSession({
        "FROM context_daily": _gates_rows({"rates_calm"}),
        "FROM regime_snapshot": [{
            "benchmark_symbol": "SPY", "market_trend": "uptrend",
            "vol_regime": "low", "sma50_over_sma200": True,
            "realized_vol_20d": Decimal("0.09"),
            "atr_pctile_1y": Decimal("0.20"),
        }],
        "FROM paper_trade_log": [0],
        "FROM paper_trade": [0],
        "FROM decision_log": [{"reason": "stress=True ..."}],
        "FROM candidate_idea c JOIN asset a": _accepted_buys(rows),
    })
    out = mod.evaluate(s, dt.date(2026, 4, 29))
    assert out.would_trade is True
    assert out.symbol == "UNH"
    assert out.side == "Buy"
    assert out.composite_score == Decimal("0.60")
    assert out.confidence == Decimal("80")
    assert out.macro_favorable_count == 1
    assert out.shadow_reason == (
        "eligible_top_decile_buy_above_median_confidence"
    )
    assert out.hypothetical_size_multiplier == Decimal("0.25")


def test_top_decile_below_median_confidence_blocks():
    # Top buy has score 0.6 but conf 30 (below median); fall through.
    rows = [
        ("UNH", 0.60, 30),
        ("QQQ", 0.50, 70),
        ("AMZN", 0.45, 68),
        ("XLK", 0.40, 65),
        ("SPY", 0.38, 62),
        ("NVDA", 0.36, 60),
    ]
    s = _StubSession({
        "FROM context_daily": _gates_rows({"rates_calm"}),
        "FROM regime_snapshot": [{
            "benchmark_symbol": "SPY", "market_trend": "uptrend",
            "vol_regime": "low", "sma50_over_sma200": True,
            "realized_vol_20d": Decimal("0.09"),
            "atr_pctile_1y": Decimal("0.20"),
        }],
        "FROM paper_trade_log": [0],
        "FROM paper_trade": [0],
        "FROM decision_log": [{"reason": "..."}],
        "FROM candidate_idea c JOIN asset a": _accepted_buys(rows),
    })
    out = mod.evaluate(s, dt.date(2026, 4, 29))
    assert out.would_trade is False
    assert out.shadow_reason.startswith("no_eligible_buy")


def test_no_accepted_buys_records_summary():
    s = _StubSession({
        "FROM context_daily": _gates_rows({"rates_calm"}),
        "FROM regime_snapshot": [{
            "benchmark_symbol": "SPY", "market_trend": "uptrend",
            "vol_regime": "low", "sma50_over_sma200": True,
            "realized_vol_20d": Decimal("0.09"),
            "atr_pctile_1y": Decimal("0.20"),
        }],
        "FROM paper_trade_log": [0],
        "FROM paper_trade": [0],
        "FROM decision_log": [{"reason": "..."}],
        "FROM candidate_idea c JOIN asset a": [],
    })
    out = mod.evaluate(s, dt.date(2026, 4, 29))
    assert out.would_trade is False
    assert "no_accepted_buys" in out.shadow_reason


# ---------------------------------------------------------------------------
# Frozen invariants
# ---------------------------------------------------------------------------


def test_hypothetical_size_multiplier_frozen():
    assert mod.HYPOTHETICAL_SIZE_MULTIPLIER == Decimal("0.25")


def test_production_gate_names_frozen():
    assert mod.PRODUCTION_GATE_NAMES == (
        "rates_calm", "vrp_supportive",
        "credit_stable", "liquidity_expanding",
    )


# ---------------------------------------------------------------------------
# Source-level safety: no production-table writes
# ---------------------------------------------------------------------------


def test_module_does_not_write_to_production_tables():
    from pathlib import Path

    src = Path(
        "apps/api/src/data/strategy/safe_gate_evolution_shadow.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "INSERT INTO paper_trade",
        "INSERT INTO paper_position",
        "INSERT INTO paper_run_log",
        "INSERT INTO candidate_idea",
        "UPDATE paper_trade",
        "UPDATE paper_run_log",
        "DELETE FROM paper_",
    )
    for tok in forbidden:
        assert tok not in src, f"forbidden write {tok!r}"


def test_module_does_not_import_execution_paths():
    from pathlib import Path

    src = Path(
        "apps/api/src/data/strategy/safe_gate_evolution_shadow.py"
    ).read_text(encoding="utf-8")
    import_lines = [
        line for line in src.splitlines()
        if line.lstrip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    forbidden = (
        "submit_trade", "auto_trade_portfolio",
        "auto_trader", "paper_execution",
    )
    for tok in forbidden:
        assert tok not in joined, f"forbidden import {tok!r}"


def test_no_strategy_threshold_changes_in_module():
    from pathlib import Path

    src = Path(
        "apps/api/src/data/strategy/safe_gate_evolution_shadow.py"
    ).read_text(encoding="utf-8")
    # Tokens that would indicate threshold tweaking
    forbidden = (
        "exploratory", "EXPLORATORY",
        "MIN_GATE_SCORE", "RATE_THRESHOLD",
        "force_trade", "bypass_gates",
    )
    for tok in forbidden:
        assert tok not in src, f"forbidden token {tok!r}"
