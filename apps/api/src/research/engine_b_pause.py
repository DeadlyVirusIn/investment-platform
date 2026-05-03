"""Engine B → B2 promotion pause module.

Governance protection: when B2 edge deteriorates, automatically PAUSE
promotion-readiness output (block any ADVANCE recommendation) until
evidence stabilizes. Pause is observational — it does NOT change
execution, ENGINE_B_MODE, or any production behavior.

Severity:
  INFO     — observation noted, no override
  WARNING  — gates may pass but action stays HOLD; label suffix _PAUSED
  BLOCKING — gates IGNORED; action forced to HOLD; label denotes severity

Triggers (from current spec):
  edge_trajectory   — 30d/60d/90d edge decline
  tail_risk         — placeholder for future tail breach trigger
  regime_leakage    — placeholder for stress-LONG drift
  sample_size       — placeholder for sample collapse

Clear condition:
  30d edge_trajectory has trend != DECLINING AND
  recent_mean_edge_bps > 0
  for 2 consecutive decision snapshots.

Pure function. No DB writes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# Thresholds
EDGE_BLOCKING_DELTA_BPS = -10.0   # delta_bps ≤ -10 → blocking when 30d declining
PAUSE_CLEAR_CONSECUTIVE = 2       # snapshots required to clear


SEV_INFO = "INFO"
SEV_WARNING = "WARNING"
SEV_BLOCKING = "BLOCKING"


# Labels emitted under pause
LABEL_READY_REVIEW_PAUSED = "READY_FOR_REVIEW_PAUSED"
LABEL_PROMOTION_PAUSED_EDGE_DECAY = "PROMOTION_PAUSED_EDGE_DECAY"
LABEL_STRUCTURAL_REVIEW_REQUIRED = "STRUCTURAL_REVIEW_REQUIRED"


@dataclass
class PauseState:
    active: bool
    severity: str             # INFO | WARNING | BLOCKING
    triggered_by: str         # edge_trajectory | tail_risk | ...
    reason: str
    clear_condition: str
    label_override: str | None
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "active": bool(self.active),
            "severity": self.severity,
            "triggered_by": self.triggered_by,
            "reason": self.reason,
            "clear_condition": self.clear_condition,
            "label_override": self.label_override,
            "metrics": dict(self.metrics),
            "advisory_only": True,
        }


def _trends_from_edge_blocks(blocks: dict) -> tuple[str | None, str | None,
                                                              str | None,
                                                              float | None,
                                                              float | None]:
    """Extract (trend_30, trend_60, trend_90, recent_30_bps, delta_30_bps)
    from a dict like {"30d": {...}, "60d": {...}, "90d": {...}}.
    """
    def _get(w):
        b = blocks.get(w) or {}
        return (b.get("trend"),
                b.get("recent_mean_edge_bps"),
                b.get("delta_bps"))
    t30, recent_30, delta_30 = _get("30d")
    t60, _, _ = _get("60d")
    t90, _, _ = _get("90d")
    return t30, t60, t90, recent_30, delta_30


def _collect_multi_window(rows: list[dict]) -> dict:
    """Compute 30/60/90d edge_trajectory blocks for the pause evaluator."""
    from apps.api.src.research.engine_b_analytics import edge_trajectory
    return {
        "30d": edge_trajectory(rows, window_days=30),
        "60d": edge_trajectory(rows, window_days=60),
        "90d": edge_trajectory(rows, window_days=90),
    }


def evaluate_pause(
    rows: list[dict],
    *,
    previous_pause_states: Sequence[bool] | None = None,
    edge_blocks: dict | None = None,
    delta_blocking_bps: float = EDGE_BLOCKING_DELTA_BPS,
) -> PauseState:
    """Compute pause state from edge trajectory + recent snapshot history.

    `previous_pause_states` is a chronological list of `pause.active`
    flags from prior decision snapshots (most recent LAST). Used to
    enforce the "2 consecutive healthy snapshots" clear condition.

    `edge_blocks` (optional) lets caller inject precomputed multi-window
    blocks; otherwise computed from `rows`.
    """
    blocks = edge_blocks or _collect_multi_window(rows)
    t30, t60, t90, recent_30, delta_30 = _trends_from_edge_blocks(blocks)

    metrics = {"edge_blocks": {k: v for k, v in blocks.items()}}

    # If multi-window data is insufficient, return INFO/no-pause.
    if t30 in (None, "INSUFFICIENT"):
        return PauseState(
            active=False, severity=SEV_INFO,
            triggered_by="edge_trajectory",
            reason="insufficient edge data",
            clear_condition=("30d edge non-declining AND recent_mean_edge "
                              "> 0 for 2 consecutive snapshots"),
            label_override=None,
            metrics=metrics,
        )

    # Healthy: 30d not declining and recent edge positive.
    healthy_now = (t30 != "DECLINING" and recent_30 is not None
                     and recent_30 > 0)

    # ---- Pause activation rules (from spec) ----

    # BLOCKING: 30d declining AND recent < 0 AND delta ≤ -10 bps
    if (t30 == "DECLINING" and recent_30 is not None and recent_30 < 0
            and delta_30 is not None and delta_30 <= delta_blocking_bps):
        # Strengthen further if 60d also declining
        if t60 == "DECLINING" and t90 == "DECLINING":
            return PauseState(
                active=True, severity=SEV_BLOCKING,
                triggered_by="edge_trajectory",
                reason=(f"Edge declining across 30d/60d/90d windows. "
                         f"30d edge {recent_30:+.2f} bps · "
                         f"delta {delta_30:+.2f} bps."),
                clear_condition=("30d edge_trajectory != DECLINING AND "
                                   "recent_mean_edge_bps > 0 for 2 "
                                   "consecutive decision snapshots"),
                label_override=LABEL_STRUCTURAL_REVIEW_REQUIRED,
                metrics=metrics,
            )
        if t60 == "DECLINING":
            return PauseState(
                active=True, severity=SEV_BLOCKING,
                triggered_by="edge_trajectory",
                reason=(f"Edge declining at 30d AND 60d. "
                         f"30d edge {recent_30:+.2f} bps · "
                         f"delta {delta_30:+.2f} bps."),
                clear_condition=("30d edge_trajectory != DECLINING AND "
                                   "recent_mean_edge_bps > 0 for 2 "
                                   "consecutive decision snapshots"),
                label_override=LABEL_PROMOTION_PAUSED_EDGE_DECAY,
                metrics=metrics,
            )
        # 30d declining + neg + big drop, but 60d/90d intact → still
        # blocking by primary spec rule.
        return PauseState(
            active=True, severity=SEV_BLOCKING,
            triggered_by="edge_trajectory",
            reason=(f"30d edge sharply declining: {recent_30:+.2f} bps "
                     f"(delta {delta_30:+.2f} bps ≤ "
                     f"{delta_blocking_bps:.1f}). "
                     f"Longer windows still positive."),
            clear_condition=("30d edge_trajectory != DECLINING AND "
                               "recent_mean_edge_bps > 0 for 2 "
                               "consecutive decision snapshots"),
            label_override=LABEL_PROMOTION_PAUSED_EDGE_DECAY,
            metrics=metrics,
        )

    # WARNING: 30d declining BUT 60d or 90d positive
    if t30 == "DECLINING":
        longer_intact = (t60 in ("STABLE", "IMPROVING")
                            or t90 in ("STABLE", "IMPROVING"))
        if longer_intact:
            return PauseState(
                active=True, severity=SEV_WARNING,
                triggered_by="edge_trajectory",
                reason=(f"30d edge_trajectory DECLINING ({recent_30} bps), "
                         f"longer windows still intact "
                         f"(60d={t60}, 90d={t90})."),
                clear_condition=("30d edge_trajectory != DECLINING AND "
                                   "recent_mean_edge_bps > 0 for 2 "
                                   "consecutive decision snapshots"),
                label_override=LABEL_READY_REVIEW_PAUSED,
                metrics=metrics,
            )
        # 30d declining but moderate (delta > -10), not BLOCKING — WARNING
        return PauseState(
            active=True, severity=SEV_WARNING,
            triggered_by="edge_trajectory",
            reason=(f"30d edge declining ({recent_30} bps, "
                     f"delta {delta_30} bps) but not severe."),
            clear_condition=("30d edge_trajectory != DECLINING AND "
                               "recent_mean_edge_bps > 0 for 2 "
                               "consecutive decision snapshots"),
            label_override=LABEL_READY_REVIEW_PAUSED,
            metrics=metrics,
        )

    # ---- Clear condition: require 2 consecutive healthy snapshots ----
    # If currently healthy AND last K snapshots had pause active, we
    # remain in WARNING state until K consecutive healthy snapshots
    # observed.
    if healthy_now and previous_pause_states:
        # Count trailing consecutive 'active=True' from prior snapshots
        trailing_active = 0
        for s in reversed(list(previous_pause_states)):
            if s:
                trailing_active += 1
            else:
                break
        if trailing_active >= 1 and \
            len(previous_pause_states) < PAUSE_CLEAR_CONSECUTIVE - 1 + 1:
            # We've just turned healthy; still need at least
            # PAUSE_CLEAR_CONSECUTIVE-1 more snapshots clean to fully clear
            return PauseState(
                active=True, severity=SEV_WARNING,
                triggered_by="edge_trajectory",
                reason=(f"30d edge healthy ({recent_30} bps, {t30}) but "
                         f"awaiting {PAUSE_CLEAR_CONSECUTIVE-1} more "
                         f"healthy snapshots to clear pause."),
                clear_condition=(f"{PAUSE_CLEAR_CONSECUTIVE} consecutive "
                                   f"healthy snapshots required"),
                label_override=LABEL_READY_REVIEW_PAUSED,
                metrics={**metrics,
                          "trailing_active_snapshots": trailing_active},
            )

    # All clear
    return PauseState(
        active=False, severity=SEV_INFO,
        triggered_by="edge_trajectory",
        reason="edge healthy across windows",
        clear_condition="—",
        label_override=None,
        metrics=metrics,
    )
