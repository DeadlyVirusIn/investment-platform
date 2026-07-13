"""Wave 1D — replay identity pinning, isolation, associations (pg)."""

from __future__ import annotations

import datetime
import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.domain.recommendations import replay as rp
from apps.api.tests.integration.test_publication_preflight_pg import (
    _mk_asset,
    _mk_bar,
    _mk_rec,
    _seed_ingest_success,
)

pytestmark = pytest.mark.integration

NOW = datetime.datetime.now(datetime.timezone.utc)


@pytest.fixture(autouse=True)
def _fresh_cache():
    rp.reset_cache_for_tests()
    yield
    rp.reset_cache_for_tests()


def _rec_at(db, asset_id, hours_ago, **kw):
    return _mk_rec(db, asset_id,
                   generated_at=NOW - datetime.timedelta(hours=hours_ago),
                   **kw)


def _mk_user_book(db: Session, uid: str) -> str:
    pid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO paper_portfolio (id, name, starting_cash, cash, "
        "is_active, created_at, updated_at) VALUES "
        "(:i, :n, 10000, 9000, true, now(), now())"
    ), {"i": pid, "n": f"user:{uid}:stock"})
    return pid


def _mk_paper(db: Session, pid: str, asset_id: str, rec_id: str,
              cost_stamp: dict | None = None) -> None:
    tid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO paper_trade (id, portfolio_id, asset_id, side, "
        "quantity, fill_price, fill_ts, submitted_at, recommendation_id, "
        "created_at, commission, slippage_bps, execution_cost_json) VALUES "
        "(:t, :p, :a, 'buy', 2.8, 356.81, now(), now(), :r, now(), 0, 0, "
        "CAST(:c AS jsonb))"
    ), {"t": tid, "p": pid, "a": asset_id, "r": rec_id,
        "c": json.dumps(cost_stamp) if cost_stamp else None})
    db.execute(text(
        "INSERT INTO paper_position (id, portfolio_id, asset_id, quantity, "
        "avg_cost, is_open, opened_at, updated_at, "
        "opened_by_recommendation_id, opening_trade_id) VALUES "
        "(:i, :p, :a, 2.8, 356.81, true, now(), now(), :r, :t)"
    ), {"i": str(uuid.uuid4()), "p": pid, "a": asset_id, "r": rec_id,
        "t": tid})
    db.flush()


# ---------------------------------------------------------------------------
# identity pinning
# ---------------------------------------------------------------------------

def test_pinned_identity_survives_cross_asset_same_symbol(
    pg_session: Session,
) -> None:
    a1 = _mk_asset(pg_session, "PIN")
    _mk_bar(pg_session, a1.id)
    r1 = _rec_at(pg_session, a1.id, 24)
    pinned = rp.resolve_pinned(pg_session, "PIN")
    assert pinned == (r1.id, a1.id)
    tl1 = rp.get_timeline(pg_session, rec_id=r1.id)
    # a NEWER recommendation on a DIFFERENT asset reusing the symbol
    a2_id = pg_session.execute(text(
        "INSERT INTO asset (id, symbol, asset_class, exchange, currency, "
        "is_active, created_at, updated_at) VALUES (:i, 'PIN', 'equity', "
        "'OTHER', 'USD', true, now(), now()) RETURNING id"
    ), {"i": str(uuid.uuid4())}).scalar()
    _rec_at(pg_session, a2_id, 1)
    rp.reset_cache_for_tests()
    tl2 = rp.get_timeline(pg_session, rec_id=r1.id)
    assert tl1["recommendation_as_of"] == tl2["recommendation_as_of"]
    assert len(tl1["events"]) == len(tl2["events"])   # replay unchanged
    # symbol resolution NOW pins the new asset — but that is a NEW replay,
    # not a mutation of the old one
    assert rp.resolve_pinned(pg_session, "PIN")[1] == a2_id


def test_updates_included_only_with_proven_continuity(
    pg_session: Session,
) -> None:
    # replay-2: a linked open paper position proves the idea is still the
    # same lifecycle → the later row appears as an update.
    a = _mk_asset(pg_session, "UPD")
    _mk_bar(pg_session, a.id)
    r1 = _rec_at(pg_session, a.id, 72, action="Buy")
    pid = _mk_user_book(pg_session, "user-upd")
    _mk_paper(pg_session, pid, a.id, r1.id)           # open linked position
    _rec_at(pg_session, a.id, 48, action="Hold")      # meaningful update
    tl = rp.get_timeline(pg_session, rec_id=r1.id)
    ups = [e for e in tl["events"] if e["type"] == "update"]
    assert len(ups) == 1
    assert "cautious" in ups[0]["summary"]
    assert tl["updates_complete"] is True


def test_unproven_continuity_conservatively_omits_updates(
    pg_session: Session,
) -> None:
    # unresolved pinned idea, NO outcome, NO linked position — a later
    # same-asset (even same-action) row months later is NOT an update.
    a = _mk_asset(pg_session, "UNPR")
    _mk_bar(pg_session, a.id)
    r1 = _rec_at(pg_session, a.id, 24 * 90, action="Buy")
    _rec_at(pg_session, a.id, 2, action="Buy")        # same action, months later
    tl = rp.get_timeline(pg_session, rec_id=r1.id)
    assert tl["updates_complete"] is False
    assert not any(e["type"] == "update" for e in tl["events"])
    assert any(u["section"] == "later_updates"
               for u in tl["unavailable_sections"])


def test_closed_position_bounds_update_window(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "CLSD")
    _mk_bar(pg_session, a.id)
    r1 = _rec_at(pg_session, a.id, 96, action="Buy")
    pid = _mk_user_book(pg_session, "user-clsd")
    _mk_paper(pg_session, pid, a.id, r1.id)
    pg_session.execute(text(
        "UPDATE paper_position SET is_open = false, "
        "closed_at = now() - interval '48 hours' "
        "WHERE opened_by_recommendation_id = :r"), {"r": r1.id})
    pg_session.flush()
    _rec_at(pg_session, a.id, 72, action="Hold")      # inside window → update
    _rec_at(pg_session, a.id, 2, action="Sell")       # after close → excluded
    tl = rp.get_timeline(pg_session, rec_id=r1.id)
    ups = [e for e in tl["events"] if e["type"] == "update"]
    assert len(ups) == 1
    assert "cautious" in ups[0]["summary"]


def test_terminal_outcome_bounds_updates_and_new_idea_starts_fresh(
    pg_session: Session,
) -> None:
    a = _mk_asset(pg_session, "TERM")
    _mk_bar(pg_session, a.id)
    r1 = _rec_at(pg_session, a.id, 96, action="Buy")
    pg_session.execute(text(
        "INSERT INTO recommendation_outcome (id, recommendation_id, "
        "barrier_label, barrier_first_touch_at, created_at, updated_at) "
        "VALUES (:i, :r, 1, now() - interval '48 hours', now(), now())"
    ), {"i": str(uuid.uuid4()), "r": r1.id})
    pg_session.flush()
    _rec_at(pg_session, a.id, 72, action="Hold")      # pre-resolution update
    later = _rec_at(pg_session, a.id, 2, action="Buy")  # post-resolution
    tl = rp.get_timeline(pg_session, rec_id=r1.id)
    assert tl["lifecycle_status"] == "resolved_target"
    ups = [e for e in tl["events"] if e["type"] == "update"]
    assert len(ups) == 1                              # bounded by resolution
    # the post-resolution row is its own fresh lifecycle
    rp.reset_cache_for_tests()
    tl2 = rp.get_timeline(pg_session, rec_id=later.id)
    assert tl2["recommendation_as_of"] != tl["recommendation_as_of"]


def test_duplicate_scheduler_siblings_produce_no_phantom_updates(
    pg_session: Session,
) -> None:
    # identical same-timestamp siblings inside a proven window: the delta
    # between identical rows has no meaningful change → no update events.
    a = _mk_asset(pg_session, "SIBL")
    _mk_bar(pg_session, a.id)
    # all rows on the same side of the wording cutover — a straddle would
    # legitimately emit a confidence-presentation change, not a phantom
    r1 = _rec_at(pg_session, a.id, 30, action="Buy")
    pid = _mk_user_book(pg_session, "user-sibl")
    _mk_paper(pg_session, pid, a.id, r1.id)
    ts = NOW - datetime.timedelta(hours=24)
    _mk_rec(pg_session, a.id, generated_at=ts, action="Buy")
    _mk_rec(pg_session, a.id, generated_at=ts, action="Buy")
    tl = rp.get_timeline(pg_session, rec_id=r1.id)
    assert not any(e["type"] == "update" for e in tl["events"])
    assert tl["updates_complete"] is True


def test_same_timestamp_siblings_do_not_break_replay(
    pg_session: Session,
) -> None:
    a = _mk_asset(pg_session, "TWIN")
    _mk_bar(pg_session, a.id)
    ts = NOW - datetime.timedelta(hours=24)
    x = _mk_rec(pg_session, a.id, generated_at=ts)
    y = _mk_rec(pg_session, a.id, generated_at=ts)
    lo = x if x.id < y.id else y
    tl = rp.get_timeline(pg_session, rec_id=lo.id)
    assert tl is not None
    assert tl["events"][0]["type"] == "idea_generated"


# ---------------------------------------------------------------------------
# user isolation
# ---------------------------------------------------------------------------

def test_user_isolation_and_anonymous_blindness(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "ISO")
    _mk_bar(pg_session, a.id)
    rec = _rec_at(pg_session, a.id, 24)
    pid_a = _mk_user_book(pg_session, "user-a")
    _mk_paper(pg_session, pid_a, a.id, rec.id)
    # user A sees their own activity
    tl_a = rp.get_timeline(pg_session, rec_id=rec.id, user_id="user-a")
    assert any(e["type"] == "paper_action" for e in tl_a["events"])
    # user B sees none of A's activity
    tl_b = rp.get_timeline(pg_session, rec_id=rec.id, user_id="user-b")
    assert not any(e["type"] == "paper_action" for e in tl_b["events"])
    # anonymous sees none
    tl_anon = rp.get_timeline(pg_session, rec_id=rec.id, user_id=None)
    assert not any(e["type"] == "paper_action" for e in tl_anon["events"])
    # cache principal isolation: repeated mixed-principal reads stay correct
    assert any(e["type"] == "paper_action" for e in rp.get_timeline(
        pg_session, rec_id=rec.id, user_id="user-a")["events"])
    assert not any(e["type"] == "paper_action" for e in rp.get_timeline(
        pg_session, rec_id=rec.id, user_id=None)["events"])


def test_engine_demo_book_never_appears_as_user_activity(
    pg_session: Session,
) -> None:
    a = _mk_asset(pg_session, "DEMO")
    _mk_bar(pg_session, a.id)
    rec = _rec_at(pg_session, a.id, 24)
    pid = str(uuid.uuid4())
    pg_session.execute(text(
        "INSERT INTO paper_portfolio (id, name, starting_cash, cash, "
        "is_active, created_at, updated_at) VALUES "
        "(:i, 'engine:stock', 100000, 90000, true, now(), now())"
    ), {"i": pid})
    _mk_paper(pg_session, pid, a.id, rec.id)
    tl = rp.get_timeline(pg_session, rec_id=rec.id, user_id="user-a")
    assert not any(e["type"] == "paper_action" for e in tl["events"])


def test_cost_stamp_rendered_and_absent_disclosed(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "COST")
    _mk_bar(pg_session, a.id)
    rec = _rec_at(pg_session, a.id, 24)
    pid = _mk_user_book(pg_session, "user-c")
    _mk_paper(pg_session, pid, a.id, rec.id, cost_stamp={
        "gross_notional": "999.07", "commission": "1.00",
        "slippage_cost": "0.50", "total_cost": "1.50",
        "net_notional": "997.57", "cost_model_version": "cost-1",
    })
    tl = rp.get_timeline(pg_session, rec_id=rec.id, user_id="user-c")
    ev = next(e for e in tl["events"] if e["type"] == "paper_action")
    assert ev["details"]["execution_costs"]["cost_model_version"] == "cost-1"
    assert ev["detail_status"] == "complete"


# ---------------------------------------------------------------------------
# associations + firewall
# ---------------------------------------------------------------------------

def test_persisted_preflight_posture_association_no_new_rows(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.src.domain.publication import posture as ps
    from apps.api.src.domain.publication import preflight as pf
    monkeypatch.setattr(settings, "SYSTEM_POSTURE_ENABLED", True,
                        raising=False)
    ps.reset_cache_for_tests()
    a = _mk_asset(pg_session, "ASSC")
    _mk_bar(pg_session, a.id)
    _seed_ingest_success(pg_session)
    rec = _rec_at(pg_session, a.id, 2)
    pf.run_and_persist(pg_session, rec)
    counts_before = [pg_session.execute(text(
        f"SELECT count(*) FROM {t}")).scalar()
        for t in ("recommendation_preflight", "system_posture_event")]
    tl = rp.get_timeline(pg_session, rec_id=rec.id)
    assert any(e["type"] == "preflight" for e in tl["events"])
    assert any(e["type"] == "posture" for e in tl["events"])
    counts_after = [pg_session.execute(text(
        f"SELECT count(*) FROM {t}")).scalar()
        for t in ("recommendation_preflight", "system_posture_event")]
    assert counts_before == counts_after


def test_thesis_events_only_when_flag_on_and_labeled_related(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = _mk_asset(pg_session, "THX")
    _mk_bar(pg_session, a.id)
    rec = _rec_at(pg_session, a.id, 24)
    pg_session.execute(text(
        "INSERT INTO thesis (id, asset_id, scope, title, statement, "
        "wrong_if, horizon, status, created_by, created_at, updated_at) "
        "VALUES (:i, :a, 'company', 'T', 'Statement long enough.', "
        "'Wrong if broken.', 'months', 'active', 'owner', now(), now())"
    ), {"i": str(uuid.uuid4()), "a": a.id})
    pg_session.flush()
    tl_off = rp.get_timeline(pg_session, rec_id=rec.id)
    assert not any(e["type"] == "thesis" for e in tl_off["events"])
    monkeypatch.setattr(settings, "THESIS_LEDGER_ENABLED", True,
                        raising=False)
    rp.reset_cache_for_tests()
    tl_on = rp.get_timeline(pg_session, rec_id=rec.id)
    ev = next(e for e in tl_on["events"] if e["type"] == "thesis")
    assert "Related asset thesis" in ev["title"]


def test_lesson_events_flagged_and_review_gated(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = _mk_asset(pg_session, "LES")
    _mk_bar(pg_session, a.id)
    rec = _rec_at(pg_session, a.id, 24)
    for state, who in (("approved", "owner@x"), ("draft", None)):
        pg_session.execute(text(
            "INSERT INTO lesson (id, recommendation_id, what_happened, "
            "original_thesis_quote, expectation, evidence_correct, "
            "evidence_misleading, thesis_effect, provenance, review_state, "
            "reviewed_by, reviewed_at, created_by, created_at) VALUES "
            "(:i, :r, 'It moved.', 'Quoted thesis.', 'Expected up.', "
            "'[]', '[]', 'none', 'generated', "
            ":s, CAST(:w AS text), "
            "CASE WHEN CAST(:w AS text) IS NULL THEN NULL ELSE now() END, "
            "'engine', now())"
        ), {"i": str(uuid.uuid4()), "r": rec.id, "s": state, "w": who})
    pg_session.flush()
    monkeypatch.setattr(settings, "LEARNING_LOOP_ENABLED", True,
                        raising=False)
    pub = rp.get_timeline(pg_session, rec_id=rec.id)
    assert len([e for e in pub["events"] if e["type"] == "lesson"]) == 1
    rp.reset_cache_for_tests()
    own = rp.get_timeline(pg_session, rec_id=rec.id, owner=True)
    assert len([e for e in own["events"] if e["type"] == "lesson"]) == 2


def test_no_writes_and_query_bound(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "QRB")
    _mk_bar(pg_session, a.id)
    rec = _rec_at(pg_session, a.id, 24)
    _rec_at(pg_session, a.id, 2)
    tables = ("recommendation", "recommendation_preflight",
              "system_posture_event", "paper_trade", "paper_position",
              "lesson")
    before = {t: pg_session.execute(
        text(f"SELECT count(*) FROM {t}")).scalar() for t in tables}
    counter = {"n": 0}
    from sqlalchemy import event as sa_event
    engine = pg_session.get_bind()

    def cb(*args, **kw):  # noqa: ANN002, ANN003
        counter["n"] += 1

    sa_event.listen(engine, "before_cursor_execute", cb)
    try:
        rp.reset_cache_for_tests()
        rp.get_timeline(pg_session, symbol="QRB", user_id="user-x")
    finally:
        sa_event.remove(engine, "before_cursor_execute", cb)
    after = {t: pg_session.execute(
        text(f"SELECT count(*) FROM {t}")).scalar() for t in tables}
    assert before == after
    assert counter["n"] <= 12


def test_public_redaction_with_real_ids(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "REDX")
    _mk_bar(pg_session, a.id)
    rec = _rec_at(pg_session, a.id, 24)
    pid = _mk_user_book(pg_session, "user-r")
    _mk_paper(pg_session, pid, a.id, rec.id)
    tl = rp.get_timeline(pg_session, rec_id=rec.id, user_id="user-r")
    blob = json.dumps(tl)
    for leak in (rec.id, a.id, pid, "snapshot_hash", "git_sha",
                 "checks_json", "@"):
        assert leak not in blob


def test_flag_off_is_structural(pg_session: Session) -> None:
    import inspect
    assert settings.DECISION_REPLAY_ENABLED is False
    from apps.api.src.api import recommendations as rec_api
    assert "timeline" not in inspect.getsource(rec_api).lower()
