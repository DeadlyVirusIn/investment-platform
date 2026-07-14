"""Wave 1C — delta prior-selection, associations, redaction, flag (pg)."""

from __future__ import annotations

import datetime
import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.domain.recommendations import delta as d
from apps.api.tests.integration.test_publication_preflight_pg import (
    _mk_asset,
    _mk_bar,
    _mk_rec,
)

pytestmark = pytest.mark.integration

NOW = datetime.datetime.now(datetime.timezone.utc)


@pytest.fixture(autouse=True)
def _fresh_cache():
    d.reset_cache_for_tests()
    yield
    d.reset_cache_for_tests()


def _rec_at(db, asset_id, hours_ago, **kw):
    return _mk_rec(db, asset_id,
                   generated_at=NOW - datetime.timedelta(hours=hours_ago),
                   **kw)


def test_prior_selection_sequential_and_three_rows(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "SEQ")
    _mk_bar(pg_session, a.id)
    r1 = _rec_at(pg_session, a.id, 72, action="Buy")
    r2 = _rec_at(pg_session, a.id, 48, action="Buy")
    r3 = _rec_at(pg_session, a.id, 24, action="Hold")
    pair = d.load_pair(pg_session, "SEQ")
    assert pair is not None
    cur, prior = pair
    assert cur.rec_id == r3.id
    assert prior is not None and prior.rec_id == r2.id     # not r1
    res = d.compute("SEQ", cur, prior)
    assert any(c.kind == "action_change" for c in res.changes)
    assert r1.id not in (cur.rec_id, prior.rec_id)


def test_same_timestamp_tiebreak_by_id(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "TIE")
    _mk_bar(pg_session, a.id)
    ts = NOW - datetime.timedelta(hours=24)
    x = _mk_rec(pg_session, a.id, generated_at=ts)
    y = _mk_rec(pg_session, a.id, generated_at=ts)
    hi, lo = (x, y) if x.id > y.id else (y, x)
    cur, prior = d.load_pair(pg_session, "TIE")
    assert cur.rec_id == hi.id          # max (generated_at, id)
    assert prior is not None and prior.rec_id == lo.id
    # never a same-row or newer-sibling comparison
    assert cur.rec_id != prior.rec_id


def test_first_seen_when_single_row(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "SOLO")
    _mk_bar(pg_session, a.id)
    _rec_at(pg_session, a.id, 4)
    cur, prior = d.load_pair(pg_session, "SOLO")
    assert prior is None
    assert d.compute("SOLO", cur, prior).first_seen is True


def test_duplicate_symbol_across_assets_uses_latest_assets_chain(
    pg_session: Session,
) -> None:
    a1 = _mk_asset(pg_session, "DUP")
    a2 = pg_session.execute(text(
        "INSERT INTO asset (id, symbol, asset_class, exchange, currency, "
        "is_active, created_at, updated_at) VALUES (:i, 'DUP', 'equity', "
        "'OTHER', 'USD', true, now(), now()) RETURNING id"
    ), {"i": str(uuid.uuid4())}).scalar()
    _mk_bar(pg_session, a1.id)
    old_other = _rec_at(pg_session, a2, 48)      # newer asset? older row
    newest = _rec_at(pg_session, a1.id, 2)
    mid_same_asset = _rec_at(pg_session, a1.id, 24)
    cur, prior = d.load_pair(pg_session, "DUP")
    assert cur.rec_id == newest.id
    # prior must stay within the SAME canonical asset — never cross-asset
    assert prior is not None and prior.rec_id == mid_same_asset.id
    assert prior.rec_id != old_other.id


def test_future_dated_row_becomes_current_never_prior_of_itself(
    pg_session: Session,
) -> None:
    a = _mk_asset(pg_session, "FUT")
    _mk_bar(pg_session, a.id)
    _rec_at(pg_session, a.id, 24)
    fut = _mk_rec(pg_session, a.id,
                  generated_at=NOW + datetime.timedelta(days=2))
    cur, prior = d.load_pair(pg_session, "FUT")
    assert cur.rec_id == fut.id
    assert prior is not None and prior.rec_id != fut.id


def test_no_writes_produced(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "RO")
    _mk_bar(pg_session, a.id)
    _rec_at(pg_session, a.id, 24)
    _rec_at(pg_session, a.id, 2)
    before = {
        t: pg_session.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        for t in ("recommendation", "recommendation_preflight",
                  "system_posture_event")
    }
    d.get_delta(pg_session, "RO")
    after = {
        t: pg_session.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        for t in before
    }
    assert before == after
    src = __import__("inspect").getsource(d)
    assert "INSERT" not in src and "UPDATE" not in src and "DELETE" not in src


def test_persisted_preflight_and_posture_association(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.src.domain.publication import posture as ps
    from apps.api.src.domain.publication import preflight as pf
    from apps.api.tests.integration.test_publication_preflight_pg import (
        _seed_ingest_success,
    )
    monkeypatch.setattr(settings, "SYSTEM_POSTURE_ENABLED", True, raising=False)
    ps.reset_cache_for_tests()
    a = _mk_asset(pg_session, "ASSOC")
    _mk_bar(pg_session, a.id)
    _seed_ingest_success(pg_session)
    prior_rec = _rec_at(pg_session, a.id, 24)
    cur_rec = _rec_at(pg_session, a.id, 2)
    pf.run_and_persist(pg_session, prior_rec)
    pf.run_and_persist(pg_session, cur_rec)
    cur, prior = d.load_pair(pg_session, "ASSOC")
    assert cur.verdict is not None            # persisted fact consumed
    assert cur.posture is not None            # event current at verdict time
    n_before = pg_session.execute(text(
        "SELECT count(*) FROM recommendation_preflight")).scalar()
    d.get_delta(pg_session, "ASSOC")
    n_after = pg_session.execute(text(
        "SELECT count(*) FROM recommendation_preflight")).scalar()
    assert n_before == n_after                # never triggers an evaluation


def test_not_evaluated_when_no_persisted_facts(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "NOEVAL")
    _mk_bar(pg_session, a.id)
    _rec_at(pg_session, a.id, 24)
    _rec_at(pg_session, a.id, 2)
    cur, prior = d.load_pair(pg_session, "NOEVAL")
    assert cur.verdict is None and cur.posture is None
    res = d.compute("NOEVAL", cur, prior)
    assert "posture_change" not in [c.kind for c in res.changes]


def test_cache_invalidates_on_new_recommendation(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "CACHE")
    _mk_bar(pg_session, a.id)
    _rec_at(pg_session, a.id, 24, action="Buy")
    _rec_at(pg_session, a.id, 12, action="Buy")
    first = d.get_delta(pg_session, "CACHE")
    assert first is not None and "action" not in first["summary"].lower()
    _rec_at(pg_session, a.id, 1, action="Hold")     # newer insert
    second = d.get_delta(pg_session, "CACHE")
    assert second is not None
    assert second["current_as_of"] != first["current_as_of"]
    assert any(c["kind"] == "action_change" for c in second["changes"])


def test_public_payload_redaction(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "RED")
    _mk_bar(pg_session, a.id)
    r1 = _rec_at(pg_session, a.id, 24)
    r2 = _rec_at(pg_session, a.id, 2)
    out = d.get_delta(pg_session, "RED")
    blob = json.dumps(out)
    for leak in (r1.id, r2.id, a.id, "snapshot_hash", "git_sha",
                 "input_hash", "family_scores"):
        assert leak not in blob


def test_flag_off_route_absent_and_responses_untouched(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # flag default False → main.py never mounts the router (mount test is
    # structural); the recommendations list path contains no delta wiring.
    import inspect
    from apps.api.src.api import recommendations as rec_api
    assert settings.REC_DELTA_ENABLED is False
    src = inspect.getsource(rec_api)
    assert "delta" not in src.lower()


def test_query_bounds_per_delta(pg_session: Session) -> None:
    # Bounded query set: current+prior selection (2) + per-row facts
    # (outcome, maybe bar, verdict, maybe posture ≤4 each) → hard bound 10.
    a = _mk_asset(pg_session, "QB")
    _mk_bar(pg_session, a.id)
    _rec_at(pg_session, a.id, 24)
    _rec_at(pg_session, a.id, 2)
    counter = {"n": 0}
    from sqlalchemy import event as sa_event
    engine = pg_session.get_bind()

    def before_cursor(*a, **k):  # noqa: ANN002, ANN003
        counter["n"] += 1

    sa_event.listen(engine, "before_cursor_execute", before_cursor)
    try:
        d.reset_cache_for_tests()
        d.get_delta(pg_session, "QB")
    finally:
        sa_event.remove(engine, "before_cursor_execute", before_cursor)
    assert counter["n"] <= 10
