"""Wave 3A — Experiment Lab pure-logic unit tests.

Pins: spec validation bounds + canonical hashing, fold construction
(skips reported, cap disclosed), metric edge cases (single-class AUC,
censored counting, missing confidence/returns), Wilson CI, cost
sensitivity, promotion-readiness matrix (lab-gates-1), metric-hash
determinism + tolerance, environment capture redaction, and the frozen
adapter/benchmark registries (no arbitrary code).
"""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.evaluation.lab import (
    COST_SCENARIOS_BPS,
    GATE_POLICY_VERSION,
    LAB_EVALUATOR_VERSION,
    MAX_FOLDS,
    MAX_RANGE_DAYS,
    MAX_UNIVERSE,
    SPLIT_POLICY_VERSION,
    SpecError,
    _wilson_ci,
    build_folds,
    cost_sensitivity,
    environment_capture,
    evaluate_fold,
    experiment_hash,
    metric_hash,
    promotion_readiness,
    spec_payload,
    validate_spec,
)


def _spec(**over) -> dict:
    base = {"name": "unit", "start": "2024-01-01", "end": "2026-01-01"}
    base.update(over)
    return base


def _dec(day, label=1, conviction=70.0, ret=0.02, month=1, year=2025):
    return {
        "symbol": "AAA",
        "generated_at": dt.datetime(year, month, day,
                                    tzinfo=dt.timezone.utc),
        "action": "Buy", "conviction": conviction,
        "barrier_label": label, "realized_30d_return": ret,
        "barrier_n_bars": 20,
    }


# ── spec validation + hashing ─────────────────────────────────────────────

def test_spec_defaults_and_hash_determinism():
    a = validate_spec(_spec())
    b = validate_spec(_spec())
    assert experiment_hash(a) == experiment_hash(b)
    p = spec_payload(a)
    assert p["evaluator_version"] == LAB_EVALUATOR_VERSION
    assert p["split_policy_version"] == SPLIT_POLICY_VERSION


def test_spec_hash_changes_with_any_field():
    h0 = experiment_hash(validate_spec(_spec()))
    for change in ({"seed": 43}, {"fold_period": "M"},
                   {"universe": ["NVDA"]}, {"confidence_threshold": 55},
                   {"end": "2025-12-31"}):
        assert experiment_hash(validate_spec(_spec(**change))) != h0


def test_spec_bounds_rejected():
    for bad in (
        {"name": ""}, {"name": "x" * 200},
        {"engine": "eval('x')"}, {"target": "made_up"},
        {"universe": ["A" * 20]}, {"universe": [f"S{i}" for i in range(300)]},
        {"universe_size": 0}, {"universe_size": MAX_UNIVERSE + 1},
        {"start": "2026-01-01", "end": "2024-01-01"},
        {"start": "2000-01-01", "end": "2026-01-01"}
        if MAX_RANGE_DAYS < 9000 else {"fold_period": "D"},
        {"fold_period": "D"}, {"embargo_days": -1}, {"embargo_days": 999},
        {"benchmarks": ["custom_code"]}, {"cost_scenarios": ["free_money"]},
        {"confidence_threshold": 150}, {"seed": -1},
        {"actions": ["Steal"]}, {"nonsense_field": 1},
    ):
        with pytest.raises(SpecError):
            validate_spec(_spec(**bad))


def test_spec_not_a_dict_rejected():
    with pytest.raises(SpecError):
        validate_spec("import os")  # type: ignore[arg-type]


def test_universe_normalized_sorted_deduped():
    s = validate_spec(_spec(universe=["nvda", "NVDA", " tsm "]))
    assert s.universe == ("NVDA", "TSM")


# ── folds ──────────────────────────────────────────────────────────────────

def test_folds_group_by_quarter_and_skip_thin_windows():
    decisions = (
        [_dec(d, month=1) for d in range(1, 28)]        # Q1: 27 resolved
        + [_dec(d, month=4) for d in range(1, 8)]       # Q2: 7 resolved
    )
    spec = validate_spec(_spec(min_eval_rows=10))
    folds, skipped = build_folds(decisions, spec)
    assert [f["fold"] for f in folds] == ["2025-Q1"]
    assert skipped == [{"fold": "2025-Q2", "rows": 7, "resolved": 7,
                        "reason": "resolved < 10"}]


def test_censored_rows_do_not_count_toward_min_eval():
    decisions = ([_dec(d, month=1) for d in range(1, 10)]
                 + [_dec(d, month=1, label=None) for d in range(10, 28)])
    spec = validate_spec(_spec(min_eval_rows=10))
    folds, skipped = build_folds(decisions, spec)
    assert folds == [] and skipped[0]["resolved"] == 9


def test_fold_cap_drops_oldest_and_discloses():
    decisions = []
    for y in (2023, 2024, 2025, 2026):
        for m in (1, 4, 7, 10):
            decisions += [_dec(d, month=m, year=y) for d in range(1, 8)]
    spec = validate_spec(_spec(min_eval_rows=5, start="2023-01-01",
                               end="2026-12-31"))
    folds, skipped = build_folds(decisions, spec)
    assert len(folds) == MAX_FOLDS
    assert all("fold cap" in s["reason"] for s in skipped)


# ── fold metrics edge cases ────────────────────────────────────────────────

def test_single_class_fold_emits_no_auc():
    fold = {"fold": "2025-Q1",
            "rows": [_dec(d) for d in range(1, 20)],
            "resolved": [_dec(d) for d in range(1, 20)]}   # all hits
    spec = validate_spec(_spec())
    m = evaluate_fold(fold, spec)
    assert m["auc"] is None                    # never AUC on one class
    assert m["hit_rate"] == 1.0
    assert m["censored"] == 0


def test_censored_counted_and_disclosed():
    rows = [_dec(d) for d in range(1, 10)] + \
           [_dec(d, label=None) for d in range(10, 15)]
    fold = {"fold": "2025-Q1", "rows": rows,
            "resolved": [r for r in rows if r["barrier_label"] in (1, -1)]}
    m = evaluate_fold(fold, validate_spec(_spec()))
    assert m["candidates"] == 14 and m["resolved"] == 9 and m["censored"] == 5


def test_missing_confidence_and_returns_counted():
    rows = [_dec(1, conviction=None, ret=None),
            _dec(2, label=-1, conviction=None, ret=0.01)]
    fold = {"fold": "2025-Q1", "rows": rows, "resolved": rows}
    m = evaluate_fold(fold, validate_spec(_spec()))
    assert m["with_confidence"] == 0
    assert m["auc"] is None and m["brier"] is None
    assert m["n_returns"] == 1 and m["missing_returns"] == 1


def test_threshold_confusion_matrix():
    rows = [_dec(1, label=1, conviction=80), _dec(2, label=-1, conviction=90),
            _dec(3, label=1, conviction=40), _dec(4, label=-1, conviction=30)]
    fold = {"fold": "2025-Q1", "rows": rows, "resolved": rows}
    m = evaluate_fold(fold, validate_spec(_spec(confidence_threshold=60)))
    assert m["confusion"] == {"tp": 1, "fp": 1, "fn": 1, "tn": 1}
    assert m["precision_at_threshold"] == 0.5


def test_wilson_ci_bounds():
    lo, hi = _wilson_ci(50, 100)
    assert 0.40 < lo < 0.5 < hi < 0.60
    assert _wilson_ci(0, 0) is None
    lo0, _ = _wilson_ci(0, 20)
    assert lo0 == 0.0


# ── cost sensitivity ───────────────────────────────────────────────────────

def test_cost_sensitivity_scenarios():
    folds = [{"mean_realized_30d": 0.010}, {"mean_realized_30d": 0.0005}]
    out = cost_sensitivity(folds, validate_spec(_spec()))
    assert set(out) == set(COST_SCENARIOS_BPS)
    assert out["zero_cost"]["net_mean_30d"] == pytest.approx(0.00525)
    # expected 10bps: 0.010-0.001=0.009 ; 0.0005-0.001=-0.0005 → 1 positive
    assert out["expected_cost"]["folds_positive_net"] == 1
    assert out["stressed_cost"]["net_mean_30d"] < out["expected_cost"][
        "net_mean_30d"]


def test_cost_sensitivity_no_returns():
    out = cost_sensitivity([{"mean_realized_30d": None}],
                           validate_spec(_spec()))
    assert out == {"error": "no realized returns available"}


# ── promotion readiness (lab-gates-1) ─────────────────────────────────────

def _summary(resolved=500, folds=6):
    return {"total_resolved": resolved, "n_folds": folds}


def _fm(brier=0.20, base=0.25, ece=0.05):
    return {"brier": brier, "base_rate_brier": base, "ece": ece}


def test_verdict_insufficient_on_small_sample():
    v = promotion_readiness(_summary(resolved=50), [_fm()] * 6,
                            {"neutral": {"total_return": 0}}, {"x": {}}, [])
    assert v["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert v["policy"] == GATE_POLICY_VERSION


def test_verdict_insufficient_on_few_folds():
    v = promotion_readiness(_summary(folds=2), [_fm()] * 2,
                            {"neutral": {"total_return": 0}}, {"x": {}}, [])
    assert v["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_verdict_fails_baseline_when_base_rate_wins():
    fms = [_fm(brier=0.30, base=0.25)] * 6
    v = promotion_readiness(_summary(), fms,
                            {"neutral": {"total_return": 0}}, {"x": {}}, [])
    assert v["verdict"] == "FAILS_BASELINE"


def test_verdict_limitations_on_critical_warning():
    v = promotion_readiness(
        _summary(), [_fm()] * 6, {"neutral": {"total_return": 0}},
        {"x": {}}, ["CRITICAL data gap in fold 2"])
    assert v["verdict"] == "PASSES_BASELINE_WITH_LIMITATIONS"


def test_verdict_eligible_when_all_gates_pass():
    v = promotion_readiness(_summary(), [_fm()] * 6,
                            {"neutral": {"total_return": 0}}, {"x": {}}, [])
    assert v["verdict"] == "ELIGIBLE_FOR_OWNER_REVIEW"
    assert all(g["pass"] for g in v["gates"].values())


def test_verdict_reproducibility_failed_dominates():
    v = promotion_readiness(
        _summary(), [_fm()] * 6, {"neutral": {"total_return": 0}},
        {"x": {}}, [], reproducibility={"matches": False})
    assert v["verdict"] == "REPRODUCIBILITY_FAILED"


def test_verdict_never_contains_promotion_action():
    v = promotion_readiness(_summary(), [_fm()] * 6,
                            {"neutral": {"total_return": 0}}, {"x": {}}, [])
    assert "approve" not in str(v).lower()
    assert v["verdict"] in ("INSUFFICIENT_EVIDENCE", "REPRODUCIBILITY_FAILED",
                            "FAILS_BASELINE",
                            "PASSES_BASELINE_WITH_LIMITATIONS",
                            "ELIGIBLE_FOR_OWNER_REVIEW")


# ── metric hash + environment ─────────────────────────────────────────────

def test_metric_hash_deterministic_and_tolerant():
    folds = [{"a": 0.1234567890123456}]
    s = {"m": 1.0}
    assert metric_hash(folds, s) == metric_hash(folds, s)
    # differences beyond 10dp are within tolerance
    assert metric_hash([{"a": 0.12345678901}], s) == \
        metric_hash([{"a": 0.12345678902}], s)
    # differences at 3dp are not
    assert metric_hash([{"a": 0.124}], s) != metric_hash([{"a": 0.123}], s)


def test_environment_capture_has_no_secrets():
    env = environment_capture()
    flat = str(env).lower()
    assert "packages" in env and "python" in env
    for needle in ("password", "key", "token", "secret", "database_url",
                   "c:\\", "/home/"):
        assert needle not in flat
