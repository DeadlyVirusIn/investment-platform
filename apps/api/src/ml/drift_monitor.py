"""Phase 11U.3 - drift monitor orchestrator.

Loads registry entry (read-only), baseline + shadow report JSON files
(read-only), optionally two datasets for feature-drift checks
(read-only), computes deterministic drift metrics, classifies
statuses, assembles a JSON report dict. NEVER writes registry.
NEVER writes any DB. NEVER mutates source files. NEVER imports
broker / live / execution / strict-engine modules.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from loguru import logger

from apps.api.src.ml.drift_metrics import (
    BucketLift,
    CalibrationDelta,
    CoverageDeltas,
    PerformanceDeltas,
    PSIResult,
    bucket_lift,
    calibration_delta,
    coverage_deltas,
    ks,
    performance_deltas,
    psi,
)
from apps.api.src.ml.drift_thresholds import (
    AUC_DROP_REVIEW,
    BRIER_INCREASE_REVIEW,
    BUCKET_LIFT_DROP_REVIEW,
    CALIBRATION_BIN_DELTA_REVIEW,
    COVERAGE_DROP_REVIEW,
    HIT_RATIO_DROP_REVIEW,
    MIN_RECENT_ROWS,
    MISSINGNESS_INCREASE_REVIEW,
    OUTLIER_RATE_INCREASE_REVIEW,
    PROVISIONAL_RATE_INCREASE_REVIEW,
    PSI_HIGH_REVIEW,
    PSI_REVIEW,
)
from apps.api.src.ml.model_registry import show_entry


REPORT_VERSION = "model-drift-v1.0.0"
REPORTS_DIR = Path("reports")
NON_ACTION_NOTICE = (
    "Monitoring report only. No model promotion, trade decision, "
    "or execution guidance."
)

# Frozen status taxonomy.
STATUS_OK = "MONITORING_OK"
STATUS_DATA_QUALITY = "REVIEW_DATA_QUALITY"
STATUS_CALIBRATION = "REVIEW_CALIBRATION_SHIFT"
STATUS_FEATURE = "REVIEW_FEATURE_DRIFT"
STATUS_PERFORMANCE = "REVIEW_PERFORMANCE_DECAY"
STATUS_INSUFFICIENT = "INSUFFICIENT_RECENT_DATA"

# Priority order for overall_monitoring_status (data quality first).
_OVERALL_PRIORITY: tuple[str, ...] = (
    STATUS_DATA_QUALITY,
    STATUS_FEATURE,
    STATUS_CALIBRATION,
    STATUS_PERFORMANCE,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class DriftMonitorError(RuntimeError):
    """Base drift monitor error."""


class DriftInputError(DriftMonitorError):
    """Required input file missing or malformed."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriftConfig:
    model_id: str
    baseline_report_path: Path
    shadow_report_path: Path
    baseline_dataset_path: Path | None
    recent_dataset_path: Path | None
    output_dir: Path
    dry_run: bool
    commit: bool
    explain: bool

    def __post_init__(self) -> None:
        if self.dry_run == self.commit:
            raise ValueError(
                "dry_run and commit are mutually exclusive"
            )
        if not self.model_id:
            raise ValueError("model_id required")


# ---------------------------------------------------------------------------
# Loaders (read-only)
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    if not path.exists():
        raise DriftInputError(f"file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise DriftInputError(f"file empty: {path}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DriftInputError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DriftInputError(
            f"file {path} must be a JSON object",
        )
    return payload


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------

def _classify_performance(perf: PerformanceDeltas) -> str:
    if perf.auc_delta is not None and perf.auc_delta <= -AUC_DROP_REVIEW:
        return STATUS_PERFORMANCE
    if (
        perf.hit_ratio_delta is not None
        and perf.hit_ratio_delta <= -HIT_RATIO_DROP_REVIEW
    ):
        return STATUS_PERFORMANCE
    return STATUS_OK


def _classify_calibration(
    calib: CalibrationDelta, perf: PerformanceDeltas,
) -> str:
    if calib.max_abs_bin_delta >= CALIBRATION_BIN_DELTA_REVIEW:
        return STATUS_CALIBRATION
    if (
        perf.brier_delta is not None
        and perf.brier_delta >= BRIER_INCREASE_REVIEW
    ):
        return STATUS_CALIBRATION
    return STATUS_OK


def _classify_feature(per_feature_results: list[dict]) -> str:
    for r in per_feature_results:
        psi_value = r.get("psi")
        if psi_value is not None and psi_value >= PSI_REVIEW:
            return STATUS_FEATURE
    return STATUS_OK


def _classify_bucket(lift: BucketLift) -> str:
    if (
        lift.lift_drop_rel is not None
        and lift.lift_drop_rel >= BUCKET_LIFT_DROP_REVIEW
    ):
        return STATUS_PERFORMANCE
    return STATUS_OK


def _classify_coverage(c: CoverageDeltas) -> str:
    if (
        c.rows_scored_delta_pct is not None
        and c.rows_scored_delta_pct <= -COVERAGE_DROP_REVIEW
    ):
        return STATUS_DATA_QUALITY
    if (
        c.missingness_delta is not None
        and c.missingness_delta >= MISSINGNESS_INCREASE_REVIEW
    ):
        return STATUS_DATA_QUALITY
    if (
        c.outlier_rate_delta is not None
        and c.outlier_rate_delta >= OUTLIER_RATE_INCREASE_REVIEW
    ):
        return STATUS_DATA_QUALITY
    if (
        c.provisional_delta is not None
        and c.provisional_delta
        >= PROVISIONAL_RATE_INCREASE_REVIEW
    ):
        return STATUS_DATA_QUALITY
    return STATUS_OK


def _aggregate_overall(*sub_statuses: str) -> str:
    """Apply frozen priority order: DATA_QUALITY > FEATURE >
    CALIBRATION > PERFORMANCE > OK."""
    fired = set(s for s in sub_statuses if s != STATUS_OK)
    for tag in _OVERALL_PRIORITY:
        if tag in fired:
            return tag
    return STATUS_OK


# ---------------------------------------------------------------------------
# Feature drift over datasets (optional)
# ---------------------------------------------------------------------------

def _read_dataset_columns(
    path: Path,
) -> tuple[list[str], dict[str, list[Any]]]:
    """Read a parquet/csv/jsonl dataset into a column-keyed dict.
    Read-only. Returns (column_names, column_values)."""
    if path.suffix == ".parquet":
        try:
            import pandas as pd
            df = pd.read_parquet(path)
        except Exception as exc:
            raise DriftInputError(
                f"cannot read parquet {path}: {exc}"
            ) from exc
    elif path.suffix == ".csv":
        try:
            import pandas as pd
            df = pd.read_csv(path)
        except Exception as exc:
            raise DriftInputError(
                f"cannot read csv {path}: {exc}"
            ) from exc
    elif path.suffix == ".jsonl":
        rows: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
        try:
            import pandas as pd
            df = pd.DataFrame(rows)
        except Exception as exc:
            raise DriftInputError(
                f"cannot build dataframe from {path}: {exc}"
            ) from exc
    else:
        raise DriftInputError(
            f"unsupported dataset suffix: {path.suffix}"
        )
    cols = list(df.columns)
    return cols, {c: df[c].tolist() for c in cols}


def _feature_drift(
    baseline_path: Path | None,
    recent_path: Path | None,
) -> dict:
    if baseline_path is None or recent_path is None:
        return {
            "status": STATUS_OK,
            "n_features_evaluated": 0,
            "per_feature": [],
            "max_psi": None,
            "thresholds_used": {
                "psi_review": PSI_REVIEW,
                "psi_high_review": PSI_HIGH_REVIEW,
            },
            "skipped_reason": "no_dataset_paths_provided",
        }
    _, b_cols = _read_dataset_columns(baseline_path)
    _, r_cols = _read_dataset_columns(recent_path)
    per_feature: list[dict] = []
    max_psi = 0.0
    for name in sorted(set(b_cols.keys()) & set(r_cols.keys())):
        if not (
            name.startswith("feat_")
            or name.startswith("ctx_")
            or name.startswith("px_")
        ):
            continue
        b_vals = b_cols[name]
        r_vals = r_cols[name]
        if not b_vals or not r_vals:
            continue
        try:
            res = psi(b_vals, r_vals)
        except Exception:  # noqa: BLE001
            continue
        ks_value: float | None = None
        sample = next(
            (v for v in b_vals if v is not None), None,
        )
        if isinstance(sample, (int, float)) and not isinstance(
            sample, bool,
        ):
            try:
                ks_value = ks(
                    [v for v in b_vals if v is not None],
                    [v for v in r_vals if v is not None],
                )
            except Exception:  # noqa: BLE001
                ks_value = None
        f_status = STATUS_FEATURE if res.psi >= PSI_REVIEW else STATUS_OK
        per_feature.append({
            "feature": name,
            "psi": res.psi,
            "ks": ks_value,
            "status": f_status,
        })
        if res.psi > max_psi:
            max_psi = res.psi
    overall = _classify_feature(per_feature)
    return {
        "status": overall,
        "n_features_evaluated": len(per_feature),
        "per_feature": per_feature,
        "max_psi": round(max_psi, 6) if per_feature else None,
        "thresholds_used": {
            "psi_review": PSI_REVIEW,
            "psi_high_review": PSI_HIGH_REVIEW,
        },
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _baseline_and_recent_metrics(
    baseline_report: dict, shadow_report: dict,
) -> tuple[dict, dict]:
    """Pull metric blocks from training-report holdout (or test if
    holdout missing) and from shadow report's model_metrics."""
    metrics = baseline_report.get("metrics") or {}
    base = metrics.get("holdout") or metrics.get("test") or {}
    rec = shadow_report.get("model_metrics") or {}
    return dict(base), dict(rec)


def _baseline_buckets(report: dict) -> dict:
    """Extract bucket-by-bucket counts/rates from a training report.
    Falls back to empty dict if absent (training reports may not yet
    include bucket lift)."""
    metrics = report.get("metrics") or {}
    holdout = (
        metrics.get("holdout") or metrics.get("test") or {}
    )
    return holdout.get("lift_by_bucket") or {}


def _recent_buckets(shadow_report: dict) -> dict:
    return (
        shadow_report.get("model_metrics") or {}
    ).get("lift_by_bucket") or {}


def _baseline_coverage(report: dict) -> dict:
    """Training reports don't always carry a `coverage` block; use a
    minimal stand-in derived from `dataset.n_rows`."""
    cov = report.get("coverage")
    if isinstance(cov, dict):
        return cov
    n = (report.get("dataset") or {}).get("n_rows") or 0
    return {"rows_scored": int(n), "rows_excluded": {}}


def _recent_coverage(shadow_report: dict) -> dict:
    return shadow_report.get("coverage") or {
        "rows_scored": 0, "rows_excluded": {},
    }


def _baseline_window(report: dict) -> dict:
    splits = report.get("splits") or {}
    holdout = splits.get("holdout") or splits.get("test") or {}
    n = (report.get("dataset") or {}).get("n_rows") or 0
    return {
        "source": "training_holdout",
        "start": holdout.get("start"),
        "end": holdout.get("end"),
        "n_rows": int(holdout.get("n", n) or 0),
    }


def _recent_window(shadow_report: dict) -> dict:
    win = shadow_report.get("scoring_window") or {}
    cov = shadow_report.get("coverage") or {}
    return {
        "source": "shadow_score_report",
        "start": win.get("start"),
        "end": win.get("end"),
        "n_rows": int(cov.get("rows_scored", 0) or 0),
    }


def run(
    cfg: DriftConfig,
    *,
    registry_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict:
    """Orchestrator. Returns the assembled report dict. NEVER writes
    files. Caller decides whether to persist."""
    entry = show_entry(cfg.model_id, registry_path=registry_path)
    if entry is None:
        raise DriftInputError(
            f"model_id {cfg.model_id!r} not in registry"
        )
    baseline_report = _load_json(cfg.baseline_report_path)
    shadow_report = _load_json(cfg.shadow_report_path)

    baseline_window = _baseline_window(baseline_report)
    recent_window = _recent_window(shadow_report)

    n_recent = recent_window.get("n_rows", 0) or 0

    when = (now_utc or dt.datetime.now(dt.timezone.utc)).isoformat()

    if n_recent < MIN_RECENT_ROWS:
        return _stub_insufficient_report(
            cfg=cfg, entry=entry,
            baseline_window=baseline_window,
            recent_window=recent_window,
            generated_at=when,
        )

    base_metrics, rec_metrics = _baseline_and_recent_metrics(
        baseline_report, shadow_report,
    )
    perf = performance_deltas(base_metrics, rec_metrics)

    base_calib_bins = base_metrics.get("calibration_bins") or []
    rec_calib_bins = rec_metrics.get("calibration_bins") or []
    calib = calibration_delta(base_calib_bins, rec_calib_bins)

    base_buckets = _baseline_buckets(baseline_report)
    rec_buckets = _recent_buckets(shadow_report)
    lift = bucket_lift(base_buckets, rec_buckets)

    cov = coverage_deltas(
        _baseline_coverage(baseline_report),
        _recent_coverage(shadow_report),
    )

    feature_block = _feature_drift(
        cfg.baseline_dataset_path, cfg.recent_dataset_path,
    )

    perf_status = _classify_performance(perf)
    calib_status = _classify_calibration(calib, perf)
    feature_status = feature_block["status"]
    bucket_status = _classify_bucket(lift)
    coverage_status = _classify_coverage(cov)

    overall = _aggregate_overall(
        coverage_status, feature_status, calib_status,
        perf_status, bucket_status,
    )

    review_notes: list[str] = []
    if overall == STATUS_OK:
        review_notes.append(
            "All checks within thresholds. Continue observation."
        )
    if feature_status == STATUS_FEATURE:
        for r in feature_block["per_feature"]:
            if r["psi"] is not None and r["psi"] >= PSI_REVIEW:
                review_notes.append(
                    f"Feature {r['feature']} PSI={r['psi']} "
                    f"(at or above {PSI_REVIEW}). "
                    "Recent distribution differs from baseline."
                )
                break
    if perf_status == STATUS_PERFORMANCE:
        review_notes.append(
            f"Performance delta crossed review threshold "
            f"(auc_delta={perf.auc_delta}, "
            f"hit_ratio_delta={perf.hit_ratio_delta})."
        )
    if calib_status == STATUS_CALIBRATION:
        review_notes.append(
            f"Calibration shift observed "
            f"(max_abs_bin_delta={calib.max_abs_bin_delta})."
        )
    if coverage_status == STATUS_DATA_QUALITY:
        review_notes.append(
            "Coverage / missingness / provisional rate changed beyond "
            "review thresholds. Check input data quality."
        )
    review_notes.append(
        f"Recent-window n={n_recent} satisfies "
        f"min_recent_rows={MIN_RECENT_ROWS}."
    )

    body = {
        "report_version": REPORT_VERSION,
        "generated_at": when,
        "model_id": cfg.model_id,
        "model_status": str(entry.get("status", "shadow_only")),
        "baseline_window": baseline_window,
        "recent_window": recent_window,
        "overall_monitoring_status": overall,
        "checks": {
            "performance": {
                "status": perf_status,
                "auc_baseline": perf.auc_baseline,
                "auc_recent": perf.auc_recent,
                "auc_delta": perf.auc_delta,
                "brier_baseline": perf.brier_baseline,
                "brier_recent": perf.brier_recent,
                "brier_delta": perf.brier_delta,
                "hit_ratio_baseline": perf.hit_ratio_baseline,
                "hit_ratio_recent": perf.hit_ratio_recent,
                "hit_ratio_delta": perf.hit_ratio_delta,
                "thresholds_used": {
                    "auc_drop_review": AUC_DROP_REVIEW,
                    "brier_increase_review": BRIER_INCREASE_REVIEW,
                    "hit_ratio_drop_review": HIT_RATIO_DROP_REVIEW,
                },
            },
            "calibration": {
                "status": calib_status,
                "max_abs_bin_delta": calib.max_abs_bin_delta,
                "bins": calib.bins,
                "thresholds_used": {
                    "calibration_bin_delta_review":
                        CALIBRATION_BIN_DELTA_REVIEW,
                },
            },
            "feature_drift": feature_block,
            "bucket_separation": {
                "status": bucket_status,
                "baseline_lift": lift.baseline_lift,
                "recent_lift": lift.recent_lift,
                "lift_drop_rel": lift.lift_drop_rel,
                "by_bucket": lift.by_bucket,
                "thresholds_used": {
                    "bucket_lift_drop_review":
                        BUCKET_LIFT_DROP_REVIEW,
                },
            },
            "coverage": {
                "status": coverage_status,
                "rows_scored_baseline": cov.rows_scored_baseline,
                "rows_scored_recent": cov.rows_scored_recent,
                "rows_scored_delta_pct": cov.rows_scored_delta_pct,
                "missingness_baseline": cov.missingness_baseline,
                "missingness_recent": cov.missingness_recent,
                "missingness_delta": cov.missingness_delta,
                "provisional_baseline": cov.provisional_baseline,
                "provisional_recent": cov.provisional_recent,
                "provisional_delta": cov.provisional_delta,
                "outlier_rate_baseline": cov.outlier_rate_baseline,
                "outlier_rate_recent": cov.outlier_rate_recent,
                "outlier_rate_delta": cov.outlier_rate_delta,
                "thresholds_used": {
                    "coverage_drop_review": COVERAGE_DROP_REVIEW,
                    "missingness_increase_review":
                        MISSINGNESS_INCREASE_REVIEW,
                    "outlier_rate_increase_review":
                        OUTLIER_RATE_INCREASE_REVIEW,
                    "provisional_rate_increase_review":
                        PROVISIONAL_RATE_INCREASE_REVIEW,
                },
            },
        },
        "review_notes": review_notes,
        "frozen_constants": {
            "report_version": REPORT_VERSION,
            "min_recent_rows": MIN_RECENT_ROWS,
            "auc_drop_review": AUC_DROP_REVIEW,
            "brier_increase_review": BRIER_INCREASE_REVIEW,
            "hit_ratio_drop_review": HIT_RATIO_DROP_REVIEW,
            "psi_review": PSI_REVIEW,
            "psi_high_review": PSI_HIGH_REVIEW,
            "missingness_increase_review":
                MISSINGNESS_INCREASE_REVIEW,
            "outlier_rate_increase_review":
                OUTLIER_RATE_INCREASE_REVIEW,
            "bucket_lift_drop_review": BUCKET_LIFT_DROP_REVIEW,
            "calibration_bin_delta_review":
                CALIBRATION_BIN_DELTA_REVIEW,
            "coverage_drop_review": COVERAGE_DROP_REVIEW,
            "provisional_rate_increase_review":
                PROVISIONAL_RATE_INCREASE_REVIEW,
        },
        "non_action_notice": NON_ACTION_NOTICE,
        "warnings": [],
    }
    logger.info(
        "phase 11U drift complete: model_id={} overall={} "
        "n_recent={}",
        cfg.model_id, overall, n_recent,
    )
    return body


def _stub_insufficient_report(
    *,
    cfg: DriftConfig,
    entry: dict,
    baseline_window: dict,
    recent_window: dict,
    generated_at: str,
) -> dict:
    return {
        "report_version": REPORT_VERSION,
        "generated_at": generated_at,
        "model_id": cfg.model_id,
        "model_status": str(entry.get("status", "shadow_only")),
        "baseline_window": baseline_window,
        "recent_window": recent_window,
        "overall_monitoring_status": STATUS_INSUFFICIENT,
        "checks": {},
        "review_notes": [
            f"Recent-window n={recent_window.get('n_rows', 0)} below "
            f"min_recent_rows={MIN_RECENT_ROWS}. Defer review until "
            "more rows accumulate."
        ],
        "frozen_constants": {
            "report_version": REPORT_VERSION,
            "min_recent_rows": MIN_RECENT_ROWS,
        },
        "non_action_notice": NON_ACTION_NOTICE,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Persistence (commit-only)
# ---------------------------------------------------------------------------

def report_path(
    cfg: DriftConfig,
    body: dict,
) -> Path:
    """Filename keyed on (model_id, generated_at_iso). Refused-on-
    overwrite enforcement happens in `write_report`."""
    out = Path(cfg.output_dir or REPORTS_DIR)
    out.mkdir(parents=True, exist_ok=True)
    ts = body.get("generated_at", "").replace(":", "").replace("-", "")
    if "." in ts:
        ts = ts.split(".")[0]
    if "+" in ts:
        ts = ts.split("+")[0] + "Z"
    if not ts.endswith("Z"):
        ts = ts + "Z"
    return out / (
        f"model_drift_{cfg.model_id}_{ts}.json"
    )


def write_report(
    cfg: DriftConfig,
    body: dict,
) -> Path:
    if not cfg.commit:
        raise DriftMonitorError(
            "write_report requires commit=True"
        )
    path = report_path(cfg, body)
    if path.exists():
        raise DriftMonitorError(
            f"report file already exists; refusing to overwrite: "
            f"{path}"
        )
    path.write_text(
        json.dumps(body, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path
