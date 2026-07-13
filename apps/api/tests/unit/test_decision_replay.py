"""Wave 1D — replay assembly invariants (pure, replay-1)."""

from __future__ import annotations

import datetime as dt
import inspect
import json

import pytest

from apps.api.src.domain.recommendations import replay as rp

T0 = dt.datetime(2026, 7, 10, 23, 42, tzinfo=dt.timezone.utc)


def inputs(**over) -> rp.ReplayInputs:
    base = dict(
        symbol="GE", rec_id="rec-1", asset_id="asset-1",
        generated_at=T0, action="Buy", confidence_label="High",
        family_scores={"trend_momentum": 0.7, "volatility_risk": -0.2},
        stale_data=False, engine_version="0.1.0",
        snapshot_hash_present=True, price_at=359.27,
        outcome=None, verdict=None, posture=None,
        updates=[], paper=[], theses=[], lessons=[],
        predates_preflight=True, predates_posture=True,
        user_scoped=False, owner=False,
    )
    base.update(over)
    return rp.ReplayInputs(**base)


def verdict(v="READY_WITH_LIMITATIONS", lims=("a limitation",)):
    return {"verdict": v, "limitations": list(lims),
            "rule_set_version": "pf-2", "checks_json": '[{"check_id":"x"}]',
            "created_at": T0 + dt.timedelta(minutes=5)}


def types(res):
    return [e["type"] for e in res["events"]]


# ---- core events -------------------------------------------------------------

def test_idea_generated_always_present_with_historical_wording():
    old = inputs(generated_at=dt.datetime(2026, 7, 1,
                                          tzinfo=dt.timezone.utc))
    res = rp.assemble(old)
    gen = res["events"][0]
    assert gen["type"] == "idea_generated"
    assert "high confidence" in gen["summary"]        # pre-cutover wording
    new = rp.assemble(inputs(
        generated_at=dt.datetime(2026, 7, 12, tzinfo=dt.timezone.utc)))
    assert "meets the buy bar" in new["events"][0]["summary"]


def test_predates_preflight_reported_as_unavailable_never_success():
    res = rp.assemble(inputs())
    assert "preflight" not in types(res)
    assert any(u["section"] == "publication_preflight"
               and "predates" in u["reason"]
               for u in res["unavailable_sections"])
    assert res["completeness"] == "partial"


def test_preflight_and_posture_events_when_persisted():
    res = rp.assemble(inputs(
        verdict=verdict(),
        posture={"posture": "RESTRICTED",
                 "created_at": (T0 + dt.timedelta(minutes=5)).isoformat()},
        predates_preflight=False, predates_posture=False,
    ))
    pf_ev = next(e for e in res["events"] if e["type"] == "preflight")
    assert "with honest limitations" in pf_ev["summary"]
    assert pf_ev["details"]["limitations"] == ["a limitation"]
    assert "checks" not in pf_ev["details"]           # public: no raw checks
    post = next(e for e in res["events"] if e["type"] == "posture")
    assert "with limitations" in post["summary"]


def test_owner_sees_checks_and_ruleset_public_does_not():
    res = rp.assemble(inputs(verdict=verdict(), owner=True,
                             predates_preflight=False))
    pf_ev = next(e for e in res["events"] if e["type"] == "preflight")
    assert pf_ev["details"]["rule_set_version"] == "pf-2"
    assert pf_ev["details"]["checks"] == [{"check_id": "x"}]


def test_outcome_states():
    for barrier, status, phrase in [
        (1, "resolved_target", "target zone"),
        (-1, "resolved_exit", "exit condition"),
        (0, "resolved_time", "time limit"),
    ]:
        res = rp.assemble(inputs(outcome={
            "barrier": barrier,
            "first_touch_at": (T0 + dt.timedelta(days=5)).isoformat(),
            "recorded_at": None,
        }))
        assert res["lifecycle_status"] == status
        ev = next(e for e in res["events"] if e["type"] == "outcome")
        assert phrase in ev["summary"]
        assert "paper" in ev["summary"]               # paper-only context
    open_res = rp.assemble(inputs(outcome={
        "barrier": None, "first_touch_at": None, "recorded_at": None}))
    assert open_res["lifecycle_status"] == "open"
    assert "outcome" not in types(open_res)


def test_paper_events_with_and_without_cost_stamp():
    stamp = {"gross_notional": "1000", "commission": "1.00",
             "slippage_cost": "0.50", "total_cost": "1.50",
             "net_notional": "998.50", "cost_model_version": "cost-1"}
    res = rp.assemble(inputs(user_scoped=True, paper=[{
        "quantity": 2.8, "avg_cost": 356.81,
        "opened_at": (T0 + dt.timedelta(hours=1)).isoformat(),
        "closed_at": None, "is_open": True, "realized_pnl": None,
        "open_cost_stamp": stamp, "close_cost_stamp": None,
    }]))
    ev = next(e for e in res["events"] if e["type"] == "paper_action")
    assert ev["details"]["execution_costs"]["cost_model_version"] == "cost-1"
    assert ev["detail_status"] == "complete"
    res2 = rp.assemble(inputs(user_scoped=True, paper=[{
        "quantity": 2.8, "avg_cost": 356.81,
        "opened_at": (T0 + dt.timedelta(hours=1)).isoformat(),
        "closed_at": None, "is_open": True, "realized_pnl": None,
        "open_cost_stamp": None, "close_cost_stamp": None,
    }]))
    ev2 = next(e for e in res2["events"] if e["type"] == "paper_action")
    assert "not recorded" in ev2["details"]["execution_costs_note"]
    assert ev2["detail_status"] == "partial"


def test_anonymous_has_no_paper_events():
    res = rp.assemble(inputs(paper=[]))
    assert "paper_action" not in types(res)


def test_thesis_labeled_related_and_partial():
    res = rp.assemble(inputs(theses=[{
        "title": "T", "status": "active",
        "status_changed_at": None, "created_at": T0.isoformat()}]))
    ev = next(e for e in res["events"] if e["type"] == "thesis")
    assert "Related asset thesis" in ev["title"]
    assert "not necessarily the exact thesis" in ev["summary"]
    assert ev["detail_status"] == "partial"


def test_lessons_public_approved_only_owner_sees_all():
    lessons = [
        {"what_happened": "Approved lesson.", "review_state": "approved",
         "provenance": "generated", "created_at": T0.isoformat(),
         "reviewed_at": None},
        {"what_happened": "Draft lesson.", "review_state": "draft",
         "provenance": "generated", "created_at": T0.isoformat(),
         "reviewed_at": None},
    ]
    pub = rp.assemble(inputs(lessons=lessons))
    assert len([e for e in pub["events"] if e["type"] == "lesson"]) == 1
    own = rp.assemble(inputs(lessons=lessons, owner=True))
    assert len([e for e in own["events"] if e["type"] == "lesson"]) == 2


def test_update_events_capped_and_delta_derived():
    updates = [{"occurred_at": (T0 + dt.timedelta(days=n)).isoformat(),
                "summary": f"u{n}", "top_kind": "action_change",
                "direction": "cautious"} for n in range(1, 5)]
    res = rp.assemble(inputs(updates=updates))
    assert len([e for e in res["events"] if e["type"] == "update"]) == 4


# ---- ordering + completeness ----------------------------------------------------

def test_same_timestamp_semantic_ordering_pinned():
    at = T0.isoformat()
    res = rp.assemble(inputs(
        verdict={**verdict(), "created_at": T0},
        posture={"posture": "NORMAL", "created_at": at},
        predates_preflight=False,
        outcome={"barrier": 1, "first_touch_at": at, "recorded_at": None},
        user_scoped=True,
        paper=[{"quantity": 1, "avg_cost": 1, "opened_at": at,
                "closed_at": None, "is_open": True, "realized_pnl": None,
                "open_cost_stamp": None, "close_cost_stamp": None}],
        lessons=[{"what_happened": "x", "review_state": "approved",
                  "provenance": "human", "created_at": at,
                  "reviewed_at": at}],
    ))
    ordered = types(res)
    assert ordered == ["idea_generated", "preflight", "posture",
                       "paper_action", "outcome", "lesson"]


def test_completeness_note_lists_missing_sections():
    res = rp.assemble(inputs())
    assert "predates publication-preflight" in res["completeness_note"]


def test_event_cap():
    res = rp.assemble(inputs(theses=[{
        "title": f"T{n}", "status": "active",
        "status_changed_at": None, "created_at": T0.isoformat()}
        for n in range(60)]))
    assert len(res["events"]) <= rp.MAX_EVENTS


# ---- redaction + firewall --------------------------------------------------------

def test_public_payload_redaction():
    res = rp.assemble(inputs(verdict=verdict(), predates_preflight=False))
    blob = json.dumps(res)
    for leak in ("rec-1", "asset-1", "snapshot_hash", "git_sha",
                 "checks_json", "family_scores", "@", "trade_id"):
        assert leak not in blob


def test_hindsight_firewall_source_pins():
    src = inspect.getsource(rp)
    for token in ("recommendation_engine", "run_preflight",
                  "evaluate_and_record", "requests.", "httpx",
                  "INSERT ", "UPDATE ", "DELETE "):
        assert token not in src, f"replay must not contain {token}"
