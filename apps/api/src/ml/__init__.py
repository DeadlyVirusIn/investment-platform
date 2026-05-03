"""ML research foundation — dataset builder, leakage guards, walk-forward.

Purpose: convert decision_log + paper_trade_log + price bars into a clean,
leakage-free supervised learning dataset and evaluate simple models with
walk-forward splits. Output is ADVISORY ONLY until Engine C is explicitly
rewired.

Ordering rule:
  1. build_dataset()   → DataFrame (features + labels)
  2. validate_no_leakage(df) → raises if violations
  3. build_feature_health(df) → diagnostic report
  4. run_baselines(df) → baseline table
  5. walk_forward_evaluate(df) → gated behind ML_MIN_TRAINING_ROWS
  6. build_advisory(df, model_out) → per-decision advisory

Public re-exports.
"""

from apps.api.src.ml.dataset import build_dataset, DatasetResult
from apps.api.src.ml.features import (
    FEATURE_COLUMNS, LABEL_COLUMNS, IDENTITY_COLUMNS,
    OUTCOME_FORBIDDEN_PATTERNS,
)
from apps.api.src.ml.labels import (
    LABEL_HORIZONS, LabelConfig, attach_labels,
)
from apps.api.src.ml.validation import (
    LeakageError, LeakageReport, validate_no_leakage,
)
from apps.api.src.ml.splits import (
    WalkForwardConfig, walk_forward_splits, enough_data_for_ml,
)
from apps.api.src.ml.baselines import run_baselines, BaselineResult
from apps.api.src.ml.evaluation import (
    evaluate_walk_forward, WalkForwardEvalResult, classification_metrics,
)
from apps.api.src.ml.report import build_feature_health, FeatureHealthReport
from apps.api.src.ml.advisory import (
    Advisory, AdvisoryAction, build_advisory, EngineCStatus,
    engine_c_status,
)
from apps.api.src.ml.patterns import discover_patterns, PatternReport, BucketStats
from apps.api.src.ml.baselines_v2 import run_improved_baselines
from apps.api.src.ml.snapshots import (
    SnapshotRecord, capture_snapshot, latest_snapshot, list_snapshots,
    engine_c_readiness as engine_c_readiness_v2,
)
from apps.api.src.ml.recommendation import build_recommendation
from apps.api.src.ml.annotation import build_decision_annotation

__all__ = [
    "build_dataset", "DatasetResult",
    "FEATURE_COLUMNS", "LABEL_COLUMNS", "IDENTITY_COLUMNS",
    "OUTCOME_FORBIDDEN_PATTERNS",
    "LABEL_HORIZONS", "LabelConfig", "attach_labels",
    "LeakageError", "LeakageReport", "validate_no_leakage",
    "WalkForwardConfig", "walk_forward_splits", "enough_data_for_ml",
    "run_baselines", "BaselineResult",
    "evaluate_walk_forward", "WalkForwardEvalResult", "classification_metrics",
    "build_feature_health", "FeatureHealthReport",
    "Advisory", "AdvisoryAction", "build_advisory",
    "EngineCStatus", "engine_c_status",
    "discover_patterns", "PatternReport", "BucketStats",
    "run_improved_baselines",
    "SnapshotRecord", "capture_snapshot", "latest_snapshot",
    "list_snapshots", "engine_c_readiness_v2",
    "build_recommendation", "build_decision_annotation",
]
