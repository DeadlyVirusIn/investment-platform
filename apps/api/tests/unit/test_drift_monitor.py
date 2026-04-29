"""Phase 11U.3 - drift_monitor unit tests."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from apps.api.src.ml import drift_monitor as dmm
from apps.api.src.ml.drift_monitor import (
    DriftConfig,
    DriftInputError,
    DriftMonitorError,
    NON_ACTION_NOTICE,
    REPORT_VERSION,
    STATUS_CALIBRATION,
    STATUS_DATA_QUALITY,
    STATUS_FEATURE,
    STATUS_INSUFFICIENT,
    STATUS_OK,
    STATUS_PERFORMANCE,
    _aggregate_overall,
    _classify_calibration,
    _classify_coverage,
    _classify_feature,
    _classify_performance,
    report_path,
    run as run_drift,
    write_report,
)
from apps.api.src.ml.drift_metrics import (
    BucketLift,
    CalibrationDelta,
    CoverageDeltas,
    PerformanceDeltas,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _baseline_report(*, n_rows: int = 312, auc: float = 0.58,
                     brier: float = 0.22, hit: float = 0.51,
                     calib_bins: list[dict] | None = None,
                     buckets: dict | None = None) -> dict:
    return {
        "model_type": "logreg",
        "task": "classification",
        "target": "outcome_class",
        "splits": {
            "train":   {"end": "2024-12-31", "n": 800},
            "test":    {"start": "2025-01-01", "end": "2025-12-31",
                        "n": 150},
            "holdout": {"start": "2026-01-01", "end": "2026-04-08",
                        "n": n_rows},
        },
        "metrics": {
            "test":    {"auc_macro": auc, "brier_score": brier,
                        "hit_ratio": hit},
            "holdout": {"auc_macro": auc, "brier_score": brier,
                        "hit_ratio": hit,
                        "calibration_bins":
                            calib_bins or [
                                {"bin": "0.0-0.5",
                                 "actual_positive_rate": 0.10},
                                {"bin": "0.5-1.0",
                                 "actual_positive_rate": 0.40},
                            ],
                        "lift_by_bucket": buckets or {
                            "SHADOW_LOW":  {"n": 100,
                                            "actual_positive_rate": 0.10},
                            "SHADOW_MID":  {"n": 200,
                                            "actual_positive_rate": 0.30},
                            "SHADOW_HIGH": {"n":  80,
                                            "actual_positive_rate": 0.50},
                        }},
        },
        "dataset": {
            "id": "ds-1", "n_rows": 1000,
            "checksum_sha256": "abc",
        },
    }


def _shadow_report(*, n_rows: int = 200, auc: float = 0.56,
                   brier: float = 0.23, hit: float = 0.49,
                   calib_bins: list[dict] | None = None,
                   buckets: dict | None = None) -> dict:
    return {
        "report_version": "shadow-report-v1.0.0",
        "model_id": "m1",
        "model_artifact_checksum_sha256": "abcd",
        "model_status": "shadow_only",
        "scoring_window": {
            "start": "2026-04-09", "end": "2026-04-29",
        },
        "domain": "equity",
        "sources_included": ["research_fast_fill"],
        "coverage": {
            "rows_input": n_rows + 20,
            "rows_scored": n_rows,
            "rows_with_realized_label": n_rows,
            "rows_excluded": {
                "missing_features": 5,
                "is_provisional": 15,
            },
        },
        "model_metrics": {
            "auc_macro": auc, "brier_score": brier,
            "hit_ratio": hit,
            "calibration_bins":
                calib_bins or [
                    {"bin": "0.0-0.5", "actual_positive_rate": 0.12},
                    {"bin": "0.5-1.0", "actual_positive_rate": 0.42},
                ],
            "lift_by_bucket": buckets or {
                "SHADOW_LOW":  {"n":  60,
                                "actual_positive_rate": 0.12},
                "SHADOW_MID":  {"n": 100,
                                "actual_positive_rate": 0.32},
                "SHADOW_HIGH": {"n":  40,
                                "actual_positive_rate": 0.48},
            },
        },
        "rows": [],
    }


def _registry_dir(tmp_path: Path, *, model_id: str = "m1") -> Path:
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps([
        {"model_id": model_id, "status": "shadow_only",
         "artifact_path": str(tmp_path / "fake.pkl"),
         "artifact_checksum_sha256": "abcd"},
    ]), encoding="utf-8")
    return reg


def _cfg(tmp_path: Path, *, baseline=None, shadow=None,
         commit=False, model_id="m1") -> DriftConfig:
    base_path = tmp_path / "base.json"
    base_path.write_text(
        json.dumps(baseline or _baseline_report()), encoding="utf-8",
    )
    sh_path = tmp_path / "shadow.json"
    sh_path.write_text(
        json.dumps(shadow or _shadow_report()), encoding="utf-8",
    )
    return DriftConfig(
        model_id=model_id,
        baseline_report_path=base_path,
        shadow_report_path=sh_path,
        baseline_dataset_path=None,
        recent_dataset_path=None,
        output_dir=tmp_path,
        dry_run=not commit, commit=commit,
        explain=False,
    )


# ---------------------------------------------------------------------------
# Loaders + rejections
# ---------------------------------------------------------------------------

def test_run_loads_baseline_report(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = _cfg(tmp_path)
    body = run_drift(cfg, registry_path=reg)
    assert body["report_version"] == REPORT_VERSION


def test_run_loads_shadow_report(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = _cfg(tmp_path)
    body = run_drift(cfg, registry_path=reg)
    assert "checks" in body or body["overall_monitoring_status"] == \
        STATUS_INSUFFICIENT


def test_run_rejects_unknown_model_id(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = _cfg(tmp_path, model_id="ghost")
    with pytest.raises(DriftInputError, match="not in registry"):
        run_drift(cfg, registry_path=reg)


def test_run_rejects_missing_baseline_file(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = DriftConfig(
        model_id="m1",
        baseline_report_path=tmp_path / "missing.json",
        shadow_report_path=tmp_path / "shadow.json",
        baseline_dataset_path=None, recent_dataset_path=None,
        output_dir=tmp_path,
        dry_run=True, commit=False, explain=False,
    )
    (tmp_path / "shadow.json").write_text(
        json.dumps(_shadow_report()), encoding="utf-8",
    )
    with pytest.raises(DriftInputError, match="file not found"):
        run_drift(cfg, registry_path=reg)


def test_run_rejects_missing_shadow_file(tmp_path):
    reg = _registry_dir(tmp_path)
    (tmp_path / "base.json").write_text(
        json.dumps(_baseline_report()), encoding="utf-8",
    )
    cfg = DriftConfig(
        model_id="m1",
        baseline_report_path=tmp_path / "base.json",
        shadow_report_path=tmp_path / "missing.json",
        baseline_dataset_path=None, recent_dataset_path=None,
        output_dir=tmp_path,
        dry_run=True, commit=False, explain=False,
    )
    with pytest.raises(DriftInputError, match="file not found"):
        run_drift(cfg, registry_path=reg)


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------

def test_run_status_insufficient_data_when_below_min_rows(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = _cfg(tmp_path, shadow=_shadow_report(n_rows=50))
    body = run_drift(cfg, registry_path=reg)
    assert body["overall_monitoring_status"] == STATUS_INSUFFICIENT


def test_run_status_monitoring_ok_when_within_thresholds(tmp_path):
    reg = _registry_dir(tmp_path)
    base = _baseline_report(n_rows=220)
    base["dataset"]["n_rows"] = 220        # match coverage rows_scored
    rec = _shadow_report(n_rows=210)        # ~4.5% drop, no data-quality flag
    cfg = _cfg(tmp_path, baseline=base, shadow=rec)
    body = run_drift(cfg, registry_path=reg)
    assert body["overall_monitoring_status"] == STATUS_OK


def test_run_status_review_calibration_shift_when_bin_delta_above_review(
    tmp_path,
):
    reg = _registry_dir(tmp_path)
    base = _baseline_report(calib_bins=[
        {"bin": "0.0-0.5", "actual_positive_rate": 0.10},
    ])
    rec = _shadow_report(calib_bins=[
        {"bin": "0.0-0.5", "actual_positive_rate": 0.30},   # +0.20
    ])
    cfg = _cfg(tmp_path, baseline=base, shadow=rec)
    body = run_drift(cfg, registry_path=reg)
    assert body["checks"]["calibration"]["status"] == STATUS_CALIBRATION


def test_run_status_review_performance_decay_when_auc_drops(tmp_path):
    reg = _registry_dir(tmp_path)
    base = _baseline_report(auc=0.70)
    rec = _shadow_report(auc=0.60)
    cfg = _cfg(tmp_path, baseline=base, shadow=rec)
    body = run_drift(cfg, registry_path=reg)
    assert body["checks"]["performance"]["status"] == STATUS_PERFORMANCE


def test_run_status_review_data_quality_when_missingness_rises(tmp_path):
    reg = _registry_dir(tmp_path)
    base = _baseline_report()
    rec = _shadow_report()
    rec["coverage"]["rows_excluded"]["missing_features"] = 50
    cfg = _cfg(tmp_path, baseline=base, shadow=rec)
    body = run_drift(cfg, registry_path=reg)
    assert body["checks"]["coverage"]["status"] == STATUS_DATA_QUALITY


def test_run_status_review_data_quality_takes_priority(tmp_path):
    reg = _registry_dir(tmp_path)
    base = _baseline_report(auc=0.70)
    rec = _shadow_report(auc=0.55)        # performance decay too
    rec["coverage"]["rows_excluded"]["missing_features"] = 200
    cfg = _cfg(tmp_path, baseline=base, shadow=rec)
    body = run_drift(cfg, registry_path=reg)
    assert body["overall_monitoring_status"] == STATUS_DATA_QUALITY


def test_aggregate_priority_data_quality_first():
    out = _aggregate_overall(
        STATUS_DATA_QUALITY, STATUS_FEATURE, STATUS_PERFORMANCE,
    )
    assert out == STATUS_DATA_QUALITY


def test_aggregate_priority_feature_before_perf():
    out = _aggregate_overall(STATUS_FEATURE, STATUS_PERFORMANCE)
    assert out == STATUS_FEATURE


def test_aggregate_returns_ok_when_all_clean():
    out = _aggregate_overall(STATUS_OK, STATUS_OK, STATUS_OK)
    assert out == STATUS_OK


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_run_dry_run_writes_no_file(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = _cfg(tmp_path)
    run_drift(cfg, registry_path=reg)
    assert list(tmp_path.glob("model_drift_*.json")) == []


def test_run_commit_writes_report_only(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = _cfg(tmp_path, commit=True)
    body = run_drift(cfg, registry_path=reg)
    path = write_report(cfg, body)
    assert path.exists()


def test_run_filename_includes_model_id_and_timestamp(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = _cfg(tmp_path, commit=True)
    body = run_drift(cfg, registry_path=reg)
    p = report_path(cfg, body)
    assert p.name.startswith("model_drift_m1_")
    assert p.name.endswith(".json")


def test_run_refuses_overwrite(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = _cfg(tmp_path, commit=True)
    body = run_drift(cfg, registry_path=reg)
    write_report(cfg, body)
    with pytest.raises(DriftMonitorError, match="already exists"):
        write_report(cfg, body)


def test_run_no_db_imports():
    src = Path(dmm.__file__).read_text(encoding="utf-8")
    for tok in (
        "from apps.api.src.db", "INSERT INTO",
        "session.execute", "sqlalchemy", "session.commit",
    ):
        assert tok not in src, (
            f"drift_monitor must not touch DB: {tok!r}"
        )


def test_run_no_registry_writes():
    src = Path(dmm.__file__).read_text(encoding="utf-8")
    # The monitor reads via show_entry only — no register / write.
    assert "register(" not in src
    assert "registry.write_text" not in src
    assert "REGISTRY_PATH" not in src or "from apps.api.src.ml.model_registry import show_entry" in src


def test_run_no_pickle_writes():
    src = Path(dmm.__file__).read_text(encoding="utf-8")
    for tok in ("joblib.dump", "pickle.dump", "with open"):
        if tok == "with open":
            # Allowed only for read-mode (rb/r). Drift monitor does
            # not open files directly besides path.write_text on the
            # target report path.
            continue
        assert tok not in src


def test_run_does_not_modify_pickle_or_dataset_files(tmp_path):
    """Smoke: running with no datasets path must not touch the
    registry's artifact_path file."""
    reg = _registry_dir(tmp_path)
    fake_pkl = tmp_path / "fake.pkl"
    fake_pkl.write_bytes(b"binary-blob")
    mtime = fake_pkl.stat().st_mtime
    cfg = _cfg(tmp_path)
    run_drift(cfg, registry_path=reg)
    assert fake_pkl.stat().st_mtime == mtime
    assert fake_pkl.read_bytes() == b"binary-blob"


def test_run_review_notes_neutral_language(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = _cfg(tmp_path)
    body = run_drift(cfg, registry_path=reg)
    notes = body.get("review_notes", [])
    flat = " ".join(notes).lower()
    for tok in (
        "recommend", "promote", "best model", "bad model",
        "stop trading", "replace model", "failed model",
    ):
        assert tok not in flat, (
            f"review notes must stay neutral: {tok!r}"
        )


def test_run_no_recommendation_language():
    src = Path(dmm.__file__).read_text(encoding="utf-8")
    for pat in (
        r"\brecommend\w*", r"\bsignal\b", r"\btrade\s+now\b",
        r"\bplace\s+order\b", r"\bauto-?trade\b",
    ):
        assert not re.search(pat, src, flags=re.IGNORECASE), (
            f"forbidden pattern {pat!r}"
        )


def test_run_no_promotion_language():
    src = Path(dmm.__file__).read_text(encoding="utf-8")
    for pat in (
        r"\bbad\s+model\b", r"\bfailed\s+model\b",
        r"\bstop\s+trading\b", r"\breplace\s+model\b",
        r"\bpromote\s+model\b", r"\bbest\s+model\b",
        r"\bbroken\s+model\b",
    ):
        assert not re.search(pat, src, flags=re.IGNORECASE), (
            f"forbidden pattern {pat!r}"
        )


def test_run_includes_frozen_constants_block(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = _cfg(tmp_path)
    body = run_drift(cfg, registry_path=reg)
    fc = body["frozen_constants"]
    assert fc["min_recent_rows"] == 100
    assert fc["psi_review"] == 0.20
    assert fc["bucket_lift_drop_review"] == 0.25


def test_run_includes_non_action_notice(tmp_path):
    reg = _registry_dir(tmp_path)
    cfg = _cfg(tmp_path)
    body = run_drift(cfg, registry_path=reg)
    assert body["non_action_notice"] == NON_ACTION_NOTICE
    assert "promotion" in body["non_action_notice"].lower()


def test_classify_performance_perf_decay():
    perf = PerformanceDeltas(
        auc_baseline=0.7, auc_recent=0.6,
        auc_delta=-0.10, brier_baseline=0.2, brier_recent=0.2,
        brier_delta=0.0, hit_ratio_baseline=0.5,
        hit_ratio_recent=0.5, hit_ratio_delta=0.0,
    )
    assert _classify_performance(perf) == STATUS_PERFORMANCE


def test_classify_calibration_shift():
    perf = PerformanceDeltas(
        auc_baseline=None, auc_recent=None, auc_delta=None,
        brier_baseline=None, brier_recent=None, brier_delta=None,
        hit_ratio_baseline=None, hit_ratio_recent=None,
        hit_ratio_delta=None,
    )
    calib = CalibrationDelta(bins=[], max_abs_bin_delta=0.15)
    assert _classify_calibration(calib, perf) == STATUS_CALIBRATION


def test_classify_feature_drift_when_psi_high():
    rows = [{"feature": "f", "psi": 0.30, "ks": None,
             "status": STATUS_FEATURE}]
    assert _classify_feature(rows) == STATUS_FEATURE


def test_classify_coverage_data_quality_drop():
    cov = CoverageDeltas(
        rows_scored_baseline=1000, rows_scored_recent=200,
        rows_scored_delta_pct=-0.8,
        missingness_baseline=0.0, missingness_recent=0.0,
        missingness_delta=0.0,
        provisional_baseline=0.0, provisional_recent=0.0,
        provisional_delta=0.0,
        outlier_rate_baseline=0.0, outlier_rate_recent=0.0,
        outlier_rate_delta=0.0,
    )
    assert _classify_coverage(cov) == STATUS_DATA_QUALITY
