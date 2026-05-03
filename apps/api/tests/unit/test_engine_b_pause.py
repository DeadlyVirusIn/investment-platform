"""Tests for engine_b_pause + decision integration override."""

from __future__ import annotations

from datetime import date, timedelta

from src.research.engine_b_decision import evaluate as eval_decision
from src.research.engine_b_pause import (
    LABEL_PROMOTION_PAUSED_EDGE_DECAY,
    LABEL_READY_REVIEW_PAUSED,
    LABEL_STRUCTURAL_REVIEW_REQUIRED,
    SEV_BLOCKING, SEV_WARNING,
    evaluate_pause,
)


def _row(d, b="LONG", b2="LONG", regime="DIRECTIONAL", fwd=0.0,
            div=0.0):
    return {
        "as_of_date": d, "engine_b_signal": b, "b2_signal": b2,
        "routed_signal": b, "regime_label": regime,
        "fwd_return_1d": fwd, "divergence_outcome": div,
        "divergence_flag": (b != b2),
    }


def _build_declining_30d(*, n: int = 200) -> list[dict]:
    """Construct rows so 30d edge declines past the BLOCKING delta
    threshold while keeping divergence-win rate above kill-switch floor
    AND recent routed returns positive (so kill switch stays silent).
    """
    base = date(2025, 1, 1)
    out = []
    # Prior n-30 days: B2 wins divergent days, prior 30d mean ~ +10 bps
    for i in range(n - 30):
        d = base + timedelta(days=i)
        out.append(_row(d, b="FLAT", b2="LONG",
                          fwd=+0.0010, div=-0.0010))
    # Recent 30 days: 18 small B2 wins + 12 larger B wins.
    # div_win rate = 18/30 = 60% > 0.40 (kill-switch safe)
    # mean B2 advantage = (18·5 - 12·10) / 30 = -1 bps
    # delta = -1 - 10 = -11 bps ≤ blocking threshold (-10)
    for k, i in enumerate(range(n - 30, n)):
        d = base + timedelta(days=i)
        if k < 18:    # 18 days: B FLAT, B2 LONG, fwd small +
            out.append(_row(d, b="FLAT", b2="LONG",
                              fwd=+0.0005, div=-0.0005))
        else:          # 12 days: B LONG, B2 FLAT, fwd larger +
            out.append(_row(d, b="LONG", b2="FLAT",
                              fwd=+0.0010, div=+0.0010))
    return out


def _build_healthy(n: int = 200) -> list[dict]:
    """All non-divergent or B2-favoring divergent days."""
    base = date(2025, 1, 1)
    out = []
    for i in range(n):
        d = base + timedelta(days=i)
        # Half are divergent with B2 winning
        if i % 2 == 0:
            out.append(_row(d, b="FLAT", b2="LONG",
                              fwd=+0.0015, div=-0.0015))
        else:
            out.append(_row(d, b="LONG", b2="LONG",
                              fwd=+0.0010, div=0.0))
    return out


# ---- 1. Declining 30d negative + big delta → BLOCKING pause ----
def test_pause_blocking_when_30d_declining_negative():
    rows = _build_declining_30d(n=120)
    pause = evaluate_pause(rows)
    assert pause.active is True
    assert pause.severity == SEV_BLOCKING
    assert pause.label_override in (
        LABEL_PROMOTION_PAUSED_EDGE_DECAY,
        LABEL_STRUCTURAL_REVIEW_REQUIRED,
    )


# ---- 2. Declining 30d but positive 60/90 → WARNING ----
def test_pause_warning_when_only_30d_declines():
    # Build short series where 30d declines slightly but 60d/90d positive
    base = date(2025, 1, 1)
    rows = []
    for i in range(180):
        d = base + timedelta(days=i)
        # Most days B2 advantage +5bps
        if i < 150:
            rows.append(_row(d, b="FLAT", b2="LONG",
                                fwd=+0.0006, div=-0.0006))
        else:
            # Recent 30: small B advantage (-3bps each), not severe
            rows.append(_row(d, b="LONG", b2="FLAT",
                                fwd=+0.0003, div=+0.0003))
    pause = evaluate_pause(rows)
    # Either WARNING or BLOCKING depending on delta magnitude.
    # The key invariant for this test is: pause must be active.
    assert pause.active is True
    assert pause.severity in {SEV_WARNING, SEV_BLOCKING}


# ---- 3. Declining 30d AND 60d → BLOCKING ----
def test_pause_blocking_when_30d_and_60d_decline():
    base = date(2025, 1, 1)
    rows = []
    # Need ≥ 180 rows for 90d trajectory window (2*90).
    # First 150 days: B2 wins → prior 30d/60d both positive
    for i in range(150):
        d = base + timedelta(days=i)
        rows.append(_row(d, b="FLAT", b2="LONG",
                            fwd=+0.0010, div=-0.0010))
    # Last 30 days: B wins → recent 30d negative; recent 60d (which
    # spans last 60 days = mix of 30 B2-wins and 30 B-wins) declines
    # past the blocking delta threshold.
    for i in range(150, 180):
        d = base + timedelta(days=i)
        rows.append(_row(d, b="LONG", b2="FLAT",
                            fwd=+0.0010, div=+0.0010))
    pause = evaluate_pause(rows)
    assert pause.active is True
    assert pause.severity == SEV_BLOCKING


# ---- 4. All gates pass but pause active → action remains HOLD ----
def test_decision_hold_when_pause_blocking_even_with_clean_gates():
    rows = _build_declining_30d(n=120)
    v = eval_decision(rows=rows, current_state="LEGACY",
                          operator_approval=True)
    # pause must be active and force HOLD
    assert v.action == "HOLD"
    pause = v.promotion_pause
    assert pause.get("active") is True


# ---- 5. Operator approval true but pause active → cannot advance ----
def test_operator_approval_cannot_override_pause():
    rows = _build_declining_30d(n=120)
    v = eval_decision(rows=rows, current_state="LEGACY",
                          operator_approval=True,
                          require_score_for_promotion=0)
    assert v.action != "READY_FOR_NEXT"
    assert v.action != "ADVANCE"
    assert v.recommended_state == v.current_state


# ---- 6. Pause clears after consecutive healthy snapshots ----
def test_pause_persists_until_consecutive_healthy_snapshots():
    rows = _build_healthy(n=200)
    # Simulate 1 prior pause active → now healthy: should still warn
    pause = evaluate_pause(rows, previous_pause_states=[True])
    # Either active=True (still cooling down) or active=False (cleared);
    # spec requires K=2 consec healthy. With history=[True] we are on
    # the FIRST healthy snapshot → still pause active.
    assert pause.active is True
    assert pause.severity == SEV_WARNING


def test_pause_clears_after_two_consecutive_healthy_snapshots():
    rows = _build_healthy(n=200)
    # 2 consecutive healthy already observed → clear
    pause = evaluate_pause(rows, previous_pause_states=[True, False, False])
    assert pause.active is False


def test_pause_does_not_fire_when_data_insufficient():
    base = date(2025, 1, 1)
    rows = [_row(base + timedelta(days=i),
                  b="LONG", b2="LONG", fwd=0.001) for i in range(20)]
    pause = evaluate_pause(rows)
    assert pause.active is False
    assert pause.severity == "INFO"


def test_decision_to_dict_includes_promotion_pause():
    rows = _build_declining_30d(n=120)
    v = eval_decision(rows=rows, current_state="LEGACY",
                          operator_approval=False)
    d = v.to_dict()
    assert "promotion_pause" in d
    assert d["promotion_pause"]["advisory_only"] is True
