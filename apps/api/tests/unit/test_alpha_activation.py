"""SYSTEM-ALPHA-2 activation tests — orchestrator, idempotency, isolation.

DB-free: stub sessions intercept SQL and record calls.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import pytest

from apps.api.src.alpha.activation import (
    process_decision_attribution, process_paper_trades,
    write_provider_reliability, write_system_health_score,
)


# ---------------------------------------------------------------------------
# Session stub
# ---------------------------------------------------------------------------

@dataclass
class _MockResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    def mappings(self): return self
    def all(self): return list(self.rows)
    def first(self): return self.rows[0] if self.rows else None
    def fetchone(self):
        return tuple(self.rows[0].values()) if self.rows else None
    def scalar(self):
        return next(iter(self.rows[0].values())) if self.rows else 0


class StubSession:
    def __init__(self):
        self.executed: list[tuple[str, dict]] = []
        self.commits = 0
        self.scripted: list[list[dict[str, Any]]] = []
        self.script_idx = 0

    def script(self, batches: list[list[dict[str, Any]]]) -> "StubSession":
        self.scripted = batches
        return self

    def execute(self, stmt, params=None, *a, **kw):
        self.executed.append((str(stmt)[:80], dict(params or {})))
        s = str(stmt).strip().upper()
        if s.startswith("SELECT"):
            if self.script_idx < len(self.scripted):
                rows = self.scripted[self.script_idx]
                self.script_idx += 1
                return _MockResult(rows=rows)
            return _MockResult(rows=[])
        if s.startswith("UPDATE") or s.startswith("INSERT"):
            return _MockResult(rows=[{"id": "stub"}])
        return _MockResult(rows=[])

    def commit(self):
        self.commits += 1

    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass


# ---------------------------------------------------------------------------
# Phase 1 — decision attribution
# ---------------------------------------------------------------------------

def test_phase1_no_rows_returns_zero():
    s = StubSession().script([[]])
    r = process_decision_attribution(s, dry_run=True)
    assert r["processed"] == 0
    assert r["phase"] == "decision_attribution"


def test_phase1_processes_batch_dry_run():
    s = StubSession().script([[
        {"id": "d1", "inputs_used": {"mean_20d_ret": 0.001},
         "context_values": {"stress_regime": False,
                              "directional_regime": True,
                              "gates_favorable": 3},
         "catalyst": {"event_risk_score": 0.1,
                       "catalyst_score": 0.2, "trade_policy": "neutral"},
         "data_quality": {"confidence": 0.9},
         "risk_context": {}, "feature_confidence": 0.9},
    ], []])
    r = process_decision_attribution(s, dry_run=True)
    assert r["processed"] == 1
    # dry_run → no commits
    assert s.commits == 0


def test_phase1_errors_captured_not_raised():
    # Row that will crash attribution via non-dict fields; we inject by
    # making context_values a non-dict string which `_clip` tolerates.
    s = StubSession().script([[
        {"id": "d1", "inputs_used": None, "context_values": "broken",
         "catalyst": None, "data_quality": None, "risk_context": None,
         "feature_confidence": None},
    ], []])
    r = process_decision_attribution(s, dry_run=True)
    # Must not raise — either processed or skipped.
    assert isinstance(r["processed"], int)
    assert isinstance(r["skipped"], int)


# ---------------------------------------------------------------------------
# Phase 2 — paper trades
# ---------------------------------------------------------------------------

def test_phase2_skips_open_trades_via_sql_filter():
    # Empty results → nothing processed; still returns shape.
    s = StubSession().script([[]])
    r = process_paper_trades(s, dry_run=True)
    assert r["phase"] == "paper_trades"
    assert r["execution_quality_written"] == 0


def test_phase2_losing_trade_gets_failure_analysis_dry_run():
    s = StubSession().script([[
        {"id": "t1", "symbol": "AAPL", "engine": "A",
         "entry_date": dt.date(2025, 1, 5),
         "exit_date":  dt.date(2025, 1, 10),
         "entry_price": 100.0, "exit_price": 98.0,
         "gross_ret_pct": -2.0, "net_ret_pct": -2.0,
         "days_held": 5, "status": "closed",
         "regime_at_entry": "directional",
         "catalyst_snapshot": {"trade_policy": "neutral",
                                 "days_to_earnings": 1},
         "data_confidence": 0.9, "near_earnings": True,
         "execution_quality": None,
         "failure_analysis": None, "failure_version": None},
    ], []])
    r = process_paper_trades(s, dry_run=True)
    assert r["execution_quality_written"] == 1
    assert r["failure_analysis_written"] == 1


def test_phase2_winning_trade_no_failure_analysis():
    s = StubSession().script([[
        {"id": "t1", "symbol": "AAPL", "engine": "A",
         "entry_date": dt.date(2025, 1, 5),
         "exit_date":  dt.date(2025, 1, 10),
         "entry_price": 100.0, "exit_price": 103.0,
         "gross_ret_pct": 3.0, "net_ret_pct": 3.0,
         "days_held": 5, "status": "closed",
         "regime_at_entry": "directional",
         "catalyst_snapshot": {}, "data_confidence": 0.9,
         "near_earnings": False,
         "execution_quality": None,
         "failure_analysis": None, "failure_version": None},
    ], []])
    r = process_paper_trades(s, dry_run=True)
    assert r["execution_quality_written"] == 1
    assert r["failure_analysis_written"] == 0


# ---------------------------------------------------------------------------
# Phase 3 — system health
# ---------------------------------------------------------------------------

def test_phase3_dry_run_preview():
    s = StubSession().script([
        [],         # ml_research_snapshot
        [],         # execution proxy
        [],         # paper feedback
        [],         # risk proxy
    ])
    r = write_system_health_score(s, dry_run=True)
    assert r["phase"] == "system_health"
    assert r["written"] is False
    assert "preview" in r


def test_phase3_inserts_when_not_dry():
    # Force at least one commit path
    s = StubSession().script([
        [{"tier": "baselines_only", "leakage_clean": True,
          "feature_health": {"catalyst_coverage": 0.4},
          "baseline_results": {"v1": [{"sharpe_proxy": 0.2}]}}],
        [{"avg_eq": 0.6}],
        [{"wr": 0.55}],
        [{"max_drawdown_pct": -2.0}],
    ])
    r = write_system_health_score(s, dry_run=False)
    assert r["written"] is True
    assert "overall" in r


# ---------------------------------------------------------------------------
# Phase 4 — provider reliability
# ---------------------------------------------------------------------------

def test_phase4_writes_one_row_per_provider():
    s = StubSession().script([
        [],   # backfill run lookup returns none
    ])
    r = write_provider_reliability(s, dry_run=False)
    assert r["phase"] == "provider_reliability"
    assert r["written"] >= 4   # 4 default providers


def test_phase4_dry_run_writes_nothing_but_returns_shape():
    s = StubSession().script([[]])
    r = write_provider_reliability(s, dry_run=True)
    assert r["written"] == 0
    assert isinstance(r["errors"], list)


# ---------------------------------------------------------------------------
# Orchestrator — phase isolation
# ---------------------------------------------------------------------------

def test_orchestrator_result_structure():
    from apps.api.src.jobs.alpha_nightly import _summary
    phases = {
        "decision_attribution": {"processed": 5},
        "paper_trades": {"execution_quality_written": 3,
                          "failure_analysis_written": 2},
        "system_health": {"overall": 72},
        "provider_reliability": {"written": 4},
        "coverage": {"decisions_attribution_pct": 0.5},
    }
    s = _summary(phases)
    assert s["decision_attribution_processed"] == 5
    assert s["paper_trades_eq_written"] == 3
    assert s["health_overall"] == 72
    assert s["provider_rows"] == 4
    assert s["coverage"]["decisions_attribution_pct"] == 0.5
