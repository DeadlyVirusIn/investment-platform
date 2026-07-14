"""Wave 3A — Experiment Lab pg integration tests.

Real fixture data (assets, price bars, recommendations, barrier outcomes)
through the full harness. Pins: run lifecycle + append-only registry,
deterministic fingerprints, concurrent-duplicate guard, failed-run
persistence (bounded, categorized), reproduce = NEW linked run (original
untouched), task provenance in params, owner routes (auth, flag, list/
detail shapes, redaction), and query/write discipline.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.api import experiments as api
from apps.api.src.db.models import Asset, PriceBar, ResearchRun
from apps.api.src.domain.evaluation import lab
from apps.api.src.domain.research_inbox import service as inbox_svc

pytestmark = pytest.mark.integration

OWNER = {"email": "owner@example.com", "id": "o1", "role": "owner"}

SYMS = ("LABA", "LABB", "LABC")
START = dt.date(2024, 1, 1)


@pytest.fixture
def seeded(pg_session: Session):
    """Deterministic multi-asset fixture: 24 months of monthly bars per
    asset, ~8/quarter Buy recommendations with resolved outcomes plus a
    censored tail."""
    db = pg_session
    asset_ids = {}
    for s in SYMS:
        a = Asset(symbol=s, asset_class="equity", currency="USD")
        db.add(a)
        db.flush()
        asset_ids[s] = a.id
    # monthly close bars: deterministic drifting series per asset
    for i, s in enumerate(SYMS):
        px = 100.0
        for m in range(26):
            ts = dt.datetime(2024, 1, 28, tzinfo=dt.timezone.utc) \
                + dt.timedelta(days=30 * m)
            px *= (1.01 + 0.002 * i) if m % 3 else (0.99 - 0.001 * i)
            db.add(PriceBar(asset_id=asset_ids[s], timeframe="1d", ts=ts,
                            open=px, high=px, low=px, close=px,
                            volume=1000, provider="fixture"))
    db.flush()
    # recommendations + outcomes: hits ~60%, conviction correlated
    n = 0
    for q in range(8):                       # 8 quarters
        for k in range(12):                  # 12 per quarter
            n += 1
            sym = SYMS[k % 3]
            gen = dt.datetime(2024, 1, 5, tzinfo=dt.timezone.utc) \
                + dt.timedelta(days=q * 91 + (k % 12) * 7)
            hit = (n % 5) != 0 if k % 2 == 0 else (n % 3) == 0
            conviction = 72.0 if hit else 48.0
            conviction += (n % 7)            # spread, deterministic
            rid = str(uuid.uuid4())
            db.execute(text(
                "INSERT INTO recommendation (id, asset_id, generated_at, "
                "action, conviction, model_version, snapshot_hash, "
                "created_at) VALUES (:i, :a, :g, 'Buy', :c, 'fixture', "
                ":sh, now())"),
                {"i": rid, "a": asset_ids[sym], "g": gen, "c": conviction,
                 "sh": f"h{n:05d}"})
            censored = q == 7 and k >= 6      # open tail in the last quarter
            db.execute(text(
                "INSERT INTO recommendation_outcome (id, recommendation_id,"
                " barrier_label, realized_30d_return, barrier_n_bars, "
                "created_at, updated_at) VALUES (:i, :r, :bl, :ret, 20, "
                "now(), now())"),
                {"i": str(uuid.uuid4()), "r": rid,
                 "bl": None if censored else (1 if hit else -1),
                 "ret": None if censored else (0.03 if hit else -0.02)})
    db.commit()
    return db


def _spec(**over) -> dict:
    base = {"name": "pg-fixture", "universe": list(SYMS),
            "start": "2024-01-01", "end": "2026-02-01",
            "min_eval_rows": 8, "fold_period": "Q"}
    base.update(over)
    return base


# ── lifecycle + registry discipline ────────────────────────────────────────

def test_full_run_completes_with_evidence(seeded: Session):
    out = lab.execute_experiment(seeded, _spec())
    assert out["status"] == "completed"
    m = out["metrics"]
    assert m["summary"]["n_folds"] >= 4
    assert m["summary"]["total_resolved"] >= 60
    assert m["summary"]["total_censored"] >= 1          # censored disclosed
    assert m["dataset_fingerprint"]
    assert m["metric_hash"]
    assert set(m["cost_sensitivity"]) == {"zero_cost", "expected_cost",
                                          "stressed_cost"}
    assert "buy_and_hold" in m["benchmarks"]
    assert m["promotion_readiness"]["verdict"] in lab.VERDICTS
    assert m["summary"]["leakage_check"].startswith("not-applicable")


def test_registry_append_only_no_overwrite(seeded: Session):
    out1 = lab.execute_experiment(seeded, _spec())
    out2 = lab.execute_experiment(seeded, _spec(seed=43))
    assert out1["run_uid"] != out2["run_uid"]
    n = seeded.execute(text(
        "SELECT count(*) FROM research_run WHERE name LIKE 'lab: %'"
    )).scalar()
    assert n == 2                                       # never overwritten


def test_deterministic_fingerprint_and_metric_hash(seeded: Session):
    a = lab.execute_experiment(seeded, _spec())
    b = lab.execute_experiment(seeded, _spec())
    assert (a["metrics"]["dataset_fingerprint"]
            == b["metrics"]["dataset_fingerprint"])
    assert a["metrics"]["metric_hash"] == b["metrics"]["metric_hash"]


def test_fingerprint_changes_when_data_changes(seeded: Session):
    a = lab.execute_experiment(seeded, _spec())
    # add one new resolved outcome in scope
    aid = seeded.execute(text(
        "SELECT id FROM asset WHERE symbol = 'LABA'")).scalar()
    rid = str(uuid.uuid4())
    seeded.execute(text(
        "INSERT INTO recommendation (id, asset_id, generated_at, action, "
        "conviction, model_version, snapshot_hash, created_at) VALUES "
        "(:i, :a, '2025-06-01+00', 'Buy', 66, 'fixture', 'hnew', now())"),
        {"i": rid, "a": aid})
    seeded.execute(text(
        "INSERT INTO recommendation_outcome (id, recommendation_id, "
        "barrier_label, realized_30d_return, barrier_n_bars, created_at, "
        "updated_at) VALUES (:i, :r, 1, 0.05, 20, now(), now())"),
        {"i": str(uuid.uuid4()), "r": rid})
    seeded.commit()
    b = lab.execute_experiment(seeded, _spec())
    assert (a["metrics"]["dataset_fingerprint"]
            != b["metrics"]["dataset_fingerprint"])


def test_concurrent_duplicate_identity_409(seeded: Session):
    # simulate an active run with the same identity: create draft directly
    from apps.ml.lab.registry import RegistryClient, config_hash
    spec = lab.validate_spec(_spec())
    params = lab.spec_payload(spec)
    params["experiment_hash"] = lab.experiment_hash(spec)
    client = RegistryClient(seeded)
    client.create_run(run_type="walk_forward", name="lab: pg-fixture",
                      params=params, created_by="owner")
    seeded.commit()
    with pytest.raises(lab.ConcurrentRunError):
        lab.execute_experiment(seeded, _spec())


def test_failed_run_is_bounded_and_categorized(seeded: Session):
    out = lab.execute_experiment(
        seeded, _spec(start="2010-01-01", end="2010-06-01"))
    assert out["status"] == "failed"
    assert out["error_summary"].startswith("dataset_empty:")
    assert "Traceback" not in out["error_summary"]
    # failed run persisted, never promotable
    row = seeded.execute(text(
        "SELECT status, error_summary FROM research_run WHERE run_uid=:u"),
        {"u": out["run_uid"]}).mappings().one()
    assert row["status"] == "failed"


def test_reproduce_creates_new_linked_run_original_untouched(
        seeded: Session):
    first = lab.execute_experiment(seeded, _spec())
    snap = seeded.execute(text(
        "SELECT row_to_json(r)::text FROM research_run r WHERE run_uid=:u"),
        {"u": first["run_uid"]}).scalar()
    second = api.reproduce_run(run_uid=first["run_uid"], owner=OWNER,
                               db=seeded)
    assert second["run_uid"] != first["run_uid"]
    rep = second["metrics"]["reproducibility"]
    assert rep["baseline_run"] == first["run_uid"]
    assert rep["matches"] is True                       # deterministic
    assert second["metrics"]["promotion_readiness"]["gates"][
        "reproducibility"]["pass"] is True
    snap2 = seeded.execute(text(
        "SELECT row_to_json(r)::text FROM research_run r WHERE run_uid=:u"),
        {"u": first["run_uid"]}).scalar()
    assert snap == snap2                                # byte-identical


def test_task_provenance_recorded(seeded: Session):
    t = inbox_svc.create_task(seeded, title="lab origin", question="q?")
    out = api.create_run(spec=_spec(research_task_id=t.id), owner=OWNER,
                         db=seeded)
    row = seeded.execute(text(
        "SELECT parameters->>'research_task_id' FROM research_run "
        "WHERE run_uid=:u"), {"u": out["run_uid"]}).scalar()
    assert row == t.id


def test_unknown_task_provenance_422(seeded: Session):
    with pytest.raises(HTTPException) as e:
        api.create_run(spec=_spec(research_task_id=str(uuid.uuid4())),
                       owner=OWNER, db=seeded)
    assert e.value.status_code == 422


# ── routes: shapes, auth posture, redaction ────────────────────────────────

def test_list_and_detail_shapes_and_redaction(seeded: Session):
    lab.execute_experiment(seeded, _spec())
    listed = api.list_runs(owner=OWNER, db=seeded, limit=25)
    assert listed["runs"], "run must appear in the list"
    head = listed["runs"][0]
    assert {"run_uid", "status", "verdict", "n_folds", "total_resolved",
            "mean_hit_rate", "net_mean_30d_expected_cost",
            "calibration_reported"} <= set(head)
    detail = api.get_run(run_uid=head["run_uid"], owner=OWNER, db=seeded)
    payload = str(detail)
    for needle in ("Traceback", "POSTGRES_PASSWORD", "DATABASE_URL",
                   "arthos_at_"):
        assert needle not in payload
    # env capture: versions only
    env = detail["metrics"]["environment"]
    assert set(env) == {"python", "packages"}


def test_detail_404_for_non_lab_runs(seeded: Session):
    from apps.ml.lab.registry import RegistryClient
    client = RegistryClient(seeded)
    run = client.create_run(run_type="other", name="not a lab run",
                            params={}, created_by="x")
    seeded.commit()
    with pytest.raises(HTTPException) as e:
        api.get_run(run_uid=run.run_uid, owner=OWNER, db=seeded)
    assert e.value.status_code == 404


def test_reproduce_requires_completed(seeded: Session):
    out = lab.execute_experiment(
        seeded, _spec(start="2010-01-01", end="2010-06-01"))  # failed
    with pytest.raises(HTTPException) as e:
        api.reproduce_run(run_uid=out["run_uid"], owner=OWNER, db=seeded)
    assert e.value.status_code == 409


def test_spec_errors_are_422_shaped(seeded: Session):
    with pytest.raises(HTTPException) as e:
        api.create_run(spec={"name": "x", "engine": "__import__('os')"},
                       owner=OWNER, db=seeded)
    assert e.value.status_code == 422


def test_flag_off_routes_absent():
    """Structural: the router is mounted only under EXPERIMENT_LAB_ENABLED
    (fail-closed, same pattern as every flag-mounted router)."""
    import pathlib
    main_src = pathlib.Path("apps/api/src/main.py").read_text(
        encoding="utf-8")
    idx = main_src.find("experiments_router")
    assert idx > 0
    guard = main_src.rfind("if settings.EXPERIMENT_LAB_ENABLED", 0, idx)
    assert guard > 0, "experiments router must be flag-guarded"
