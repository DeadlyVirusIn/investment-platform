"""Phase ML-3 — passive shadow ML.

Entirely advisory: train on historical data, score recent decisions, store
predictions. Never affects execution, sizing, or blocking.
"""

from apps.api.src.ml.shadow.eligibility import (
    EligibilityStatus, EligibilityReport, evaluate_eligibility,
)
from apps.api.src.ml.shadow.trainer import (
    ModelType, TrainerResult, train_shadow_models,
)
from apps.api.src.ml.shadow.calibration import (
    CalibrationReport, compute_calibration,
)
from apps.api.src.ml.shadow.disagreement import (
    DisagreementReport, compute_disagreements,
)
from apps.api.src.ml.shadow.comparison import (
    ShadowComparison, compare_shadow_vs_baselines,
)
from apps.api.src.ml.shadow.scorer import (
    score_recent_decisions, ShadowScoringResult,
)
from apps.api.src.ml.shadow.orchestrator import (
    run_nightly_shadow, NightlyShadowResult,
)

__all__ = [
    "EligibilityStatus", "EligibilityReport", "evaluate_eligibility",
    "ModelType", "TrainerResult", "train_shadow_models",
    "CalibrationReport", "compute_calibration",
    "DisagreementReport", "compute_disagreements",
    "ShadowComparison", "compare_shadow_vs_baselines",
    "score_recent_decisions", "ShadowScoringResult",
    "run_nightly_shadow", "NightlyShadowResult",
]
