"""ML-5 — Gated Hybrid Advisor policy.

Pure deterministic function. No learning, no state, no randomness.

Inputs: runtime ML signal + current paper multipliers + risk context.
Output: ml_shadow_multiplier ∈ [MIN_MULTIPLIER, 1.0] + snapshot.

Hard invariants:
  • never > 1.0
  • never below ML_HYBRID_MIN_MULTIPLIER
  • defaults to 1.0 if ML unavailable or any gate fails
  • cannot increase size, cannot bypass engines/gates
  • block mapping: only emitted when ALLOW_BLOCK=true, otherwise
    downgraded to reduce_size automatically
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Config shape (pulled from settings; policy accepts a plain dict so it is
# easy to unit-test without loading the app)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HybridConfig:
    enabled: bool = False
    mode: str = "advisory"            # advisory | paper_reduce
    min_confidence: float = 0.65
    require_calibration: bool = True
    require_baseline_beat: bool = True
    max_stale_days: int = 7
    min_data_confidence: float = 0.70
    allow_block: bool = False
    min_multiplier: float = 0.50

    @classmethod
    def from_settings(cls, settings: Any) -> "HybridConfig":
        g = lambda k, d: getattr(settings, k, d)   # noqa: E731
        return cls(
            enabled=bool(g("ML_HYBRID_ENABLED", False)),
            mode=str(g("ML_HYBRID_MODE", "advisory")),
            min_confidence=float(g("ML_HYBRID_MIN_CONFIDENCE", 0.65)),
            require_calibration=bool(
                g("ML_HYBRID_REQUIRE_CALIBRATION", True),
            ),
            require_baseline_beat=bool(
                g("ML_HYBRID_REQUIRE_BASELINE_BEAT", True),
            ),
            max_stale_days=int(g("ML_HYBRID_MAX_STALE_DAYS", 7)),
            min_data_confidence=float(
                g("ML_HYBRID_MIN_DATA_CONFIDENCE", 0.70),
            ),
            allow_block=bool(g("ML_HYBRID_ALLOW_BLOCK", False)),
            min_multiplier=float(g("ML_HYBRID_MIN_MULTIPLIER", 0.50)),
        )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class HybridResult:
    enabled: bool
    applied: bool                 # mode=paper_reduce AND mult < 1.0
    multiplier: float             # ALWAYS clamped to [min, 1.0]
    action: str                   # none|annotate|reduce_size|would_block
    reason: str
    gates_blocking: list[str] = field(default_factory=list)
    snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ml_hybrid_enabled": self.enabled,
            "ml_shadow_multiplier": round(self.multiplier, 4),
            "ml_hybrid_action": self.action,
            "ml_hybrid_reason": self.reason,
            "ml_hybrid_applied": self.applied,
            "ml_hybrid_gates_blocking": list(self.gates_blocking),
            "ml_hybrid_snapshot": dict(self.snapshot),
        }


# ---------------------------------------------------------------------------
# Gating — hard no-op conditions
# ---------------------------------------------------------------------------

def _gate_check(
    *, ml: dict[str, Any], cfg: HybridConfig,
    data_quality: dict[str, Any] | None,
) -> list[str]:
    blocking: list[str] = []
    if not cfg.enabled:
        blocking.append("disabled")
    if not ml.get("available"):
        blocking.append(
            f"ml_unavailable:{(ml.get('reason_codes') or ['unknown'])[0]}",
        )
    status = str(ml.get("status") or "")
    if status not in {"SHADOW_OUTPERFORMING", "TRAINED_SHADOW"}:
        blocking.append(f"bad_status:{status or 'none'}")
    if cfg.mode == "paper_reduce" and status != "SHADOW_OUTPERFORMING":
        blocking.append("paper_reduce_requires_outperforming")
    if cfg.require_calibration and not bool(ml.get("calibration_ok")):
        blocking.append("poor_calibration")
    if cfg.require_baseline_beat and not bool(ml.get("beats_baseline")):
        blocking.append("below_baseline")
    age = ml.get("model_age_days")
    if age is not None and int(age) > int(cfg.max_stale_days):
        blocking.append(f"stale:{age}d")
    mlconf = ml.get("ml_confidence")
    if mlconf is None or float(mlconf) < float(cfg.min_confidence):
        blocking.append("low_ml_confidence")
    dq = (data_quality or {}).get("confidence")
    if dq is None or float(dq) < float(cfg.min_data_confidence):
        blocking.append("low_data_confidence")
    # leakage report check — dataset builder marks issues under
    # ml_model_run.leakage_report; loader surfaces status, so we only
    # hard-block when status indicates leakage skip
    if status == "SKIPPED_LEAKAGE_RISK":
        blocking.append("leakage_risk")
    return blocking


# ---------------------------------------------------------------------------
# Action → proposed multiplier (pre-compound safety)
# ---------------------------------------------------------------------------

def _proposed_from_action(
    ml_action: str | None, ml_confidence: float | None,
    *, catalyst_risk: float | None,
) -> tuple[float, str]:
    """Return (multiplier_proposal, action_label)."""
    act = (ml_action or "").lower()
    conf = float(ml_confidence or 0.0)
    # needs_more_data → no reduction, just annotate
    if act == "needs_more_data":
        return 1.0, "annotate"
    if act == "accept":
        return 1.0, "none"
    if act == "reduce":
        # Only reduce when high-confidence reduce
        return (0.8 if conf >= 0.65 else 1.0), (
            "reduce_size" if conf >= 0.65 else "annotate"
        )
    if act == "avoid":
        # High-catalyst + avoid → stronger cut, else 0.5
        if catalyst_risk is not None and float(catalyst_risk) >= 0.6:
            return 0.5, "would_block"    # mapped down if block disabled
        return (0.5 if conf >= 0.65 else 0.8), "reduce_size"
    return 1.0, "none"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def evaluate_hybrid(
    *,
    ml_signal: dict[str, Any],
    cfg: HybridConfig,
    current_paper_mult: float,
    data_quality: dict[str, Any] | None = None,
    catalyst: dict[str, Any] | None = None,
    similarity: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> HybridResult:
    """Resolve final ML hybrid multiplier + action.

    Hard contract: returns multiplier ∈ [cfg.min_multiplier, 1.0].
    """
    blocking = _gate_check(
        ml=ml_signal, cfg=cfg, data_quality=data_quality,
    )
    snapshot_base = {
        "mode":     cfg.mode,
        "min_conf": cfg.min_confidence,
        "max_stale_days": cfg.max_stale_days,
        "allow_block":    cfg.allow_block,
        "min_multiplier": cfg.min_multiplier,
        "ml_action": ml_signal.get("ml_action"),
        "ml_confidence": ml_signal.get("ml_confidence"),
        "ml_score":      ml_signal.get("ml_score"),
        "status": ml_signal.get("status"),
        "model_run_id": ml_signal.get("model_run_id"),
        "model_age_days": ml_signal.get("model_age_days"),
        "calibration_ok": ml_signal.get("calibration_ok"),
        "baseline_delta": ml_signal.get("baseline_delta"),
        "baseline_winner": ml_signal.get("baseline_winner"),
        "gates_blocking": list(blocking),
    }

    # --- Any gate blocks → no-op multiplier ---
    if blocking:
        return HybridResult(
            enabled=bool(cfg.enabled),
            applied=False,
            multiplier=1.0,
            action="none",
            reason="gated_off: " + ", ".join(blocking[:4]),
            gates_blocking=blocking,
            snapshot=snapshot_base,
        )

    # --- Proposed multiplier from ml_action ---
    cat_risk = None
    if isinstance(catalyst, dict):
        cr = catalyst.get("event_risk_score")
        if isinstance(cr, (int, float)):
            cat_risk = float(cr)

    proposed, action = _proposed_from_action(
        ml_signal.get("ml_action"),
        float(ml_signal.get("ml_confidence") or 0.0),
        catalyst_risk=cat_risk,
    )
    # Block action policy
    if action == "would_block" and not cfg.allow_block:
        action = "reduce_size"       # downgrade block → reduce

    # Clamp — never > 1.0, never < min_multiplier
    clamped = max(cfg.min_multiplier, min(1.0, float(proposed)))

    # Advisory mode never applies reduction to size (annotate only)
    applied = cfg.mode == "paper_reduce" and clamped < 1.0
    applied_multiplier = clamped if applied else 1.0

    # --- Double-punish guard ---
    # If similarity already reduced (similarity_multiplier < 0.7), cap
    # the compounded effect so the combined reduction doesn't fall below
    # ML's own floor. We enforce this by clamping the ML mult upward so
    # that (sim × ml) ≥ min_multiplier.
    if similarity and applied:
        sim_m = float(similarity.get("multiplier") or 1.0)
        if sim_m > 0:
            max_allowed = 1.0
            min_product = cfg.min_multiplier
            # effective ml mult must keep (sim_m × ml_m) ≥ min_product
            lower_bound = min_product / sim_m
            if applied_multiplier < lower_bound:
                applied_multiplier = min(max_allowed, lower_bound)

    reason = _reason_from(action, ml_signal)
    snapshot = dict(snapshot_base)
    snapshot["proposed_multiplier"] = round(float(proposed), 4)
    snapshot["clamped_multiplier"]  = round(float(clamped), 4)
    snapshot["applied_multiplier"]  = round(float(applied_multiplier), 4)
    if similarity:
        snapshot["similarity_seen"] = {
            "matched":   bool(similarity.get("matched")),
            "multiplier": float(similarity.get("multiplier") or 1.0),
            "reason":     similarity.get("reason"),
        }
    if catalyst is not None:
        snapshot["catalyst_risk"] = cat_risk
    if context is not None:
        snapshot["context_regime"] = context.get("regime")

    return HybridResult(
        enabled=bool(cfg.enabled),
        applied=bool(applied),
        multiplier=float(applied_multiplier),
        action=action,
        reason=reason,
        gates_blocking=blocking,
        snapshot=snapshot,
    )


def _reason_from(action: str, ml: dict[str, Any]) -> str:
    ma = (ml.get("ml_action") or "").lower() or "none"
    conf = ml.get("ml_confidence")
    cstr = f"{float(conf):.0%}" if isinstance(conf, (int, float)) else "—"
    if action == "none":
        return f"ML accept ({cstr} conf) — no adjustment"
    if action == "annotate":
        return f"ML {ma} ({cstr} conf) — logged only"
    if action == "reduce_size":
        return f"ML {ma} ({cstr} conf) — paper size reduced"
    if action == "would_block":
        return f"ML avoid ({cstr} conf) — would block, blocking disabled"
    return f"ML {ma}"
