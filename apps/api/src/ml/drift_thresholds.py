"""Phase 11U.2 - frozen drift thresholds.

Bumping any constant in this module REQUIRES a registry-review.
Tests assert exact values; mutating these is treated as a breaking
change.
"""

from __future__ import annotations

from typing import Final


MIN_RECENT_ROWS: Final[int] = 100

# Performance
AUC_DROP_REVIEW: Final[float] = 0.05
BRIER_INCREASE_REVIEW: Final[float] = 0.03
HIT_RATIO_DROP_REVIEW: Final[float] = 0.05

# Feature drift
PSI_REVIEW: Final[float] = 0.20
PSI_HIGH_REVIEW: Final[float] = 0.35

# Data quality
MISSINGNESS_INCREASE_REVIEW: Final[float] = 0.10
OUTLIER_RATE_INCREASE_REVIEW: Final[float] = 0.05

# Bucket separation
BUCKET_LIFT_DROP_REVIEW: Final[float] = 0.25

# Calibration
CALIBRATION_BIN_DELTA_REVIEW: Final[float] = 0.10

# Coverage
COVERAGE_DROP_REVIEW: Final[float] = 0.30
PROVISIONAL_RATE_INCREASE_REVIEW: Final[float] = 0.20
