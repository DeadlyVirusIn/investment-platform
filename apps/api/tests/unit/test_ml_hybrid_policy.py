"""ML-5 — Gated Hybrid Advisor policy unit tests.

Pure function tests — no DB, no config. Policy invariants:
  • never > 1.0
  • never < ML_HYBRID_MIN_MULTIPLIER
  • defaults to 1.0 under any gate failure
  • block → reduce_size when ALLOW_BLOCK=false
  • advisory mode never applies a reduction to size (annotate only)
  • never imported from real-money code path
"""

from __future__ import annotations

from apps.api.src.ml.shadow.hybrid_policy import (
    HybridConfig, evaluate_hybrid,
)


def _cfg(**over):
    base = dict(
        enabled=True, mode="paper_reduce",
        min_confidence=0.65, require_calibration=True,
        require_baseline_beat=True, max_stale_days=7,
        min_data_confidence=0.70, allow_block=False,
        min_multiplier=0.50,
    )
    base.update(over)
    return HybridConfig(**base)


def _sig(**over):
    base = dict(
        available=True, ml_score=0.5, ml_confidence=0.8,
        ml_action="reduce",
        model_run_id="r1", status="SHADOW_OUTPERFORMING",
        calibration_ok=True, baseline_delta=0.1,
        baseline_winner="ml", beats_baseline=True,
        stale=False, model_age_days=1, reason_codes=[],
        source="ml_shadow_prediction",
    )
    base.update(over)
    return base


def _dq(conf=0.9):
    return {"confidence": conf}


# ---------------------------------------------------------------------------
# Gate failures → multiplier 1.0
# ---------------------------------------------------------------------------

def test_ml_disabled_returns_1():
    r = evaluate_hybrid(
        ml_signal=_sig(), cfg=_cfg(enabled=False),
        current_paper_mult=1.0, data_quality=_dq(),
    )
    assert r.multiplier == 1.0
    assert r.applied is False
    assert "disabled" in r.gates_blocking


def test_ml_unavailable_returns_1():
    r = evaluate_hybrid(
        ml_signal=_sig(available=False, reason_codes=["no_prediction"]),
        cfg=_cfg(), current_paper_mult=1.0, data_quality=_dq(),
    )
    assert r.multiplier == 1.0


def test_poor_calibration_returns_1():
    r = evaluate_hybrid(
        ml_signal=_sig(calibration_ok=False),
        cfg=_cfg(), current_paper_mult=1.0, data_quality=_dq(),
    )
    assert r.multiplier == 1.0
    assert "poor_calibration" in r.gates_blocking


def test_below_baseline_returns_1():
    r = evaluate_hybrid(
        ml_signal=_sig(beats_baseline=False,
                        baseline_winner="baseline"),
        cfg=_cfg(), current_paper_mult=1.0, data_quality=_dq(),
    )
    assert r.multiplier == 1.0
    assert "below_baseline" in r.gates_blocking


def test_stale_model_returns_1():
    r = evaluate_hybrid(
        ml_signal=_sig(model_age_days=30),
        cfg=_cfg(max_stale_days=7),
        current_paper_mult=1.0, data_quality=_dq(),
    )
    assert r.multiplier == 1.0
    assert any(g.startswith("stale:") for g in r.gates_blocking)


def test_low_ml_confidence_returns_1():
    r = evaluate_hybrid(
        ml_signal=_sig(ml_confidence=0.30),
        cfg=_cfg(), current_paper_mult=1.0, data_quality=_dq(),
    )
    assert r.multiplier == 1.0
    assert "low_ml_confidence" in r.gates_blocking


def test_low_data_confidence_returns_1():
    r = evaluate_hybrid(
        ml_signal=_sig(), cfg=_cfg(),
        current_paper_mult=1.0, data_quality={"confidence": 0.5},
    )
    assert r.multiplier == 1.0
    assert "low_data_confidence" in r.gates_blocking


def test_bad_status_returns_1():
    r = evaluate_hybrid(
        ml_signal=_sig(status="SKIPPED_LEAKAGE_RISK"),
        cfg=_cfg(), current_paper_mult=1.0, data_quality=_dq(),
    )
    assert r.multiplier == 1.0
    assert "leakage_risk" in r.gates_blocking


# ---------------------------------------------------------------------------
# Action → multiplier mapping
# ---------------------------------------------------------------------------

def test_ml_action_reduce_gives_0_8():
    r = evaluate_hybrid(
        ml_signal=_sig(ml_action="reduce", ml_confidence=0.8),
        cfg=_cfg(mode="paper_reduce"),
        current_paper_mult=1.0, data_quality=_dq(),
    )
    assert abs(r.multiplier - 0.8) < 1e-9
    assert r.action == "reduce_size"
    assert r.applied is True


def test_ml_action_avoid_gives_0_5():
    r = evaluate_hybrid(
        ml_signal=_sig(ml_action="avoid", ml_confidence=0.85),
        cfg=_cfg(mode="paper_reduce"),
        current_paper_mult=1.0, data_quality=_dq(),
    )
    assert abs(r.multiplier - 0.5) < 1e-9


def test_ml_action_accept_returns_1():
    r = evaluate_hybrid(
        ml_signal=_sig(ml_action="accept"),
        cfg=_cfg(mode="paper_reduce"),
        current_paper_mult=1.0, data_quality=_dq(),
    )
    assert r.multiplier == 1.0
    assert r.action == "none"


def test_needs_more_data_returns_1_with_annotate():
    r = evaluate_hybrid(
        ml_signal=_sig(ml_action="needs_more_data"),
        cfg=_cfg(mode="paper_reduce"),
        current_paper_mult=1.0, data_quality=_dq(),
    )
    assert r.multiplier == 1.0
    assert r.action == "annotate"


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------

def test_multiplier_never_exceeds_1():
    for act in ["reduce", "avoid", "accept", "needs_more_data"]:
        r = evaluate_hybrid(
            ml_signal=_sig(ml_action=act),
            cfg=_cfg(mode="paper_reduce"),
            current_paper_mult=1.0, data_quality=_dq(),
        )
        assert r.multiplier <= 1.0


def test_multiplier_never_below_floor():
    # Force extreme avoid + high catalyst risk
    r = evaluate_hybrid(
        ml_signal=_sig(ml_action="avoid", ml_confidence=0.99),
        cfg=_cfg(mode="paper_reduce", min_multiplier=0.60),
        current_paper_mult=1.0, data_quality=_dq(),
        catalyst={"event_risk_score": 0.9},
    )
    assert r.multiplier >= 0.60


def test_block_downgrades_to_reduce_when_blocking_disabled():
    r = evaluate_hybrid(
        ml_signal=_sig(ml_action="avoid", ml_confidence=0.9),
        cfg=_cfg(mode="paper_reduce", allow_block=False),
        current_paper_mult=1.0, data_quality=_dq(),
        catalyst={"event_risk_score": 0.8},
    )
    assert r.action == "reduce_size"


def test_block_preserved_when_blocking_allowed():
    r = evaluate_hybrid(
        ml_signal=_sig(ml_action="avoid", ml_confidence=0.9),
        cfg=_cfg(mode="paper_reduce", allow_block=True),
        current_paper_mult=1.0, data_quality=_dq(),
        catalyst={"event_risk_score": 0.8},
    )
    assert r.action == "would_block"


def test_advisory_mode_does_not_apply_reduction():
    # Same ML action 'reduce' but advisory → applied=False, mult=1.0
    r = evaluate_hybrid(
        ml_signal=_sig(ml_action="reduce"),
        cfg=_cfg(mode="advisory"),
        current_paper_mult=1.0, data_quality=_dq(),
    )
    # advisory mode eligibility check still passes on TRAINED_SHADOW
    # but applied_multiplier stays at 1.0
    assert r.applied is False
    assert r.multiplier == 1.0


def test_paper_reduce_requires_outperforming():
    r = evaluate_hybrid(
        ml_signal=_sig(status="TRAINED_SHADOW"),
        cfg=_cfg(mode="paper_reduce"),
        current_paper_mult=1.0, data_quality=_dq(),
    )
    assert r.multiplier == 1.0
    assert "paper_reduce_requires_outperforming" in r.gates_blocking


def test_similarity_already_reduced_does_not_double_punish():
    # Similarity already at 0.5 — combined floor should not fall below 0.5
    sim = {"matched": True, "multiplier": 0.5, "reason": "heavy"}
    r = evaluate_hybrid(
        ml_signal=_sig(ml_action="avoid", ml_confidence=0.9),
        cfg=_cfg(mode="paper_reduce", min_multiplier=0.50),
        current_paper_mult=1.0, data_quality=_dq(),
        similarity=sim,
    )
    # product with sim (0.5 × ml_mult) must stay >= 0.5 → ml_mult >= 1.0
    # so ml floor gets raised to keep product at or above min_multiplier
    product = 0.5 * r.multiplier
    assert product >= 0.50 - 1e-9


def test_snapshot_includes_key_fields():
    r = evaluate_hybrid(
        ml_signal=_sig(ml_action="reduce"),
        cfg=_cfg(mode="paper_reduce"),
        current_paper_mult=1.0, data_quality=_dq(),
    )
    snap = r.to_dict()
    assert "ml_hybrid_enabled" in snap
    assert "ml_shadow_multiplier" in snap
    assert "ml_hybrid_action" in snap
    assert "ml_hybrid_reason" in snap
    assert "ml_hybrid_snapshot" in snap
    inner = snap["ml_hybrid_snapshot"]
    assert inner["mode"] == "paper_reduce"
    assert inner["status"] == "SHADOW_OUTPERFORMING"
    assert "gates_blocking" in inner


def test_real_money_path_does_not_import_hybrid_policy():
    """Invariant: only paper-only modules import hybrid_policy.

    Allowed importers:
      • apps.api.src.data.strategy.paper_decision_wrapper (paper wrapper)
      • apps.api.src.api.ml_hybrid                          (admin API)
      • apps.api.src.ml.shadow.hybrid_policy                (self)
      • apps.api.tests.*                                     (tests)
    Any other import is a leak into the real-money path.
    """
    import os
    import apps.api.src as _src
    root = os.path.dirname(_src.__file__)
    allowed_suffixes = (
        os.path.join("data", "strategy", "paper_decision_wrapper.py"),
        os.path.join("api", "ml_hybrid.py"),
        os.path.join("ml", "shadow", "hybrid_policy.py"),
    )
    offenders: list[str] = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dirpath, f)
            with open(p, encoding="utf-8") as fh:
                src = fh.read()
            if "ml.shadow.hybrid_policy" in src:
                if not any(p.endswith(a) for a in allowed_suffixes):
                    offenders.append(p)
    assert offenders == [], (
        f"hybrid_policy imported from disallowed modules: {offenders}"
    )
