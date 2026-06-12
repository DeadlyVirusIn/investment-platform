"""P0-2A — unit + golden-table tests for derived_confidence (v2 shadow).

Pure-function tests: no DB, no fixtures, no clock. Expected golden
values are hand-computed from the locked formula:

    confidence_v2 = 0.35*delta_placement + 0.30*economics_quality
                  + 0.20*signal_alignment + 0.15*freshness_quality
"""

from __future__ import annotations

import pytest

from apps.api.src.options.strategy_candidates.derived_confidence import (
    DerivedConfidence,
    MODEL_TAG,
    compute_confidence_v2,
)


def _cv2(**overrides):
    """Call compute_confidence_v2 with neutral defaults, overridable."""
    kwargs = dict(
        short_abs_deltas=None,
        credit=None,
        width=None,
        pop=None,
        is_directional=False,
        high_importance_event=False,
        quote_age_seconds=None,
    )
    kwargs.update(overrides)
    return compute_confidence_v2(**kwargs)


# ---------------------------------------------------------------------------
# Golden table — 12 representative candidates, expected values explicit.
# Each expectation is hand-computed in the comment.
# ---------------------------------------------------------------------------

GOLDEN = [
    # (label, kwargs, expected_value)
    (
        "G1 ideal directional spread, fresh quote",
        dict(short_abs_deltas=[0.30], credit=0.35, width=1.0,
             is_directional=True, quote_age_seconds=30),
        # dp=1.0 eq=clip(.35/.33)=1.0 sa=.70 fq=1.0
        # .35 + .30 + .14 + .15 = .94
        0.94,
    ),
    (
        "G2 decent spread, delta 0.25, credit 0.25",
        dict(short_abs_deltas=[0.25], credit=0.25, width=1.0,
             is_directional=True, quote_age_seconds=30),
        # dp=1-.05/.15=.666667 eq=.25/.33=.757576 sa=.70 fq=1.0
        # .233333 + .227273 + .14 + .15 = .750606
        0.7506,
    ),
    (
        "G3 iron condor, two wings, no quote age",
        dict(short_abs_deltas=[0.28, 0.33], credit=0.30, width=1.0,
             is_directional=False, quote_age_seconds=None),
        # dp=min(.866667,.8)=.8 eq=.30/.33=.909091 sa=.50 fq=.50
        # .28 + .272727 + .10 + .075 = .727727
        0.7277,
    ),
    (
        "G4 everything missing, directional",
        dict(is_directional=True),
        # dp=.40 eq=.40 sa=.70 fq=.50
        # .14 + .12 + .14 + .075 = .475
        0.475,
    ),
    (
        "G5 ideal spread but quote age at zero-point 900s",
        dict(short_abs_deltas=[0.30], credit=0.35, width=1.0,
             is_directional=True, quote_age_seconds=900),
        # fq=0 -> .35 + .30 + .14 + 0 = .79
        0.79,
    ),
    (
        "G6 ideal spread, mid-decay age 480s",
        dict(short_abs_deltas=[0.30], credit=0.35, width=1.0,
             is_directional=True, quote_age_seconds=480),
        # fq=(900-480)/840=.5 -> .35 + .30 + .14 + .075 = .865
        0.865,
    ),
    (
        "G7 directional + high-importance event",
        dict(short_abs_deltas=[0.25], credit=0.25, width=1.0,
             is_directional=True, high_importance_event=True,
             quote_age_seconds=30),
        # sa=.80 -> .233333 + .227273 + .16 + .15 = .770606
        0.7706,
    ),
    (
        "G8 neutral IC + high-importance event",
        dict(short_abs_deltas=[0.28, 0.33], credit=0.30, width=1.0,
             is_directional=False, high_importance_event=True,
             quote_age_seconds=None),
        # sa=.60 -> .28 + .272727 + .12 + .075 = .747727
        0.7477,
    ),
    (
        "G9 negative credit clips economics to 0",
        dict(short_abs_deltas=[0.30], credit=-0.05, width=1.0,
             is_directional=True, quote_age_seconds=30),
        # eq=0 -> .35 + 0 + .14 + .15 = .64
        0.64,
    ),
    (
        "G10 POP supplied blends with credit ratio",
        dict(short_abs_deltas=[0.30], credit=0.35, width=1.0, pop=0.75,
             is_directional=True, quote_age_seconds=30),
        # pop_score=clip(.25/.35)=.714286 eq=.5*1+.5*.714286=.857143
        # .35 + .257143 + .14 + .15 = .897143
        0.8971,
    ),
    (
        "G11 POP at/below floor zeroes the POP half",
        dict(short_abs_deltas=[0.30], credit=0.35, width=1.0, pop=0.40,
             is_directional=True, quote_age_seconds=30),
        # pop_score=0 eq=.5 -> .35 + .15 + .14 + .15 = .79
        0.79,
    ),
    (
        "G12 far delta zeroes placement",
        dict(short_abs_deltas=[0.45], credit=0.20, width=1.0,
             is_directional=True, quote_age_seconds=30),
        # dp=0 eq=.20/.33=.606061 -> 0 + .181818 + .14 + .15 = .471818
        0.4718,
    ),
]


@pytest.mark.parametrize(
    "label,kwargs,expected", GOLDEN, ids=[g[0] for g in GOLDEN],
)
def test_golden_table(label, kwargs, expected):
    result = _cv2(**kwargs)
    assert result.value == pytest.approx(expected, abs=1e-4), label


# ---------------------------------------------------------------------------
# Component edges + clipping
# ---------------------------------------------------------------------------


def test_delta_at_exact_target_scores_one():
    r = _cv2(short_abs_deltas=[0.30])
    assert r.components["delta_placement"] == 1.0


@pytest.mark.parametrize("delta", [0.15, 0.45, 0.60, 0.05])
def test_delta_outside_band_clips_to_zero(delta):
    r = _cv2(short_abs_deltas=[delta])
    assert r.components["delta_placement"] == 0.0


def test_delta_min_rule_across_short_legs():
    solo = _cv2(short_abs_deltas=[0.33])
    pair = _cv2(short_abs_deltas=[0.30, 0.33])
    assert pair.components["delta_placement"] == (
        solo.components["delta_placement"]
    )


def test_credit_ratio_clips_at_one():
    r = _cv2(credit=2.0, width=1.0)  # ratio 2.0 >> 0.33
    assert r.components["economics_quality"] == 1.0


def test_pop_clips_at_one():
    r = _cv2(credit=0.35, width=1.0, pop=0.95)
    # both halves at 1.0
    assert r.components["economics_quality"] == 1.0


def test_zero_or_negative_width_degrades():
    assert _cv2(credit=0.30, width=0.0).components[
        "economics_quality"] == 0.40
    assert _cv2(credit=0.30, width=-1.0).components[
        "economics_quality"] == 0.40


def test_freshness_boundaries():
    assert _cv2(quote_age_seconds=0).components["freshness_quality"] == 1.0
    assert _cv2(quote_age_seconds=60).components["freshness_quality"] == 1.0
    assert _cv2(quote_age_seconds=900).components[
        "freshness_quality"] == 0.0
    assert _cv2(quote_age_seconds=2000).components[
        "freshness_quality"] == 0.0
    mid = _cv2(quote_age_seconds=480).components["freshness_quality"]
    assert mid == pytest.approx(0.5, abs=1e-9)


def test_alignment_values_and_event_bonus():
    assert _cv2(is_directional=True).components[
        "signal_alignment"] == 0.70
    assert _cv2(is_directional=False).components[
        "signal_alignment"] == 0.50
    assert _cv2(is_directional=True, high_importance_event=True).components[
        "signal_alignment"] == pytest.approx(0.80)
    assert _cv2(is_directional=False, high_importance_event=True).components[
        "signal_alignment"] == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# Missing-input degradation
# ---------------------------------------------------------------------------


def test_all_missing_inputs_degrade_with_reasons():
    r = _cv2()
    assert r.components["delta_placement"] == 0.40
    assert r.components["economics_quality"] == 0.40
    assert r.components["freshness_quality"] == 0.50
    joined = " ".join(r.reasons)
    assert "delta unavailable" in joined
    assert "credit/width unavailable" in joined
    assert "quote age unavailable" in joined


def test_none_entries_in_delta_list_are_filtered():
    r = _cv2(short_abs_deltas=[None, 0.30])
    assert r.components["delta_placement"] == 1.0


def test_pop_missing_uses_credit_ratio_only_with_reason():
    r = _cv2(credit=0.165, width=1.0)  # ratio .165 -> cr .5
    assert r.components["economics_quality"] == pytest.approx(0.5, abs=1e-9)
    assert any("POP unavailable" in s for s in r.reasons)


# ---------------------------------------------------------------------------
# Determinism + output bounds + payload shape
# ---------------------------------------------------------------------------


def test_determinism_same_inputs_same_output():
    kwargs = dict(short_abs_deltas=[0.27], credit=0.28, width=1.0,
                  pop=0.66, is_directional=True,
                  high_importance_event=True, quote_age_seconds=120)
    a = _cv2(**kwargs)
    b = _cv2(**kwargs)
    assert a == b
    assert a.to_diagnostics() == b.to_diagnostics()


def test_value_always_within_unit_interval():
    grid_deltas = [None, [0.10], [0.30], [0.50], [0.28, 0.41]]
    grid_econ = [(None, None, None), (0.5, 1.0, None), (-1.0, 1.0, 0.9),
                 (0.4, 0.0, 0.2)]
    grid_age = [None, 0, 60, 500, 5000]
    for d in grid_deltas:
        for credit, width, pop in grid_econ:
            for age in grid_age:
                for dirn in (True, False):
                    for ev in (True, False):
                        v = _cv2(
                            short_abs_deltas=d, credit=credit, width=width,
                            pop=pop, is_directional=dirn,
                            high_importance_event=ev,
                            quote_age_seconds=age,
                        ).value
                        assert 0.0 <= v <= 1.0


def test_diagnostics_payload_shape():
    r = _cv2(short_abs_deltas=[0.30], credit=0.35, width=1.0,
             is_directional=True, quote_age_seconds=30)
    payload = r.to_diagnostics()
    assert payload["confidence_model"] == MODEL_TAG == "v2_shadow"
    assert payload["confidence_v2"] == r.value
    assert set(payload["confidence_v2_components"]) == {
        "delta_placement", "economics_quality",
        "signal_alignment", "freshness_quality",
    }
    assert len(payload["confidence_v2_reasons"]) == 4
    assert isinstance(r, DerivedConfidence)
