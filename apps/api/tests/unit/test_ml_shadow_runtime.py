"""ML-5 — shadow runtime loader fail-soft tests."""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock

from apps.api.src.ml.shadow.runtime import (
    _as_date, _days_since, _num, load_latest_shadow_signal,
)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def test_as_date_accepts_iso():
    d = _as_date("2026-04-24")
    assert d == dt.date(2026, 4, 24)


def test_as_date_returns_none_on_bad():
    assert _as_date("garbage") is None
    assert _as_date(None) is None


def test_num_handles_junk():
    assert _num(None) is None
    assert _num("abc") is None
    assert _num("0.5") == 0.5
    assert _num(3) == 3.0


def test_days_since_handles_various_inputs():
    now = dt.datetime.utcnow()
    d = _days_since(now)
    assert d is not None
    assert d >= 0
    assert _days_since("not-a-date") is None
    assert _days_since(None) is None


# ---------------------------------------------------------------------------
# load_latest_shadow_signal — fail-soft
# ---------------------------------------------------------------------------

def _mock_session_raises():
    s = MagicMock()
    s.execute.side_effect = RuntimeError("db down")
    return s


def test_loader_failsoft_on_db_error():
    s = _mock_session_raises()
    out = load_latest_shadow_signal(
        s, symbol="SPY", as_of_date=dt.date.today(),
        engine="B", decision_context={},
    )
    assert out["available"] is False
    assert out["ml_score"] is None
    assert out["source"] == "ml_shadow_prediction"
    assert any("load_error" in rc for rc in out["reason_codes"])


def test_loader_returns_unavailable_when_no_prediction():
    s = MagicMock()
    # First execute (pred by date) → empty
    # Second execute (pred fallback) → empty
    mapping_first = MagicMock()
    mapping_first.first.return_value = None
    mapping_second = MagicMock()
    mapping_second.first.return_value = None
    s.execute.return_value.mappings.side_effect = [
        mapping_first, mapping_second,
    ]
    out = load_latest_shadow_signal(
        s, symbol="SPY", as_of_date=dt.date.today(),
        engine="B", decision_context={},
    )
    assert out["available"] is False
    assert "no_prediction" in out["reason_codes"]


def test_loader_marks_unavailable_when_stale_or_bad_status():
    s = MagicMock()
    old = dt.datetime.utcnow() - dt.timedelta(days=30)
    pred_mapping = MagicMock()
    pred_mapping.first.return_value = {
        "id": "p1", "model_run_id": "r1",
        "symbol": "SPY", "as_of_date": dt.date.today(),
        "decision_ts": None, "source_type": "real",
        "engine": "B", "original_decision": "enter_long",
        "engine_confidence": 0.6,
        "ml_score": 0.5, "ml_confidence": 0.8,
        "ml_action": "reduce", "ml_reason_codes": [],
    }
    run_mapping = MagicMock()
    run_mapping.first.return_value = {
        "id": "r1", "created_at": old, "model_type": "logistic",
        "status": "SHADOW_OUTPERFORMING", "row_count": 1000,
        "labeled_row_count": 500,
        "metrics": {}, "baseline_comparison": {
            "winner": "ml", "delta_sharpe": 0.1,
        },
        "calibration": {"ece": 0.02, "poor_calibration": False},
        "leakage_report": {}, "feature_health": {}, "blockers": [],
    }
    s.execute.return_value.mappings.side_effect = [
        pred_mapping, run_mapping,
    ]
    out = load_latest_shadow_signal(
        s, symbol="SPY", as_of_date=dt.date.today(),
        engine="B", decision_context={},
        max_stale_days=7,
    )
    # Stale → not available even if status is good
    assert out["available"] is False
    assert out["stale"] is True
    assert out["ml_action"] == "reduce"


def test_loader_returns_available_on_fresh_outperforming():
    s = MagicMock()
    recent = dt.datetime.utcnow() - dt.timedelta(days=1)
    pred_mapping = MagicMock()
    pred_mapping.first.return_value = {
        "id": "p1", "model_run_id": "r1",
        "symbol": "SPY", "as_of_date": dt.date.today(),
        "decision_ts": None, "source_type": "real",
        "engine": "B", "original_decision": "enter_long",
        "engine_confidence": 0.6,
        "ml_score": 0.4, "ml_confidence": 0.82,
        "ml_action": "reduce", "ml_reason_codes": ["mean_revert"],
    }
    run_mapping = MagicMock()
    run_mapping.first.return_value = {
        "id": "r1", "created_at": recent, "model_type": "rf",
        "status": "SHADOW_OUTPERFORMING", "row_count": 2000,
        "labeled_row_count": 1000,
        "metrics": {}, "baseline_comparison": {
            "winner": "ml", "delta_sharpe": 0.15,
        },
        "calibration": {"ece": 0.03, "poor_calibration": False},
        "leakage_report": {}, "feature_health": {}, "blockers": [],
    }
    s.execute.return_value.mappings.side_effect = [
        pred_mapping, run_mapping,
    ]
    out = load_latest_shadow_signal(
        s, symbol="SPY", as_of_date=dt.date.today(),
        engine="B", decision_context={},
        max_stale_days=7,
    )
    assert out["available"] is True
    assert out["beats_baseline"] is True
    assert out["calibration_ok"] is True
    assert out["stale"] is False
    assert out["ml_confidence"] == 0.82
    assert out["ml_action"] == "reduce"
