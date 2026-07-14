"""Wave 1C — delta compute invariants (pure, delta-1 rule set)."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.recommendations import delta as d

T0 = dt.datetime(2026, 7, 12, 23, 0, tzinfo=dt.timezone.utc)
T1 = dt.datetime(2026, 7, 13, 23, 0, tzinfo=dt.timezone.utc)


def facts(**over) -> d.RecFacts:
    base = dict(
        rec_id="cur", generated_at=T1, action="Buy",
        confidence_label="High",
        family_scores={"trend_momentum": 0.7, "volatility_risk": -0.2},
        malformed_families=(),
        stale_data=False, price_at=100.0,
        outcome_barrier=None, has_outcome_row=False,
        verdict="READY_WITH_LIMITATIONS",
        verdict_limitations=("Confidence wording is preliminary.",),
        posture="NORMAL",
    )
    base.update(over)
    return d.RecFacts(**base)


def prior(**over) -> d.RecFacts:
    over.setdefault("rec_id", "prior")
    over.setdefault("generated_at", T0)
    return facts(**over)


def run(cur_over=None, prior_over=None, *, no_prior: bool = False):
    return d.compute("ge", facts(**(cur_over or {})),
                     None if no_prior else prior(**(prior_over or {})))


def kinds(res):
    return [c.kind for c in res.changes]


# ---- first appearance -------------------------------------------------------

def test_no_prior_is_first_seen_with_no_invented_changes():
    res = run(no_prior=True)
    assert res.first_seen is True
    assert res.summary == "This is a new idea from ArthOS."
    assert res.changes == []
    assert res.prior_as_of is None
    assert res.evidence_balance == "not_evaluated"


# ---- action changes ---------------------------------------------------------

@pytest.mark.parametrize("prev_a, cur_a, direction", [
    ("Buy", "Hold", "cautious"),
    ("Buy", "Trim", "cautious"),
    ("Buy", "Sell", "cautious"),
    ("Hold", "Buy", "positive"),
])
def test_action_changes(prev_a, cur_a, direction):
    res = run({"action": cur_a}, {"action": prev_a})
    c = next(c for c in res.changes if c.kind == "action_change")
    assert c.direction == direction
    assert f"from {prev_a} to {cur_a}" in c.beginner_text
    assert res.changes[0].kind == "action_change"     # top priority
    assert res.summary.startswith("ArthOS became more")
    # never causal market language
    assert "market" not in c.beginner_text.lower()


# ---- confidence presentation + historical wording ---------------------------

def test_confidence_presentation_change_detected():
    res = run({"confidence_label": "Low"}, {"confidence_label": "High"})
    c = next(c for c in res.changes if c.kind == "confidence_presentation")
    assert "meets the buy bar" in c.beginner_text
    assert "low confidence" in c.beginner_text


def test_historical_wording_not_rewritten():
    # prior generated BEFORE the wording cutover renders under legacy copy
    old = d.WORDING_CUTOVER - dt.timedelta(days=2)
    assert d.presentation_for("High", old) == "high confidence"
    assert d.presentation_for("High", T1) == "meets the buy bar"
    res = run({"confidence_label": "High"},
              {"confidence_label": "High", "generated_at": old})
    c = next(c for c in res.changes if c.kind == "confidence_presentation")
    assert "high confidence" in c.beginner_text          # history preserved
    assert "meets the buy bar" in c.beginner_text        # today’s policy today


def test_same_presentation_no_change():
    res = run({"confidence_label": "Medium"}, {"confidence_label": "High"})
    assert "confidence_presentation" not in kinds(res)   # both → buy bar


# ---- family thresholds ------------------------------------------------------

@pytest.mark.parametrize("delta_v, expect", [
    (0.049, None), (0.05, "small"), (0.149, "small"),
    (0.15, "meaningful"), (0.349, "meaningful"), (0.35, "large"),
])
def test_score_threshold_boundaries(delta_v, expect):
    assert d._score_sig(delta_v) == expect
    assert d._score_sig(-delta_v) == expect


def test_family_directions_and_vocabulary():
    res = run({"family_scores": {"trend_momentum": 0.9,
                                 "volatility_risk": -0.6}},
              {"family_scores": {"trend_momentum": 0.7,
                                 "volatility_risk": -0.2}})
    trend = next(c for c in res.changes if c.id == "family_change:trend_momentum")
    risk = next(c for c in res.changes if c.id == "family_change:volatility_risk")
    assert trend.direction == "positive" and "price trend" in trend.beginner_text
    assert risk.direction == "cautious" and "price-swing risk" in risk.beginner_text
    assert res.evidence_balance == "mixed"


def test_family_added_and_removed():
    res = run({"family_scores": {"trend_momentum": 0.7, "exposure": 0.3}},
              {"family_scores": {"trend_momentum": 0.7,
                                 "volatility_risk": -0.2}})
    added = next(c for c in res.changes if c.kind == "family_added")
    removed = next(c for c in res.changes if c.kind == "family_removed")
    assert "New supporting evidence" in added.beginner_text
    assert "no longer part of the case" in removed.beginner_text


def test_missing_vs_zero_distinct():
    # zero-valued family present in both → unchanged, no removal/addition
    res = run({"family_scores": {"trend_momentum": 0.0}},
              {"family_scores": {"trend_momentum": 0.0}})
    assert "family_removed" not in kinds(res)
    assert "family_added" not in kinds(res)
    assert res.evidence_balance == "unchanged"


def test_malformed_values_yield_unavailable_not_direction():
    res = run({"family_scores": {}, "malformed_families": ("trend_momentum",)},
              {"family_scores": {"trend_momentum": 0.7}})
    c = next(c for c in res.changes if c.kind == "family_unavailable")
    assert "unavailable" in c.beginner_text
    assert all(x.kind != "family_change" for x in res.changes)


def test_tiny_drift_not_material():
    res = run({"family_scores": {"trend_momentum": 0.701}},
              {"family_scores": {"trend_momentum": 0.700}})
    assert res.changes == []
    assert "broadly unchanged" in res.summary


# ---- evidence balance summaries ---------------------------------------------

def test_balance_more_supportive_summary():
    res = run({"family_scores": {"trend_momentum": 1.2,
                                 "volatility_risk": -0.2}})
    assert res.evidence_balance == "more_supportive"
    assert res.summary == ("The main action is unchanged, but the evidence "
                           "strengthened.")


def test_balance_more_cautious_summary():
    res = run({"family_scores": {"trend_momentum": 0.7,
                                 "volatility_risk": -0.8}})
    assert res.evidence_balance == "more_cautious"
    assert "more cautious" in res.summary


# ---- price context ------------------------------------------------------------

@pytest.mark.parametrize("pct, expect", [
    (0.2, None), (0.3, "small"), (1.49, "small"),
    (1.5, "meaningful"), (3.99, "meaningful"), (4.0, "large"),
])
def test_price_threshold_boundaries(pct, expect):
    assert d._price_sig(pct) == expect


def test_price_move_change_and_large_priority():
    res = run({"price_at": 106.0})     # +6% vs prior 100 → large
    c = next(c for c in res.changes if c.kind == "price_move")
    assert c.significance == "large"
    assert "6.0%" in c.beginner_text
    assert res.changes[0].kind == "price_move"    # large price = priority 2


def test_price_unavailable_stays_unavailable():
    res = run({"price_at": None})
    assert res.price_context is None
    assert "price_move" not in kinds(res)


# ---- outcome status ------------------------------------------------------------

@pytest.mark.parametrize("barrier, phrase, direction", [
    (1, "target zone", "positive"),
    (-1, "exit condition", "cautious"),
    (0, "time limit", "neutral"),
])
def test_outcome_status(barrier, phrase, direction):
    res = run({"outcome_barrier": barrier, "has_outcome_row": True})
    c = next(c for c in res.changes if c.kind == "outcome_status")
    assert phrase in c.beginner_text and c.direction == direction


# ---- freshness / posture / limitations ------------------------------------------

def test_freshness_degraded_and_improved():
    worse = run({"stale_data": True})
    assert any("staleness flag" in c.beginner_text for c in worse.changes)
    better = run({}, {"stale_data": True})
    assert any("fresher than" in c.beginner_text for c in better.changes)


def test_limitation_added_and_removed():
    res = run({"verdict_limitations": ("a", "b")},
              {"verdict_limitations": ("a",)})
    assert any(c.id == "limitation_added" for c in res.changes)
    res2 = run({"verdict_limitations": ()},
               {"verdict_limitations": ("a",)})
    assert any(c.id == "limitation_removed" for c in res2.changes)


def test_posture_transition_to_safe():
    res = run({"posture": "SAFE"}, {"posture": "NORMAL"})
    c = next(c for c in res.changes if c.kind == "posture_change")
    assert "paused by Safe Mode" in c.beginner_text
    assert c.direction == "cautious"


def test_posture_not_evaluated_is_silent():
    res = run({"posture": None}, {"posture": None})
    assert "posture_change" not in kinds(res)


# ---- ordering, cap, redaction -----------------------------------------------------

def test_deterministic_ordering_and_cap():
    over_cur = {
        "action": "Hold",
        "family_scores": {"trend_momentum": 1.5, "volatility_risk": -1.5,
                          "exposure": 0.9},
        "stale_data": True,
        "confidence_label": "Low",
        "price_at": 110.0,
        "outcome_barrier": -1, "has_outcome_row": True,
        "verdict_limitations": ("a", "b"),
        "posture": "RESTRICTED",
    }
    res = run(over_cur, {"action": "Buy"})
    assert len(res.changes) <= d.MAX_CHANGES
    assert res.changes[0].kind == "action_change"
    a = d.compute("ge", facts(**over_cur), prior(action="Buy"))
    b = d.compute("ge", facts(**over_cur), prior(action="Buy"))
    assert [c.id for c in a.changes] == [c.id for c in b.changes]


def test_public_dict_redaction():
    import json
    res = run({"price_at": 106.0})
    blob = json.dumps(res.public_dict())
    for leak in ("rec_id", '"cur"', '"prior"', "snapshot_hash", "git_sha",
                 "input_hash", "family_scores", "checks_json", "job_id"):
        assert leak not in blob
    assert '"rule_set_version": "delta-1"' in blob


def test_no_material_change_state():
    res = run()
    assert res.changes == []
    assert res.summary == ("The evidence is broadly unchanged since the "
                           "previous update.")
