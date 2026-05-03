"""ML-6 — Promotion Guard.

Deterministic state machine. RECOMMENDS mode transitions. Never flips
`ML_HYBRID_MODE` automatically. Operator must approve.

Inputs are window results from hybrid_monitor. Output is a state string
plus a list of blockers and a plain-text recommendation.

States:
  NOT_READY_NO_ML
  NOT_READY_INSUFFICIENT_ADVICE
  NOT_READY_INSUFFICIENT_OUTCOMES
  NOT_READY_POOR_CALIBRATION
  NOT_READY_BELOW_BASELINE
  NOT_READY_HIGH_FALSE_AVOID
  ADVISORY_HEALTHY
  READY_FOR_PAPER_REDUCE
  PAPER_REDUCE_PAUSED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PromotionThresholds:
    min_advice: int = 20
    min_outcomes: int = 20
    max_ece: float = 0.10
    min_delta_sharpe: float = 0.00
    max_false_avoid_rate: float = 0.35
    required_healthy_days: int = 7
    require_operator_approval: bool = True
    max_missed_winner_rate: float = 0.50

    @classmethod
    def from_settings(cls, settings: Any) -> "PromotionThresholds":
        g = lambda k, d: getattr(settings, k, d)   # noqa: E731
        return cls(
            min_advice=int(g("ML_PROMOTION_MIN_ADVICE", 20)),
            min_outcomes=int(g("ML_PROMOTION_MIN_OUTCOMES", 20)),
            max_ece=float(g("ML_PROMOTION_MAX_ECE", 0.10)),
            min_delta_sharpe=float(
                g("ML_PROMOTION_MIN_DELTA_SHARPE", 0.00),
            ),
            max_false_avoid_rate=float(
                g("ML_PROMOTION_MAX_FALSE_AVOID_RATE", 0.35),
            ),
            required_healthy_days=int(
                g("ML_PROMOTION_REQUIRED_HEALTHY_DAYS", 7),
            ),
            require_operator_approval=bool(
                g("ML_PROMOTION_REQUIRE_OPERATOR_APPROVAL", True),
            ),
            max_missed_winner_rate=float(
                g("ML_PROMOTION_MAX_MISSED_WINNER_RATE", 0.50),
            ),
        )


@dataclass
class PromotionDecision:
    state: str
    current_mode: str
    blockers: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    recommendation: str = ""
    operator_approval_required: bool = True
    healthy_day_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "current_mode": self.current_mode,
            "blockers": list(self.blockers),
            "reasons":  list(self.reasons),
            "recommendation": self.recommendation,
            "operator_approval_required": bool(
                self.operator_approval_required,
            ),
            "healthy_day_count": self.healthy_day_count,
        }


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------

def _per_window_blockers(
    res: dict[str, Any], th: PromotionThresholds,
) -> list[str]:
    """Return blocker strings for one window result dict."""
    blk: list[str] = []
    n_adv = int(res.get("ml_advice_count") or 0)
    n_det = int(res.get("deterministic_trades") or 0)
    ece   = res.get("calibration_ece")
    dsh   = res.get("delta_sharpe_vs_deterministic")
    fa    = res.get("false_avoid_rate")
    mw    = res.get("missed_winner_rate")
    status = str(res.get("model_status") or "")

    if n_adv < th.min_advice:
        blk.append(f"insufficient_advice:{n_adv}")
    if n_det < th.min_outcomes:
        blk.append(f"insufficient_outcomes:{n_det}")
    if ece is None:
        blk.append("no_ece")
    elif float(ece) >= th.max_ece:
        blk.append(f"poor_calibration:{float(ece):.3f}")
    if dsh is None or float(dsh) < th.min_delta_sharpe:
        blk.append(
            f"below_delta_sharpe:{float(dsh) if dsh is not None else 'none'}",
        )
    if fa is not None and float(fa) > th.max_false_avoid_rate:
        blk.append(f"high_false_avoid:{float(fa):.2f}")
    if (mw is not None and float(mw) > th.max_missed_winner_rate):
        blk.append(f"high_missed_winner:{float(mw):.2f}")
    if status not in {"SHADOW_OUTPERFORMING"}:
        # advisory tolerates TRAINED_SHADOW; paper_reduce needs
        # SHADOW_OUTPERFORMING — caller decides which list to trust.
        blk.append(f"model_status_not_outperforming:{status or 'none'}")
    return blk


def _healthy_days_from_history(
    snapshots: list[dict[str, Any]], th: PromotionThresholds,
) -> int:
    """Count trailing consecutive days where 7d-window snapshot had no
    critical blockers. Expects snapshots sorted DESC by as_of_date."""
    count = 0
    for s in snapshots:
        if int(s.get("window_days") or 0) != 7:
            continue
        blk = _per_window_blockers(s, th)
        critical = [b for b in blk if not b.startswith(
            ("insufficient_advice", "insufficient_outcomes"),
        )]
        if critical:
            break
        count += 1
    return count


# ---------------------------------------------------------------------------
# Core decision
# ---------------------------------------------------------------------------

def evaluate_promotion(
    *,
    current_mode: str,
    window_results: dict[int, dict[str, Any]],
    recent_snapshots: list[dict[str, Any]] | None = None,
    thresholds: PromotionThresholds | None = None,
    has_ml_predictions: bool = True,
) -> PromotionDecision:
    """Determine promotion state. Does NOT mutate mode.

    `window_results` keyed by window_days (7, 14, 30). Each is a dict
    matching HybridWindowResult.to_dict().
    `recent_snapshots` is an optional chronological-desc list of persisted
    snapshot rows — used to count consecutive healthy days.
    """
    th = thresholds or PromotionThresholds()
    mode = str(current_mode or "advisory")

    if not has_ml_predictions or not window_results:
        return PromotionDecision(
            state="NOT_READY_NO_ML",
            current_mode=mode,
            blockers=["no_ml_predictions"],
            reasons=["ML shadow has no usable predictions yet."],
            recommendation=(
                "Run nightly ML shadow job. Accumulate predictions before "
                "promotion can be evaluated."
            ),
            operator_approval_required=th.require_operator_approval,
            healthy_day_count=0,
        )

    # Primary window for gating is 14d (medium-term stability). 7d is used
    # for healthy-day counting, 30d for long-term confirmation.
    r14 = window_results.get(14) or window_results.get(30) \
          or window_results.get(7)
    r30 = window_results.get(30)
    assert r14 is not None

    blockers_14 = _per_window_blockers(r14, th)
    blockers_30 = _per_window_blockers(r30, th) if r30 else []

    # NOT_READY short-circuits — single strongest blocker wins
    if any(b.startswith("insufficient_advice") for b in blockers_14):
        return _build(
            state="NOT_READY_INSUFFICIENT_ADVICE",
            mode=mode, blockers=blockers_14, th=th,
            reason="Fewer than the required ML predictions in window.",
            healthy_day_count=0,
        )
    if any(b.startswith("insufficient_outcomes") for b in blockers_14):
        return _build(
            state="NOT_READY_INSUFFICIENT_OUTCOMES",
            mode=mode, blockers=blockers_14, th=th,
            reason="Fewer than the required closed outcomes in window.",
            healthy_day_count=0,
        )
    if any(b.startswith("poor_calibration") for b in blockers_14):
        return _build(
            state="NOT_READY_POOR_CALIBRATION",
            mode=mode, blockers=blockers_14, th=th,
            reason="Model ECE is above the configured threshold.",
            healthy_day_count=0,
        )
    if any(b.startswith("below_delta_sharpe") for b in blockers_14) \
       or any(b.startswith("model_status_not_outperforming")
              for b in blockers_14):
        return _build(
            state="NOT_READY_BELOW_BASELINE",
            mode=mode, blockers=blockers_14, th=th,
            reason="Counterfactual Sharpe not improving, or model not "
                   "outperforming baseline.",
            healthy_day_count=0,
        )
    if any(b.startswith("high_false_avoid") for b in blockers_14):
        return _build(
            state="NOT_READY_HIGH_FALSE_AVOID",
            mode=mode, blockers=blockers_14, th=th,
            reason="ML is warning on too many eventual winners.",
            healthy_day_count=0,
        )

    # Advisory health passes all 14d gates. Check 30d if present.
    days = _healthy_days_from_history(recent_snapshots or [], th)

    # In paper_reduce mode we watch for degradation.
    if mode == "paper_reduce":
        dsh = r14.get("delta_sharpe_vs_deterministic")
        if dsh is None or float(dsh) < 0:
            return _build(
                state="PAPER_REDUCE_PAUSED",
                mode=mode, blockers=["negative_delta_sharpe_live"], th=th,
                reason="paper_reduce live but ML-applied Sharpe delta is "
                       "negative. Recommend reverting to advisory.",
                healthy_day_count=days,
            )
        return _build(
            state="READY_FOR_PAPER_REDUCE",
            mode=mode, blockers=[], th=th,
            reason="paper_reduce is running cleanly across windows.",
            healthy_day_count=days,
        )

    # Advisory mode — do we have enough consecutive clean days?
    if days < th.required_healthy_days:
        return _build(
            state="ADVISORY_HEALTHY",
            mode=mode,
            blockers=[f"need_more_healthy_days:{days}/"
                       f"{th.required_healthy_days}"],
            th=th,
            reason="Advisory looks healthy in current window, but needs "
                    f"more consecutive healthy days "
                    f"({days}/{th.required_healthy_days}).",
            healthy_day_count=days,
        )

    # Long-window confirmation
    if r30:
        if any(b.startswith(("poor_calibration", "below_delta_sharpe",
                                "model_status_not_outperforming",
                                "high_false_avoid"))
                for b in blockers_30):
            return _build(
                state="ADVISORY_HEALTHY",
                mode=mode, blockers=blockers_30, th=th,
                reason="30d window still shows concerns; keep advisory.",
                healthy_day_count=days,
            )

    return _build(
        state="READY_FOR_PAPER_REDUCE",
        mode=mode, blockers=[], th=th,
        reason=("All gates clean for required healthy days. Operator can "
                 "promote to paper_reduce; approval remains required."),
        healthy_day_count=days,
    )


def _build(
    *, state: str, mode: str, blockers: list[str],
    th: PromotionThresholds, reason: str,
    healthy_day_count: int | None,
) -> PromotionDecision:
    return PromotionDecision(
        state=state,
        current_mode=mode,
        blockers=list(blockers),
        reasons=[reason],
        recommendation=_recommendation_from_state(state, mode),
        operator_approval_required=bool(th.require_operator_approval),
        healthy_day_count=healthy_day_count,
    )


def _recommendation_from_state(state: str, mode: str) -> str:
    if state == "NOT_READY_NO_ML":
        return "Keep advisory mode. ML has no usable predictions."
    if state == "NOT_READY_INSUFFICIENT_ADVICE":
        return "Keep advisory mode. Need more ML predictions."
    if state == "NOT_READY_INSUFFICIENT_OUTCOMES":
        return "Keep advisory mode. Need more closed outcomes."
    if state == "NOT_READY_POOR_CALIBRATION":
        return "Keep advisory mode. Model calibration is poor."
    if state == "NOT_READY_BELOW_BASELINE":
        return "Keep advisory mode. ML is not beating baseline."
    if state == "NOT_READY_HIGH_FALSE_AVOID":
        return ("Keep advisory mode. ML warns on too many winners — review "
                 "feature set.")
    if state == "ADVISORY_HEALTHY":
        return ("Advisory looks healthy. Need more consecutive healthy "
                 "days before paper_reduce trial.")
    if state == "READY_FOR_PAPER_REDUCE":
        if mode == "advisory":
            return ("Ready for paper_reduce trial. Operator approval "
                     "required before switching.")
        return "paper_reduce running cleanly. Keep monitoring."
    if state == "PAPER_REDUCE_PAUSED":
        return ("paper_reduce appears to hurt results. Recommend reverting "
                 "to advisory.")
    return "Insufficient evidence."
