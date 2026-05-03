"""Phase ML-2.5 — safe historical replay.

Replay the current engines over past dates using strictly point-in-time
data. Produces synthetic decisions + future-only labels, kept in separate
tables so they never mix with real paper_trade / decision_log rows.

Public API:
    PointInTimeDataAccessor   — PIT price + market-series accessor
    PITCatalystService        — replay-safe catalyst summary
    Replayer                  — orchestrates per-date per-symbol replay
    label_outcomes_for_run    — attaches forward-only labels
    validate_replay_leakage   — strict leakage guard
    Universe                  — resolver + survivorship warnings
    ReplayReport              — per-run diagnostics
"""

from apps.api.src.ml.replay.point_in_time import (
    PITError, PointInTimeDataAccessor, PITPriceBar,
)
from apps.api.src.ml.replay.universe import (
    DEFAULT_UNIVERSE, Universe, resolve_universe,
)
from apps.api.src.ml.replay.replayer import (
    Replayer, ReplayRunConfig, ReplayRunResult,
)
from apps.api.src.ml.replay.outcomes import (
    label_outcomes_for_run, OutcomeRow,
)
from apps.api.src.ml.replay.leakage import (
    ReplayLeakageError, ReplayLeakageReport, validate_replay_leakage,
)
from apps.api.src.ml.replay.report import (
    build_replay_report, ReplayReport,
)

__all__ = [
    "PITError", "PointInTimeDataAccessor", "PITPriceBar",
    "DEFAULT_UNIVERSE", "Universe", "resolve_universe",
    "Replayer", "ReplayRunConfig", "ReplayRunResult",
    "label_outcomes_for_run", "OutcomeRow",
    "ReplayLeakageError", "ReplayLeakageReport", "validate_replay_leakage",
    "build_replay_report", "ReplayReport",
]
