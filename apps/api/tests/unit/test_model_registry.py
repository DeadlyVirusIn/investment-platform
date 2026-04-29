"""Phase 11T.1 - model_registry unit tests."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from apps.api.src.ml import model_registry as reg_mod
from apps.api.src.ml.model_registry import (
    ALLOWED_STATUS,
    DuplicateModelIdError,
    ModelRegistryError,
    REGISTRY_VERSION,
    RegistrationRequest,
    list_entries,
    register,
    show_entry,
)


class _StubEstimator:
    """Module-scope stub so joblib/pickle can resolve the class."""
    classes_ = ["negative", "neutral", "positive"]

    def predict_proba(self, X):
        import numpy as np
        return np.zeros((len(X), 3)) + 0.33


def _stub_pickle(path: Path, *, model_type="logreg", task="classification"):
    """Build a tiny pickle that mimics the 11S artifact shape."""
    import joblib
    payload = {
        "model": _StubEstimator(),
        "preprocessor": None,
        "feature_names": ["ctx_rates_calm"],
        "task": task,
        "target": "outcome_class",
        "model_type": model_type,
        "model_params": {"C": 1.0},
        "trained_on": {
            "dataset_path": "data/exports/foo.parquet",
            "dataset_checksum_sha256": "abc",
            "train_range": {"start": "2021-01-01", "end": "2024-12-31"},
            "n_train": 1000,
            "random_state": 1729,
        },
        "trained_at": "2026-04-30T03:30:00Z",
        "model_version": "ml-v1.0.0",
        "label_version": "label-v1.0.0",
        "dataset_version": "dataset-v1.0.0",
    }
    joblib.dump(payload, path)


def _stub_report(path: Path, *, model_type="logreg",
                 task="classification"):
    body = {
        "model_version": "ml-v1.0.0",
        "model_type": model_type,
        "task": task,
        "target": "outcome_class",
        "trained_at": "2026-04-30T03:30:00Z",
        "dataset": {
            "id": "dataset-2021-04-28_2026-04-08-dataset-v1.0.0",
            "n_rows": 1000,
            "n_features": 1,
            "checksum_sha256": "abc",
        },
        "splits": {
            "train":   {"end": "2024-12-31", "n": 800},
            "test":    {"start": "2025-01-01", "end": "2025-12-31",
                        "n": 150},
            "holdout": {"start": "2026-01-01", "end": "2026-04-08",
                        "n": 50},
        },
        "metrics": {
            "test":    {"auc_macro": 0.6, "accuracy": 0.55,
                        "brier_score": 0.21},
            "holdout": {"auc_macro": 0.58, "accuracy": 0.53,
                        "brier_score": 0.22},
        },
    }
    path.write_text(json.dumps(body), encoding="utf-8")


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def test_registry_load_empty_returns_empty_list(tmp_path):
    p = tmp_path / "registry.json"
    assert list_entries(registry_path=p) == []


def test_registry_load_round_trips_entry(tmp_path):
    p = tmp_path / "registry.json"
    p.write_text(json.dumps([{"model_id": "a", "status": "shadow_only"}]))
    out = list_entries(registry_path=p)
    assert out == [{"model_id": "a", "status": "shadow_only"}]


def test_registry_show_returns_full_entry(tmp_path):
    p = tmp_path / "registry.json"
    p.write_text(json.dumps([{"model_id": "x", "status": "shadow_only"}]))
    e = show_entry("x", registry_path=p)
    assert e == {"model_id": "x", "status": "shadow_only"}


def test_registry_show_missing_returns_none(tmp_path):
    p = tmp_path / "registry.json"
    p.write_text(json.dumps([]))
    assert show_entry("missing", registry_path=p) is None


def test_registry_list_returns_all_entries(tmp_path):
    p = tmp_path / "registry.json"
    p.write_text(
        json.dumps([
            {"model_id": "a", "status": "shadow_only"},
            {"model_id": "b", "status": "shadow_only"},
        ])
    )
    assert len(list_entries(registry_path=p)) == 2


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def test_registry_register_dry_run_writes_no_file(tmp_path):
    pickle = tmp_path / "m.pkl"
    report = tmp_path / "r.json"
    _stub_pickle(pickle)
    _stub_report(report)
    reg = tmp_path / "registry.json"
    entry = register(
        RegistrationRequest(pickle_path=pickle, report_path=report),
        registry_path=reg, dry_run=True,
        now_utc=dt.datetime(2026, 4, 30, 3, 30, tzinfo=dt.timezone.utc),
    )
    assert entry["model_type"] == "logreg"
    assert not reg.exists()


def test_registry_register_commit_writes_file(tmp_path):
    pickle = tmp_path / "m.pkl"
    report = tmp_path / "r.json"
    _stub_pickle(pickle)
    _stub_report(report)
    reg = tmp_path / "registry.json"
    register(
        RegistrationRequest(pickle_path=pickle, report_path=report),
        registry_path=reg, dry_run=False,
        now_utc=dt.datetime(2026, 4, 30, 3, 30, tzinfo=dt.timezone.utc),
    )
    assert reg.exists()
    out = json.loads(reg.read_text(encoding="utf-8"))
    assert len(out) == 1
    assert out[0]["status"] == "shadow_only"


def test_registry_register_appends(tmp_path):
    p1 = tmp_path / "a.pkl"
    p2 = tmp_path / "b.pkl"
    r1 = tmp_path / "a.json"
    r2 = tmp_path / "b.json"
    _stub_pickle(p1, model_type="logreg")
    _stub_pickle(p2, model_type="gbm")
    _stub_report(r1, model_type="logreg")
    _stub_report(r2, model_type="gbm")
    reg = tmp_path / "registry.json"
    register(
        RegistrationRequest(pickle_path=p1, report_path=r1),
        registry_path=reg, dry_run=False,
        now_utc=dt.datetime(2026, 4, 30, 3, 30, tzinfo=dt.timezone.utc),
    )
    register(
        RegistrationRequest(pickle_path=p2, report_path=r2),
        registry_path=reg, dry_run=False,
        now_utc=dt.datetime(2026, 4, 30, 4, 0, tzinfo=dt.timezone.utc),
    )
    out = json.loads(reg.read_text(encoding="utf-8"))
    assert len(out) == 2


def test_registry_register_refuses_duplicate_model_id(tmp_path):
    p = tmp_path / "m.pkl"
    r = tmp_path / "r.json"
    _stub_pickle(p)
    _stub_report(r)
    reg = tmp_path / "registry.json"
    when = dt.datetime(2026, 4, 30, 3, 30, tzinfo=dt.timezone.utc)
    register(
        RegistrationRequest(pickle_path=p, report_path=r),
        registry_path=reg, dry_run=False, now_utc=when,
    )
    with pytest.raises(DuplicateModelIdError):
        register(
            RegistrationRequest(pickle_path=p, report_path=r),
            registry_path=reg, dry_run=False, now_utc=when,
        )


def test_registry_status_frozen_at_shadow_only():
    assert ALLOWED_STATUS == ("shadow_only",)


def test_registry_register_records_artifact_checksum(tmp_path):
    p = tmp_path / "m.pkl"
    r = tmp_path / "r.json"
    _stub_pickle(p)
    _stub_report(r)
    reg = tmp_path / "registry.json"
    entry = register(
        RegistrationRequest(pickle_path=p, report_path=r),
        registry_path=reg, dry_run=True,
    )
    assert isinstance(entry["artifact_checksum_sha256"], str)
    assert len(entry["artifact_checksum_sha256"]) == 64


def test_registry_register_records_dataset_checksum(tmp_path):
    p = tmp_path / "m.pkl"
    r = tmp_path / "r.json"
    _stub_pickle(p)
    _stub_report(r)
    reg = tmp_path / "registry.json"
    entry = register(
        RegistrationRequest(pickle_path=p, report_path=r),
        registry_path=reg, dry_run=True,
    )
    assert entry["training_dataset_checksum_sha256"] == "abc"


def test_registry_register_records_created_at_utc(tmp_path):
    p = tmp_path / "m.pkl"
    r = tmp_path / "r.json"
    _stub_pickle(p)
    _stub_report(r)
    reg = tmp_path / "registry.json"
    entry = register(
        RegistrationRequest(pickle_path=p, report_path=r),
        registry_path=reg, dry_run=True,
        now_utc=dt.datetime(2026, 4, 30, 3, 30, tzinfo=dt.timezone.utc),
    )
    assert entry["created_at"].endswith("+00:00")


def test_registry_no_db_imports():
    src = Path(reg_mod.__file__).read_text(encoding="utf-8")
    for tok in (
        "from apps.api.src.db", "INSERT INTO",
        "session.execute", "sqlalchemy",
    ):
        assert tok not in src, (
            f"registry must not touch DB: {tok!r}"
        )


def test_registry_no_delete_method_exposed():
    """No public delete/edit methods on the module — append-only API."""
    public_names = [n for n in dir(reg_mod) if not n.startswith("_")]
    for forbidden in ("delete", "remove", "drop", "edit", "update"):
        assert forbidden not in public_names, (
            f"registry must not expose {forbidden!r}"
        )


def test_registry_entries_immutable_signature():
    """`register` only appends; there is no `update` or `replace`
    function. The registry file is rewritten in full but the
    existing entries are preserved verbatim by `register`."""
    src = Path(reg_mod.__file__).read_text(encoding="utf-8")
    assert "def update_entry" not in src
    assert "def delete_entry" not in src
    assert "def replace_entry" not in src
