"""Phase F1 — assignment-risk classifier unit coverage. Pure, no DB."""

from __future__ import annotations

from apps.api.src.options.opportunities.assignment import assess_assignment_risk


def _leg(role, delta, ot):
    return {"role": role, "delta": delta, "option_type": ot}


def test_high_itm_short_near_expiry():
    r = assess_assignment_risk(
        [_leg("short_put", -0.58, "PUT"), _leg("long_put", -0.40, "PUT")], 4)
    assert r["level"] == "high"
    assert r["short_delta"] == 0.58
    assert r["defined_risk"] is True


def test_moderate_near_the_money():
    assert assess_assignment_risk([_leg("short_put", -0.35, "PUT")], 20)["level"] == "moderate"


def test_moderate_itm_but_far_dte():
    # ITM (|delta|>0.5) but DTE>5 → not the pin zone → moderate, not high.
    assert assess_assignment_risk([_leg("short_call", 0.60, "CALL")], 20)["level"] == "moderate"


def test_moderate_expiry_approaching_not_deep_otm():
    assert assess_assignment_risk([_leg("short_put", -0.20, "PUT")], 5)["level"] == "moderate"


def test_low_otm_with_time():
    assert assess_assignment_risk([_leg("short_put", -0.20, "PUT")], 16)["level"] == "low"


def test_iron_condor_uses_worst_short():
    r = assess_assignment_risk(
        [_leg("short_put", -0.30, "PUT"), _leg("short_call", 0.58, "CALL"),
         _leg("long_put", -0.20, "PUT"), _leg("long_call", 0.28, "CALL")], 4)
    assert r["level"] == "high" and r["option_type"] == "CALL"


def test_none_when_no_short_or_no_dte():
    assert assess_assignment_risk([_leg("long_put", -0.40, "PUT")], 10) is None
    assert assess_assignment_risk([_leg("short_put", -0.40, "PUT")], None) is None
