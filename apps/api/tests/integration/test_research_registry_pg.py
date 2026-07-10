"""Integration tests (pg) — research_run registry write path.

Exercises RegistryClient through the apps.api shim
(apps.api.src.ml.registry_client) against real Postgres: lifecycle state
machine, append-only metrics, terminal freeze, error-summary cap,
parent/child lineage, config-hash determinism, artifact manifest sha256,
and end-to-end reproducibility (same params+seed ⇒ same config_hash and
identical metrics from a seeded deterministic computation).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re

import numpy as np
import pytest

from apps.api.src.ml.registry_client import (
    ERROR_SUMMARY_MAX_CHARS,
    InvalidTransitionError,
    MetricOverwriteError,
    RegistryClient,
    RegistryError,
    RunFrozenError,
    config_hash,
)
from apps.ml.lab import metrics as lab_metrics

RUN_UID_RE = re.compile(r"^rr_\d{8}_[0-9a-f]{8}$")


def _mk(client: RegistryClient, **overrides):
    kwargs = dict(
        run_type="calibration",
        name="registry pg test run",
        params={"alpha_param": 1, "beta_param": "x"},
        git_sha="deadbeef" * 5,
        seed=42,
    )
    kwargs.update(overrides)
    return client.create_run(**kwargs)


def test_lifecycle_metrics_append_only_then_freeze(pg_session):
    client = RegistryClient(pg_session)
    run = _mk(client)

    assert run.status == "draft"
    assert RUN_UID_RE.match(run.run_uid)
    assert re.fullmatch(r"[0-9a-f]{64}", run.config_hash)
    assert run.metrics == {}

    client.start(run)
    assert run.status == "running"
    assert run.started_at is not None
    with pytest.raises(InvalidTransitionError):
        client.start(run)  # running → running is not a transition

    client.append_metrics(run, {"n_rows": 10})
    client.append_metrics(run, {"auc": 0.61, "brier": None})
    assert run.metrics == {"n_rows": 10, "auc": 0.61, "brier": None}

    # append-only: existing key can never be overwritten (even same value)
    with pytest.raises(MetricOverwriteError):
        client.append_metrics(run, {"n_rows": 10})
    with pytest.raises(MetricOverwriteError):
        client.append_metrics(run, {"auc": 0.99, "fresh_key": 1})
    assert "fresh_key" not in run.metrics  # partial merges never land

    client.finish(run, metrics={"ece": 0.05})
    assert run.status == "completed"
    assert run.completed_at is not None

    # terminal = frozen: client refuses any further metric append
    with pytest.raises(RunFrozenError):
        client.append_metrics(run, {"late_key": 1})
    with pytest.raises(InvalidTransitionError):
        client.finish(run)
    with pytest.raises(RunFrozenError):
        client.fail(run, "too late")

    pg_session.commit()
    reloaded = client.get_run(run.run_uid)
    assert reloaded.metrics == {"n_rows": 10, "auc": 0.61, "brier": None, "ece": 0.05}


def test_draft_cannot_finish_and_metrics_reject_nan(pg_session):
    client = RegistryClient(pg_session)
    run = _mk(client)
    with pytest.raises(InvalidTransitionError):
        client.finish(run)  # draft → completed skips running
    client.start(run)
    with pytest.raises(ValueError):  # NaN has no canonical JSON form
        client.append_metrics(run, {"bad": float("nan")})


def test_failure_path_caps_error_summary(pg_session):
    client = RegistryClient(pg_session)
    run = _mk(client)
    client.start(run)
    client.fail(run, "boom " * 1000)  # 5000 chars
    assert run.status == "failed"
    assert len(run.error_summary) == ERROR_SUMMARY_MAX_CHARS
    assert run.completed_at is not None
    with pytest.raises(RunFrozenError):
        client.fail(run, "again")

    run2 = _mk(client)
    client.start(run2)
    with pytest.raises(RegistryError):
        client.fail(run2, "")  # failures must explain themselves


def test_parent_child_lineage(pg_session):
    client = RegistryClient(pg_session)
    parent = _mk(client, run_type="optuna_study", name="parent study")
    child = _mk(
        client, run_type="optuna_trial", name="trial 0",
        params={"max_depth": 6}, parent_run_id=parent.id,
    )
    assert child.parent_run_id == parent.id
    assert child.run_uid != parent.run_uid

    with pytest.raises(RegistryError):
        _mk(client, parent_run_id="00000000-0000-0000-0000-000000000000")
    with pytest.raises(RegistryError):
        _mk(client, run_type="not_a_type")


def test_config_hash_deterministic_and_param_sensitive(pg_session):
    client = RegistryClient(pg_session)
    a = _mk(client, params={"n_splits": 8, "embargo_days": 10})
    b = _mk(client, params={"embargo_days": 10, "n_splits": 8})  # key order
    c = _mk(client, params={"n_splits": 8, "embargo_days": 11})
    assert a.config_hash == b.config_hash
    assert a.config_hash != c.config_hash
    assert config_hash({"n_splits": 8, "embargo_days": 10}) == a.config_hash


def test_artifact_manifest_sha256_and_terminal_availability(pg_session, tmp_path):
    client = RegistryClient(pg_session)
    run = _mk(client)
    client.start(run)

    payload = b"fold,auc\n0,0.61\n"
    art = tmp_path / "folds.csv"
    art.write_bytes(payload)

    entry = client.add_artifact(run, str(art), kind="fold_results")
    assert entry["sha256"] == hashlib.sha256(payload).hexdigest()
    assert entry["bytes"] == len(payload)
    assert entry["available"] is True

    with pytest.raises(RegistryError):  # manifest is append-only per path
        client.add_artifact(run, str(art), kind="fold_results")

    missing = client.add_artifact(run, str(tmp_path / "gone.parquet"))
    assert missing["available"] is False
    assert missing["sha256"] is None

    client.finish(run)
    with pytest.raises(RunFrozenError):
        client.add_artifact(run, str(tmp_path / "late.json"))
    # the ONE legal terminal mutation: availability is a fact about the disk
    client.set_artifact_available(run, str(art), False)
    pg_session.commit()
    reloaded = client.get_run(run.run_uid)
    flags = {e["path"]: e["available"] for e in reloaded.artifact_manifest}
    assert flags[str(art)] is False


def test_data_window_and_data_hash_recorded(pg_session):
    client = RegistryClient(pg_session)
    manifest = {"table": "historical_label", "n_rows": 123,
                "date_min": "2024-01-02", "date_max": "2025-06-30"}
    run = _mk(
        client,
        data_window=(dt.date(2024, 1, 2), dt.date(2025, 6, 30)),
        data_manifest=manifest,
    )
    assert run.data_start == dt.date(2024, 1, 2)
    assert run.data_end == dt.date(2025, 6, 30)
    assert re.fullmatch(r"[0-9a-f]{64}", run.data_hash)
    # same manifest → same hash; window shift → different hash
    run2 = _mk(client, data_manifest=dict(manifest))
    assert run2.data_hash == run.data_hash
    run3 = _mk(client, data_manifest={**manifest, "date_max": "2025-07-01"})
    assert run3.data_hash != run.data_hash


def _tiny_deterministic_training(seed: int) -> dict:
    """Seeded numpy stand-in for a training loop: same seed ⇒ bit-identical
    metrics. No fitting library needed — the point is reproducibility of
    the recorded numbers, not model quality."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=200)
    y = (x + rng.normal(scale=0.5, size=200) > 0).astype(int)
    p = 1.0 / (1.0 + np.exp(-x))
    return {
        "auc": lab_metrics.auc(y, p),
        "brier": lab_metrics.brier(y, p),
        "ece": lab_metrics.ece(y, p),
        "n_rows": int(len(y)),
    }


def test_reproducibility_same_params_seed_same_hash_and_metrics(pg_session):
    client = RegistryClient(pg_session)
    params = {"model": "tiny_sim", "n_rows": 200, "noise_scale": 0.5}

    uids = []
    for _ in range(2):
        run = client.create_run(
            run_type="walk_forward", name="reproducibility check",
            params=dict(params), git_sha="cafebabe" * 5, seed=1337,
        )
        client.start(run)
        client.append_metrics(run, _tiny_deterministic_training(seed=1337))
        client.finish(run)
        uids.append(run.run_uid)
    pg_session.commit()

    first, second = (client.get_run(u) for u in uids)
    assert first.run_uid != second.run_uid          # distinct ledger rows
    assert first.config_hash == second.config_hash  # same experiment identity
    assert first.random_seed == second.random_seed == 1337
    assert first.metrics == second.metrics          # bit-identical metrics
