"""Phase 3 — promotion/rejection audit. Pure tests, no DB.

Covers every classify_candidate reason branch, honest-empty aggregation,
mixed-candidate aggregation (runs ordering, reason_counts, rejected list,
cap), plus the GET-only route pin + no-writes-in-source pin (mirrors
test_options_closed_analytics.py).
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from apps.api.src.options.portfolio.promotion_audit import (
    REJECTED_CAP,
    aggregate_audit,
    classify_candidate,
)

GATES = dict(
    universe="QQQ",
    strategy="SHORT_PUT_CREDIT_SPREAD",
    min_dte=21,
    max_dte=45,
    min_conf=0.60,
)


def _cand(**over):
    base = {
        "underlying": "QQQ",
        "rule_id": "SHORT_PUT_CREDIT_SPREAD",
        "confidence": 0.70,
        "dte": 30,
        "has_legs": True,
        "quotes_stale": False,
        "legs_fillable": True,
        "economics_viable": True,
    }
    base.update(over)
    return base


# --- classify_candidate: each reason branch ---------------------------------

def test_classify_wrong_underlying():
    assert classify_candidate(
        _cand(underlying="SPY"), **GATES) == "wrong_underlying"


def test_classify_wrong_strategy():
    assert classify_candidate(
        _cand(rule_id="LONG_CALL_VERTICAL"), **GATES) == "wrong_strategy"


def test_classify_no_legs():
    assert classify_candidate(
        _cand(has_legs=False, dte=None), **GATES) == "no_legs"


def test_classify_dte_below_window():
    assert classify_candidate(_cand(dte=14), **GATES) == "dte_out_of_range"


def test_classify_dte_above_window():
    assert classify_candidate(_cand(dte=60), **GATES) == "dte_out_of_range"


def test_classify_dte_none_with_legs():
    # legs exist but expiry unresolvable → treated as out of range
    assert classify_candidate(_cand(dte=None), **GATES) == "dte_out_of_range"


def test_classify_confidence_below_gate():
    assert classify_candidate(
        _cand(confidence=0.55), **GATES) == "confidence_below_gate"
    assert classify_candidate(
        _cand(confidence=None), **GATES) == "confidence_below_gate"


def test_classify_unfillable_leg():
    assert classify_candidate(
        _cand(legs_fillable=False), **GATES) == "unfillable_leg"


def test_classify_stale_quotes():
    # P6D.34D — gate-passing candidate whose leg quotes' max effective age
    # exceeded OPTIONS_CANARY_MAX_PROMOTION_AGE_SECONDS (or were missing).
    assert classify_candidate(
        _cand(quotes_stale=True), **GATES) == "stale_quotes"


def test_classify_stale_quotes_before_fillability():
    # ORDERING PIN (mirrors selector attribution): the 900s freshness gate
    # runs BEFORE compute_fill, so a stale candidate that would ALSO fail
    # fillability (60s fill gate) and economics reads 'stale_quotes'.
    assert classify_candidate(
        _cand(quotes_stale=True, legs_fillable=False,
              economics_viable=False), **GATES
    ) == "stale_quotes"


def test_classify_stale_quotes_after_confidence():
    # ORDERING PIN: stale is only attributed to gate-passing candidates —
    # cheap gates (dte/confidence) win first, same as the selector.
    assert classify_candidate(
        _cand(confidence=0.55, quotes_stale=True), **GATES
    ) == "confidence_below_gate"
    assert classify_candidate(
        _cand(dte=14, quotes_stale=True), **GATES) == "dte_out_of_range"


def test_classify_stale_quotes_none_not_rejection():
    # quotes_stale=None (not checked — cheap gate failed upstream or no
    # classification ran) is NOT a rejection on its own.
    assert classify_candidate(_cand(quotes_stale=None), **GATES) == "eligible"


def test_classify_uneconomic():
    # P6D.33A — fillable but fails assess_economics → terminal 'uneconomic'.
    assert classify_candidate(
        _cand(economics_viable=False), **GATES) == "uneconomic"


def test_classify_uneconomic_after_fillability():
    # Unfillable wins over uneconomic (selector gate order: fill → economics).
    assert classify_candidate(
        _cand(legs_fillable=False, economics_viable=False), **GATES
    ) == "unfillable_leg"


def test_classify_eligible():
    assert classify_candidate(_cand(), **GATES) == "eligible"
    # legs_fillable=None (not checked) is NOT a rejection
    assert classify_candidate(_cand(legs_fillable=None), **GATES) == "eligible"
    # economics_viable=None (not checked / malformed shape) is NOT a rejection
    assert classify_candidate(
        _cand(economics_viable=None), **GATES) == "eligible"


def test_classify_gate_order_underlying_first():
    # Wrong on every gate → first gate (underlying) wins
    c = _cand(underlying="SPY", rule_id="LONG_CALL", has_legs=False,
              dte=None, confidence=0.1, quotes_stale=True,
              legs_fillable=False, economics_viable=False)
    assert classify_candidate(c, **GATES) == "wrong_underlying"


def test_classify_dte_window_inclusive():
    assert classify_candidate(_cand(dte=21), **GATES) == "eligible"
    assert classify_candidate(_cand(dte=45), **GATES) == "eligible"


# --- aggregate_audit ---------------------------------------------------------

def test_aggregate_honest_empty():
    r = aggregate_audit([], [])
    assert r["status"] == "empty"
    assert r["runs"] == []
    assert r["rejected"] == []
    assert r["eligible_count"] == 0
    assert r["reason_counts"] == {}


def _funnel(run_date, **over):
    base = {
        "run_date": run_date,
        "candidates_total": 5,
        "promoted": 1,
        "filled": 1,
        "skip_slot_full": 0,
        "skip_over_capital_cap": 0,
        "skip_proposal_duplicate": 0,
        "skip_other": 0,
    }
    base.update(over)
    return base


def _classified(cid, run_date, reason, **over):
    base = {
        "candidate_id": cid,
        "run_date": run_date,
        "underlying": "QQQ",
        "rule_id": "SHORT_PUT_CREDIT_SPREAD",
        "confidence": 0.70,
        "dte": 30,
        "reason": reason,
    }
    base.update(over)
    return base


def test_aggregate_mixed():
    d1 = dt.date(2026, 6, 7)
    d2 = dt.date(2026, 6, 8)
    funnel = [
        _funnel(d1, promoted=0, skip_slot_full=2),
        _funnel(d2, promoted=1, skip_proposal_duplicate=1),
    ]
    cands = [
        _classified(1374, d2, "eligible"),
        _classified(1384, d2, "dte_out_of_range", dte=14),
        _classified(1387, d2, "dte_out_of_range", dte=60),
        _classified(1390, d2, "wrong_strategy",
                    rule_id="LONG_CALL_VERTICAL"),
        _classified(1300, d1, "wrong_underlying", underlying="SPY"),
        _classified(1301, d1, "confidence_below_gate", confidence=0.4),
        _classified(1302, d1, "unfillable_leg"),
        _classified(1303, d1, "no_legs", dte=None, confidence=None),
    ]
    r = aggregate_audit(funnel, cands)
    assert r["status"] == "live"

    # runs newest first, dates serialized to ISO strings
    assert [x["run_date"] for x in r["runs"]] == ["2026-06-08", "2026-06-07"]
    assert r["runs"][0]["promoted"] == 1
    assert r["runs"][0]["skip_proposal_duplicate"] == 1
    assert r["runs"][1]["skip_slot_full"] == 2

    assert r["eligible_count"] == 1
    assert r["reason_counts"] == {
        "eligible": 1,
        "dte_out_of_range": 2,
        "wrong_strategy": 1,
        "wrong_underlying": 1,
        "confidence_below_gate": 1,
        "unfillable_leg": 1,
        "no_legs": 1,
    }

    # rejected excludes eligible, newest first (then id desc)
    ids = [x["candidate_id"] for x in r["rejected"]]
    assert 1374 not in ids
    assert ids == [1390, 1387, 1384, 1303, 1302, 1301, 1300]
    by_id = {x["candidate_id"]: x for x in r["rejected"]}
    assert by_id[1390]["reason"] == "wrong_strategy"
    assert by_id[1390]["strategy"] == "LONG_CALL_VERTICAL"
    assert by_id[1384]["dte"] == 14
    assert by_id[1300]["underlying"] == "SPY"
    assert by_id[1301]["confidence"] == 0.4
    assert by_id[1303]["confidence"] is None
    assert all(x["run_date"] == "2026-06-08" for x in r["rejected"][:3])


def test_aggregate_funnel_only_is_live():
    r = aggregate_audit([_funnel(dt.date(2026, 6, 8))], [])
    assert r["status"] == "live"
    assert len(r["runs"]) == 1
    assert r["rejected"] == []
    assert r["eligible_count"] == 0


def test_aggregate_reports_recorded_skip_split_counters():
    """P6D.36C — runs expose the RECORDED selector-stage skip counters
    (stale_quotes / uneconomic / confidence_below_gate), defaulting 0
    for pre-095 rows that lack the keys."""
    row = _funnel(
        dt.date(2026, 6, 8),
        skip_stale_quotes=3, skip_uneconomic=2,
        skip_confidence_below_gate=1,
    )
    r = aggregate_audit([row], [])
    run = r["runs"][0]
    assert run["skip_stale_quotes"] == 3
    assert run["skip_uneconomic"] == 2
    assert run["skip_confidence_below_gate"] == 1

    legacy = aggregate_audit([_funnel(dt.date(2026, 6, 7))], [])
    run = legacy["runs"][0]
    assert run["skip_stale_quotes"] == 0
    assert run["skip_uneconomic"] == 0
    assert run["skip_confidence_below_gate"] == 0


def test_aggregate_reports_risk_control_counters():
    """P6D.36D — runs expose the enforced risk-control rejection counters
    (underlying_cap / daily_cap / cash_floor / aggregate_loss_cap),
    defaulting 0 for pre-096 rows."""
    row = _funnel(
        dt.date(2026, 6, 8),
        skip_underlying_cap=2, skip_daily_cap=1,
        skip_cash_floor=3, skip_aggregate_loss_cap=4,
    )
    run = aggregate_audit([row], [])["runs"][0]
    assert run["skip_underlying_cap"] == 2
    assert run["skip_daily_cap"] == 1
    assert run["skip_cash_floor"] == 3
    assert run["skip_aggregate_loss_cap"] == 4

    legacy = aggregate_audit([_funnel(dt.date(2026, 6, 7))], [])["runs"][0]
    assert legacy["skip_underlying_cap"] == 0
    assert legacy["skip_daily_cap"] == 0
    assert legacy["skip_cash_floor"] == 0
    assert legacy["skip_aggregate_loss_cap"] == 0


def test_aggregate_candidates_only_is_live():
    r = aggregate_audit([], [_classified(1, dt.date(2026, 6, 8), "eligible")])
    assert r["status"] == "live"
    assert r["runs"] == []
    assert r["eligible_count"] == 1


def test_aggregate_rejected_cap():
    d = dt.date(2026, 6, 8)
    cands = [
        _classified(i, d, "dte_out_of_range", dte=5)
        for i in range(REJECTED_CAP + 20)
    ]
    r = aggregate_audit([], cands)
    assert len(r["rejected"]) == REJECTED_CAP
    assert r["reason_counts"]["dte_out_of_range"] == REJECTED_CAP + 20


# --- route / read-only pins (mirror test_options_closed_analytics.py) -------

def test_promotion_audit_route_registered_get_only():
    import apps.api.src.options.routes_readonly as mod
    target = "/options/portfolio/promotion-audit"
    found = []
    for r in mod.router.routes:
        if getattr(r, "path", "") == target:
            methods = {m.upper() for m in (getattr(r, "methods", set()) or set())}
            found.append(methods)
            assert methods <= {"GET", "HEAD", "OPTIONS"}, (
                f"non-GET on {target}: {methods}")
    assert found, f"route {target} not registered"


def test_no_writes_in_promotion_audit_source():
    src = Path(
        "apps/api/src/options/portfolio/promotion_audit.py"
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
