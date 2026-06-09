"""Phase 2 — closed options trade analytics. Pure aggregator, no DB.

Also pins the route is GET-only + the source has no INSERT/UPDATE/DELETE
(mirrors test_paper_executed_api.py).
"""

from __future__ import annotations

import re
from pathlib import Path

from apps.api.src.options.portfolio.closed_analytics import aggregate_closed


def _t(pnl, strategy="SHORT_PUT_CREDIT_SPREAD", exit_reason="TP50"):
    return {
        "realized_pnl_dollars": pnl,
        "strategy": strategy,
        "exit_reason": exit_reason,
    }


def test_empty_honest():
    r = aggregate_closed([])
    assert r["status"] == "empty"
    assert r["total_closed"] == 0
    assert r["wins"] == 0 and r["losses"] == 0 and r["breakeven"] == 0
    assert r["total_realized"] == 0.0
    assert r["win_rate"] is None
    assert r["avg_winner"] is None and r["avg_loser"] is None
    assert r["expectancy"] is None and r["profit_factor"] is None
    assert r["by_strategy"] == [] and r["by_exit_reason"] == []


def test_mixed_wins_losses_breakeven():
    trades = [
        _t(100.0), _t(50.0),          # 2 wins
        _t(-40.0), _t(-10.0),         # 2 losses
        _t(0.0),                      # 1 breakeven
        _t(None),                     # None → 0.0 → breakeven
    ]
    r = aggregate_closed(trades)
    assert r["status"] == "live"
    assert r["total_closed"] == 6
    assert r["wins"] == 2
    assert r["losses"] == 2
    assert r["breakeven"] == 2
    assert r["win_rate"] == round(2 / 6, 4)
    assert r["total_realized"] == 100.0
    assert r["avg_winner"] == 75.0          # (100+50)/2
    assert r["avg_loser"] == -25.0          # (-40-10)/2
    assert r["expectancy"] == round(100.0 / 6, 2)
    # profit_factor = 150 / 50 = 3.0
    assert r["profit_factor"] == 3.0


def test_strategy_grouping():
    trades = [
        _t(100.0, strategy="SHORT_PUT_CREDIT_SPREAD"),
        _t(-30.0, strategy="SHORT_PUT_CREDIT_SPREAD"),
        _t(60.0, strategy="IRON_CONDOR"),
    ]
    r = aggregate_closed(trades)
    by = {s["strategy"]: s for s in r["by_strategy"]}
    assert set(by) == {"SHORT_PUT_CREDIT_SPREAD", "IRON_CONDOR"}
    sp = by["SHORT_PUT_CREDIT_SPREAD"]
    assert sp["count"] == 2
    assert sp["wins"] == 1 and sp["losses"] == 1
    assert sp["realized"] == 70.0           # 100 - 30
    assert sp["win_rate"] == 0.5
    ic = by["IRON_CONDOR"]
    assert ic["count"] == 1
    assert ic["wins"] == 1 and ic["losses"] == 0
    assert ic["realized"] == 60.0


def test_exit_reason_grouping():
    trades = [
        _t(40.0, exit_reason="TP50"),
        _t(20.0, exit_reason="TP50"),
        _t(-15.0, exit_reason="DTE7"),
        _t(None, exit_reason=None),         # None → "UNKNOWN"
    ]
    r = aggregate_closed(trades)
    by = {x["exit_reason"]: x for x in r["by_exit_reason"]}
    assert by["TP50"]["count"] == 2 and by["TP50"]["realized"] == 60.0
    assert by["DTE7"]["count"] == 1 and by["DTE7"]["realized"] == -15.0
    assert by["UNKNOWN"]["count"] == 1 and by["UNKNOWN"]["realized"] == 0.0


def test_profit_factor_all_wins_is_none():
    r = aggregate_closed([_t(10.0), _t(20.0), _t(0.0)])
    # no losses → profit_factor undefined → None
    assert r["losses"] == 0
    assert r["profit_factor"] is None
    assert r["avg_loser"] is None


def test_profit_factor_mix():
    r = aggregate_closed([_t(80.0), _t(-20.0), _t(-20.0)])
    # gross_win 80 / abs(gross_loss 40) = 2.0
    assert r["profit_factor"] == 2.0


def test_profit_factor_all_losses_is_zero():
    r = aggregate_closed([_t(-10.0), _t(-30.0)])
    # gross_win 0 / abs(gross_loss 40) = 0.0
    assert r["wins"] == 0 and r["losses"] == 2
    assert r["profit_factor"] == 0.0
    assert r["avg_winner"] is None


# --- route / read-only pins (mirror test_paper_executed_api.py) -------------

def test_closed_analytics_route_registered_get_only():
    import apps.api.src.options.routes_readonly as mod
    target = "/options/portfolio/closed-analytics"
    found = []
    for r in mod.router.routes:
        if getattr(r, "path", "") == target:
            methods = {m.upper() for m in (getattr(r, "methods", set()) or set())}
            found.append(methods)
            assert methods <= {"GET", "HEAD", "OPTIONS"}, (
                f"non-GET on {target}: {methods}")
    assert found, f"route {target} not registered"


def test_no_writes_in_closed_analytics_source():
    src = Path(
        "apps/api/src/options/portfolio/closed_analytics.py"
    ).read_text(encoding="utf-8")
    write_patterns = (
        re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
        re.compile(r"\bUPDATE\s+\w+\s+SET\b", re.IGNORECASE),
        re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    )
    for line in src.splitlines():
        stripped = line.lstrip()
        if (stripped.startswith('"') or stripped.startswith("#")
                or stripped.startswith("'")):
            continue
        for pat in write_patterns:
            assert not pat.search(line), (
                f"write found in read-only source: {line.strip()}")
