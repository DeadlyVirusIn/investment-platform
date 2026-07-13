"""Publication Preflight — persistence + publication-seam invariants (pg).

Pins (Wave 1A):
  * idempotency: identical (recommendation, rule set, input hash) persists
    exactly one row, including under a concurrency-shaped double insert;
  * append-only history: changed inputs append a NEW row; the service module
    exposes no UPDATE/DELETE against recommendation_preflight
    (introspection, inbox precedent);
  * DB layer: verdict CHECK rejects unknown verdicts; unique idempotency key
    enforced; FK refuses deleting a recommendation that has verdicts;
  * ensure_current_verdict: returns the row matching the CURRENT input hash,
    re-evaluates when facts move, and fails CLOSED (synthetic HOLD) when the
    evaluator raises;
  * publication seam: with the flag ON, GET /recommendations hides
    HOLD/BLOCKED and embeds the redacted projection; with the flag OFF the
    payload is byte-identical to legacy (no preflight key, nothing hidden);
  * reads that must never be affected: paper portfolio/canonical endpoints
    ignore preflight entirely (no code path touches them — asserted by
    module introspection).
"""

from __future__ import annotations

import datetime
import inspect
import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db.models import (
    Asset,
    PriceBar,
    Recommendation,
    RecommendationPreflight,
)
from apps.api.src.domain.publication import preflight as pf

pytestmark = pytest.mark.integration


def _mk_asset(db: Session, symbol: str = "GE") -> Asset:
    a = Asset(id=str(uuid.uuid4()), symbol=symbol, name=f"{symbol} Test Co",
              asset_class="equity")
    db.add(a)
    db.flush()
    return a


def _mk_bar(db: Session, asset_id: str, ts: datetime.datetime | None = None) -> None:
    db.add(PriceBar(
        id=str(uuid.uuid4()), asset_id=asset_id, timeframe="1d",
        ts=ts or datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=8),
        open=100, high=101, low=99, close=100.5, provider="test",
    ))
    db.flush()


def _mk_rec(db: Session, asset_id: str, **kw) -> Recommendation:
    rationale = {
        "confidence_label": "High", "enough_data": True, "stale_data": False,
        "thesis": "Trend supportive.",
        "family_scores": {"trend_momentum": "0.7", "volatility_risk": "-0.2"},
    }
    rationale.update(kw.pop("rationale", {}))
    snap = kw.pop("snapshot_hash", uuid.uuid4().hex[:16])
    rationale.setdefault("snapshot_hash", snap)
    r = Recommendation(
        id=str(uuid.uuid4()), asset_id=asset_id, action=kw.pop("action", "Buy"),
        conviction=66, rationale=json.dumps(rationale),
        model_version="0.1.0-test", snapshot_hash=snap,
        generated_at=kw.pop(
            "generated_at",
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=2),
        ),
    )
    db.add(r)
    db.flush()
    return r


def _seed_ingest_success(db: Session) -> None:
    sid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO job_schedule (id, name, cron_expr, enabled, next_run_at, "
        "created_at, updated_at) "
        "VALUES (:i, 'ingest_prices_daily', '0 1 * * *', true, "
        "now() + interval '1 hour', now(), now()) "
        "ON CONFLICT DO NOTHING"
    ), {"i": sid})
    real_sid = db.execute(text(
        "SELECT id FROM job_schedule WHERE name='ingest_prices_daily' LIMIT 1"
    )).scalar()
    db.execute(text(
        "INSERT INTO job_run (id, job_schedule_id, started_at, finished_at, "
        "status) VALUES (:i, :s, now() - interval '2 hours', "
        "now() - interval '1 hour', 'success')"
    ), {"i": str(uuid.uuid4()), "s": real_sid})
    db.flush()


def _healthy_candidate(db: Session) -> Recommendation:
    a = _mk_asset(db, "GE")
    _mk_bar(db, a.id)
    _seed_ingest_success(db)
    return _mk_rec(db, a.id)


# ---------------------------------------------------------------------------
# persistence invariants
# ---------------------------------------------------------------------------

def test_idempotent_same_input_single_row(pg_session: Session) -> None:
    rec = _healthy_candidate(pg_session)
    r1 = pf.run_and_persist(pg_session, rec)
    r2 = pf.run_and_persist(pg_session, rec)
    assert r1["id"] == r2["id"]
    n = pg_session.execute(text(
        "SELECT count(*) FROM recommendation_preflight WHERE "
        "recommendation_id=:r"), {"r": rec.id}).scalar()
    assert n == 1
    assert r1["verdict"] == "READY_WITH_LIMITATIONS"


def test_concurrent_shaped_double_insert_resolves_to_one_row(
    pg_session: Session,
) -> None:
    rec = _healthy_candidate(pg_session)
    inp = pf.load_inputs(pg_session, rec)
    res = pf.evaluate(inp)
    # Two writers race: both use ON CONFLICT DO NOTHING on the same key.
    for _ in range(2):
        pg_session.execute(text(
            "INSERT INTO recommendation_preflight (id, recommendation_id, "
            "verdict, rule_set_version, input_hash, checks_json, "
            "limitations_json, blocking_reasons_json, evaluated_at, "
            "evaluator_git_sha, created_at) VALUES (:i, :r, :v, :rsv, :h, "
            "'[]', '[]', '[]', now(), 'test', now()) "
            "ON CONFLICT (recommendation_id, rule_set_version, input_hash) "
            "DO NOTHING"
        ), {"i": str(uuid.uuid4()), "r": rec.id, "v": res.verdict,
            "rsv": res.rule_set_version, "h": res.input_hash})
    pg_session.flush()
    n = pg_session.execute(text(
        "SELECT count(*) FROM recommendation_preflight WHERE "
        "recommendation_id=:r AND input_hash=:h"),
        {"r": rec.id, "h": res.input_hash}).scalar()
    assert n == 1


def test_changed_input_appends_new_row_history_intact(
    pg_session: Session,
) -> None:
    rec = _healthy_candidate(pg_session)
    first = pf.run_and_persist(pg_session, rec)
    # Facts move: a newer bar lands → different input hash.
    _mk_bar(pg_session, rec.asset_id,
            ts=datetime.datetime.now(datetime.timezone.utc))
    second = pf.run_and_persist(pg_session, rec)
    assert first["input_hash"] != second["input_hash"]
    rows = pg_session.execute(text(
        "SELECT id, checks_json FROM recommendation_preflight WHERE "
        "recommendation_id=:r ORDER BY created_at"), {"r": rec.id}).all()
    assert len(rows) == 2
    # first row untouched
    assert rows[0][0] == first["id"]
    assert rows[0][1] == first["checks_json"]


def test_service_module_has_no_update_or_delete_path() -> None:
    src = inspect.getsource(pf)
    assert "UPDATE recommendation_preflight" not in src
    assert "DELETE FROM recommendation_preflight" not in src


def test_verdict_check_constraint_rejects_unknown(pg_session: Session) -> None:
    rec = _healthy_candidate(pg_session)
    with pytest.raises(Exception, match="ck_rec_preflight_verdict|CheckViolation"):
        pg_session.execute(text(
            "INSERT INTO recommendation_preflight (id, recommendation_id, "
            "verdict, rule_set_version, input_hash, checks_json, "
            "limitations_json, blocking_reasons_json, evaluated_at, "
            "evaluator_git_sha, created_at) VALUES (:i, :r, 'MAYBE', 'pf-1', "
            "'h', '[]', '[]', '[]', now(), 'test', now())"
        ), {"i": str(uuid.uuid4()), "r": rec.id})
        pg_session.flush()
    pg_session.rollback()


def test_fk_refuses_recommendation_delete_with_verdicts(
    pg_session: Session,
) -> None:
    rec = _healthy_candidate(pg_session)
    pf.run_and_persist(pg_session, rec)
    with pytest.raises(Exception, match="foreign key|ForeignKeyViolation"):
        pg_session.execute(text(
            "DELETE FROM recommendation WHERE id=:r"), {"r": rec.id})
        pg_session.flush()
    pg_session.rollback()


# ---------------------------------------------------------------------------
# ensure_current_verdict — the publication-transaction guarantee
# ---------------------------------------------------------------------------

def test_ensure_current_matches_exact_hash_and_reevaluates_on_change(
    pg_session: Session,
) -> None:
    rec = _healthy_candidate(pg_session)
    v1 = pf.ensure_current_verdict(pg_session, rec)
    v1_again = pf.ensure_current_verdict(pg_session, rec)
    assert v1["input_hash"] == v1_again["input_hash"]
    _mk_bar(pg_session, rec.asset_id,
            ts=datetime.datetime.now(datetime.timezone.utc))
    v2 = pf.ensure_current_verdict(pg_session, rec)
    assert v2["input_hash"] != v1["input_hash"]


def test_evaluator_exception_fails_closed_to_hold(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = _healthy_candidate(pg_session)

    def boom(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("synthetic evaluator failure")

    monkeypatch.setattr(pf, "load_inputs", boom)
    row = pf.ensure_current_verdict(pg_session, rec)
    assert row["verdict"] == "HOLD"
    assert row.get("synthetic") is True


# ---------------------------------------------------------------------------
# verdict correctness against real stored facts
# ---------------------------------------------------------------------------

def test_missing_price_data_blocks(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "NOPX")
    _seed_ingest_success(pg_session)
    rec = _mk_rec(pg_session, a.id)          # no bar seeded
    row = pf.run_and_persist(pg_session, rec)
    assert row["verdict"] == "BLOCKED"
    blocks = json.loads(row["blocking_reasons_json"])
    assert any(c["check_id"] == "price_data_exists" for c in blocks)


def test_stale_bar_holds(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "OLDY")
    _mk_bar(pg_session, a.id,
            ts=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=12))
    _seed_ingest_success(pg_session)
    rec = _mk_rec(pg_session, a.id)
    row = pf.run_and_persist(pg_session, rec)
    assert row["verdict"] == "HOLD"


def test_no_ingest_history_fails_closed_to_hold(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "NOJOB")
    _mk_bar(pg_session, a.id)
    rec = _mk_rec(pg_session, a.id)          # no job_run seeded
    row = pf.run_and_persist(pg_session, rec)
    assert row["verdict"] == "HOLD"


def test_newer_recommendation_blocks_older_candidate(
    pg_session: Session,
) -> None:
    a = _mk_asset(pg_session, "DUPE")
    _mk_bar(pg_session, a.id)
    _seed_ingest_success(pg_session)
    old = _mk_rec(pg_session, a.id, generated_at=datetime.datetime.now(
        datetime.timezone.utc) - datetime.timedelta(days=1))
    _mk_rec(pg_session, a.id)                # newer sibling
    row = pf.run_and_persist(pg_session, old)
    assert row["verdict"] == "BLOCKED"
    blocks = json.loads(row["blocking_reasons_json"])
    assert any(c["check_id"] == "no_duplicate_open_idea" for c in blocks)


def test_posture_safe_holds_new_publication(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SYSTEM_POSTURE_OVERRIDE", "SAFE",
                        raising=False)
    rec = _healthy_candidate(pg_session)
    row = pf.run_and_persist(pg_session, rec)
    assert row["verdict"] == "HOLD"


def test_prohibited_language_blocks(pg_session: Session) -> None:
    a = _mk_asset(pg_session, "HYPE")
    _mk_bar(pg_session, a.id)
    _seed_ingest_success(pg_session)
    rec = _mk_rec(pg_session, a.id,
                  rationale={"thesis": "This trade is guaranteed to win."})
    row = pf.run_and_persist(pg_session, rec)
    assert row["verdict"] == "BLOCKED"


# ---------------------------------------------------------------------------
# publication seam (flag behavior) — via the route function directly
# ---------------------------------------------------------------------------

def _list_payload(db: Session) -> dict:
    from apps.api.src.api.recommendations import list_recommendations
    return list_recommendations(latest=True, sort_by="generated_at",
                                order="desc", limit=100, session=db)


def test_flag_off_parity_no_preflight_key_nothing_hidden(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RECOMMENDATION_PREFLIGHT_ENABLED", False,
                        raising=False)
    a = _mk_asset(pg_session, "NOPF")
    rec = _mk_rec(pg_session, a.id)          # would BLOCK if gated (no bar)
    out = _list_payload(pg_session)
    ids = [r["id"] for r in out["recommendations"]]
    assert rec.id in ids
    assert all("preflight" not in r for r in out["recommendations"])
    n = pg_session.execute(
        text("SELECT count(*) FROM recommendation_preflight")).scalar()
    assert n == 0                             # flag off → no evaluation ran


def test_flag_on_hides_hold_blocked_and_embeds_projection(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RECOMMENDATION_PREFLIGHT_ENABLED", True,
                        raising=False)
    good = _healthy_candidate(pg_session)
    bad_asset = _mk_asset(pg_session, "BADX")
    bad = _mk_rec(pg_session, bad_asset.id)   # no bar → BLOCKED
    out = _list_payload(pg_session)
    ids = [r["id"] for r in out["recommendations"]]
    assert good.id in ids and bad.id not in ids
    good_payload = next(r for r in out["recommendations"] if r["id"] == good.id)
    proj = good_payload["preflight"]
    assert proj["verdict"] == "READY_WITH_LIMITATIONS"
    assert set(proj.keys()) == {"verdict", "limitations", "evaluated_at",
                                "freshness_summary"}
    blob = json.dumps(proj)
    assert "input_hash" not in blob and "check_id" not in blob
    # BLOCKED candidate stays owner-visible in the ledger, not deleted
    assert pg_session.execute(text(
        "SELECT verdict FROM recommendation_preflight WHERE "
        "recommendation_id=:r ORDER BY created_at DESC LIMIT 1"),
        {"r": bad.id}).scalar() == "BLOCKED"
    assert pg_session.get(Recommendation, bad.id) is not None


def test_gate_never_touches_paper_or_portfolio_modules() -> None:
    # Import/call-level isolation: the gate must never couple to paper
    # execution or portfolio state (prose mentions in docstrings are fine).
    src = inspect.getsource(pf)
    for token in ("paper_trading", "paper_service", "paper_execution",
                  "exit_cycle", "submit_trade", "PaperTrade",
                  "paper_portfolio"):
        assert token not in src, f"preflight must not couple to {token}"


def test_orm_model_matches_migration_uniques(pg_session: Session) -> None:
    cols = {c.name for c in RecommendationPreflight.__table__.columns}
    assert {"id", "recommendation_id", "verdict", "rule_set_version",
            "input_hash", "checks_json", "limitations_json",
            "blocking_reasons_json", "evaluated_at", "evaluator_git_sha",
            "source_freshness_at", "created_at"} <= cols


def test_bulk_loader_parity_with_single(pg_session: Session) -> None:
    """The bulk publication path must build byte-identical inputs (same
    hash, same verdict) as the audited single-candidate loader."""
    from apps.api.src.domain.publication.preflight import (
        _bulk_load_inputs,
        ensure_current_verdicts_bulk,
    )
    rec = _healthy_candidate(pg_session)
    single = pf.load_inputs(pg_session, rec)
    bulk = _bulk_load_inputs(pg_session, [rec])[rec.id]
    assert bulk.input_hash() == single.input_hash()
    assert pf.evaluate(bulk).verdict == pf.evaluate(single).verdict
    rows = ensure_current_verdicts_bulk(pg_session, [rec])
    assert rows[rec.id]["verdict"] == pf.evaluate(single).verdict
    # idempotent second call reuses the stored row
    rows2 = ensure_current_verdicts_bulk(pg_session, [rec])
    assert rows2[rec.id]["id"] == rows[rec.id]["id"]


def test_bulk_loader_fails_closed(pg_session: Session,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.api.src.domain.publication import preflight as _pf

    def boom(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("synthetic bulk failure")

    rec = _healthy_candidate(pg_session)
    monkeypatch.setattr(_pf, "_bulk_load_inputs", boom)
    rows = _pf.ensure_current_verdicts_bulk(pg_session, [rec])
    assert rows[rec.id]["verdict"] == "HOLD"
    assert rows[rec.id].get("synthetic") is True


def test_bulk_cap_bounds_cold_evaluations_not_lookups(
    pg_session: Session,
) -> None:
    """The per-request cap limits COLD evaluations only; already-verdicted
    candidates resolve by lookup and capped-out ones fail closed to HOLD."""
    from apps.api.src.domain.publication.preflight import (
        ensure_current_verdicts_bulk,
    )
    a1 = _mk_asset(pg_session, "CAPA")
    a2 = _mk_asset(pg_session, "CAPB")
    for a in (a1, a2):
        _mk_bar(pg_session, a.id)
    _seed_ingest_success(pg_session)
    r1 = _mk_rec(pg_session, a1.id)
    r2 = _mk_rec(pg_session, a2.id)
    # pre-verdict r1, then cap evaluations at 0: r1 resolves by lookup,
    # r2 fails closed (capped), neither silently dropped.
    ensure_current_verdicts_bulk(pg_session, [r1])
    rows = ensure_current_verdicts_bulk(pg_session, [r1, r2],
                                        max_evaluations=0)
    assert set(rows) == {r1.id, r2.id}
    assert rows[r1.id]["verdict"] == "READY_WITH_LIMITATIONS"
    assert rows[r2.id]["verdict"] == "HOLD"
    assert rows[r2.id].get("capped") is True
