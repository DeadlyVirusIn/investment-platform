"""Tests for governance.alerting — pure rule layer."""

from __future__ import annotations

from src.governance.alerting import (
    SEV_CRIT,
    SEV_INFO,
    SEV_WARN,
    baseline_alert,
    calibration_alert,
    drift_alerts,
    engine_b_alert,
    evaluate,
    ml_alpha_alert,
)


def test_engine_b_alert_critical_at_disabled_threshold():
    out = engine_b_alert({"rolling_sharpe": -0.9, "state": "DISABLED"})
    assert len(out) == 1
    assert out[0].severity == SEV_CRIT


def test_engine_b_alert_warn_at_degraded_threshold():
    out = engine_b_alert({"rolling_sharpe": -0.4, "state": "DEGRADED"})
    assert len(out) == 1
    assert out[0].severity == SEV_WARN


def test_engine_b_alert_silent_when_active():
    out = engine_b_alert({"rolling_sharpe": 1.5, "state": "ACTIVE"})
    assert out == []


def test_engine_b_alert_silent_when_no_sharpe():
    assert engine_b_alert({}) == []
    assert engine_b_alert(None) == []


def test_baseline_alert_only_when_underperforming():
    s = {"system_underperforming_baseline": True,
          "delta_sharpe_vs_baseline": -0.5,
          "best_baseline_name": "tsmom_60d"}
    out = baseline_alert(s)
    assert len(out) == 1
    assert out[0].severity == SEV_CRIT
    assert "tsmom_60d" in out[0].detail


def test_baseline_alert_silent_when_outperforming():
    s = {"system_underperforming_baseline": False,
          "delta_sharpe_vs_baseline": 0.5,
          "best_baseline_name": "tsmom_60d"}
    assert baseline_alert(s) == []


def test_ml_alpha_alert_critical():
    out = ml_alpha_alert({"delta_sharpe_vs_deterministic": -0.8})
    assert len(out) == 1
    assert out[0].severity == SEV_CRIT


def test_ml_alpha_alert_warn():
    out = ml_alpha_alert({"delta_sharpe_vs_deterministic": -0.1})
    assert len(out) == 1
    assert out[0].severity == SEV_WARN


def test_ml_alpha_alert_silent_when_positive():
    assert ml_alpha_alert({"delta_sharpe_vs_deterministic": 0.5}) == []


def test_calibration_alert_levels():
    assert calibration_alert({"ece": 0.05}) == []
    w = calibration_alert({"ece": 0.12})
    assert w and w[0].severity == SEV_WARN
    c = calibration_alert({"ece": 0.30})
    assert c and c[0].severity == SEV_CRIT


def test_drift_alerts_maps_severity():
    drift_agg = {
        "results": [
            {"name": "feature_drift:x", "severity": "CRITICAL",
             "detail": "PSI=0.5", "statistic": 0.5},
            {"name": "performance_drift", "severity": "WARN",
             "detail": "Sharpe drop 0.6", "statistic": -0.6},
            {"name": "regime_drift", "severity": "OK",
             "detail": "stable", "statistic": 0.05},
        ],
    }
    out = drift_alerts(drift_agg)
    sevs = {a.severity for a in out}
    assert SEV_CRIT in sevs
    assert SEV_WARN in sevs
    assert all(a.severity in {SEV_WARN, SEV_CRIT} for a in out)


def test_evaluate_aggregates_and_marks_advisory():
    out = evaluate(
        engine_b_verdict={"rolling_sharpe": -0.9, "state": "DISABLED"},
        baseline_snapshot={
            "system_underperforming_baseline": True,
            "delta_sharpe_vs_baseline": -0.4,
            "best_baseline_name": "tsmom_60d",
        },
        promotion_inputs={"delta_sharpe_vs_deterministic": -0.1,
                            "ece": 0.30},
        drift_aggregate={"results": [
            {"name": "feature_drift:x", "severity": "WARN",
             "detail": "PSI=0.15", "statistic": 0.15},
        ]},
    )
    assert out["overall_severity"] == SEV_CRIT
    assert out["advisory_only"] is True
    assert out["auto_action_taken"] is False
    assert out["n_critical"] >= 1


def test_evaluate_clean_state_info():
    out = evaluate(
        engine_b_verdict={"rolling_sharpe": 1.5, "state": "ACTIVE"},
        baseline_snapshot={"system_underperforming_baseline": False,
                            "delta_sharpe_vs_baseline": 0.5},
        promotion_inputs={"delta_sharpe_vs_deterministic": 0.5,
                            "ece": 0.05},
        drift_aggregate=None,
    )
    assert out["overall_severity"] == SEV_INFO
    assert out["alerts"] == []


def test_evaluate_with_no_inputs_safe():
    out = evaluate()
    assert out["overall_severity"] == SEV_INFO
    assert out["alerts"] == []
    assert out["advisory_only"] is True
