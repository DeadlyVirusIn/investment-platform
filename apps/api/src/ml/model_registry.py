"""Phase 11T.1 - file-based model registry.

`models/model_registry.json` is the single source of truth for which
trained model artifacts exist locally. Append-only JSON list.
NEVER edits or deletes existing entries. NEVER touches the database.
NEVER imports broker / live / execution modules.

Frozen invariants:
  * `status` is always `"shadow_only"` in v1.
  * `registry_version` is always `"registry-v1.0.0"` in v1.
  * Existing entries are immutable (a duplicate `model_id` is rejected).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path("models/model_registry.json")
REGISTRY_VERSION = "registry-v1.0.0"
ALLOWED_STATUS: tuple[str, ...] = ("shadow_only",)
ALLOWED_MODEL_TYPES: tuple[str, ...] = ("logreg", "gbm", "rf")
ALLOWED_TASKS: tuple[str, ...] = ("classification", "regression")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ModelRegistryError(RuntimeError):
    """Base registry error."""


class DuplicateModelIdError(ModelRegistryError):
    """A model_id already exists in the registry."""


# ---------------------------------------------------------------------------
# IO helpers (pure-fn)
# ---------------------------------------------------------------------------

def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_entries(
    *,
    registry_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return all registry entries as a list of dicts. Empty list when
    the registry file does not exist."""
    p = registry_path or REGISTRY_PATH
    if not p.exists():
        return []
    raw = p.read_text(encoding="utf-8")
    if not raw.strip():
        return []
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ModelRegistryError(
            f"registry file {p} must be a JSON list (got {type(payload).__name__})"
        )
    return [dict(e) for e in payload]


def list_entries(
    *,
    registry_path: Path | None = None,
) -> list[dict[str, Any]]:
    return load_entries(registry_path=registry_path)


def show_entry(
    model_id: str,
    *,
    registry_path: Path | None = None,
) -> dict[str, Any] | None:
    for e in load_entries(registry_path=registry_path):
        if e.get("model_id") == model_id:
            return dict(e)
    return None


# ---------------------------------------------------------------------------
# Registration (write path)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegistrationRequest:
    pickle_path: Path
    report_path: Path
    notes: str | None = None


def _validate_request(req: RegistrationRequest) -> None:
    if not req.pickle_path.exists():
        raise ModelRegistryError(
            f"pickle file not found: {req.pickle_path}"
        )
    if not req.report_path.exists():
        raise ModelRegistryError(
            f"report file not found: {req.report_path}"
        )


def _read_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ModelRegistryError(
            f"report file {path} must be a JSON object"
        )
    return payload


def _read_pickle_metadata(path: Path) -> dict[str, Any]:
    """Read non-model metadata from a 11S-style pickle without
    instantiating the estimator into the trading runtime. NEVER
    invokes any prediction or training method."""
    import joblib
    obj = joblib.load(path)
    if not isinstance(obj, dict):
        raise ModelRegistryError(
            f"pickle {path} must be a dict (got {type(obj).__name__})"
        )
    out: dict[str, Any] = {}
    for k in (
        "model_type", "task", "target",
        "model_version", "label_version", "dataset_version",
        "trained_at", "trained_on", "feature_names",
        "model_params",
    ):
        if k in obj:
            out[k] = obj[k]
    return out


def build_entry(
    req: RegistrationRequest,
    *,
    registry_version: str = REGISTRY_VERSION,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Pure-fn assemble a registry entry from pickle + report. Does
    NOT mutate the registry file."""
    _validate_request(req)
    report = _read_report(req.report_path)
    meta = _read_pickle_metadata(req.pickle_path)
    artifact_checksum = _file_sha256(req.pickle_path)
    trained_on = meta.get("trained_on") or {}
    dataset_path = trained_on.get("dataset_path")
    dataset_checksum = trained_on.get("dataset_checksum_sha256")
    model_type = meta.get("model_type") or report.get("model_type")
    if model_type not in ALLOWED_MODEL_TYPES:
        raise ModelRegistryError(
            f"model_type {model_type!r} not in {ALLOWED_MODEL_TYPES}"
        )
    task = meta.get("task") or report.get("task")
    if task not in ALLOWED_TASKS:
        raise ModelRegistryError(
            f"task {task!r} not in {ALLOWED_TASKS}"
        )
    when = (now_utc or _now_utc()).isoformat()
    short_hash = artifact_checksum[:4]
    model_id = (
        f"{model_type}-{task}-"
        f"{when.replace(':', '').split('.')[0]}Z-{short_hash}"
    )
    train_range = (report.get("splits") or {}).get("train", {})
    test_range = (report.get("splits") or {}).get("test", {})
    holdout_range = (report.get("splits") or {}).get("holdout", {})
    metrics = report.get("metrics") or {}
    entry = {
        "model_id": model_id,
        "model_type": model_type,
        "task": task,
        "target": meta.get("target") or report.get("target"),
        "training_dataset_id":
            (report.get("dataset") or {}).get("id"),
        "training_dataset_path": dataset_path,
        "training_dataset_checksum_sha256": dataset_checksum,
        "label_version": meta.get("label_version"),
        "feature_schema_version": meta.get("dataset_version"),
        "train_range": train_range,
        "test_range": test_range,
        "holdout_range": holdout_range,
        "metrics": {
            "test": metrics.get("test"),
            "holdout": metrics.get("holdout"),
        },
        "artifact_path": str(req.pickle_path),
        "artifact_checksum_sha256": artifact_checksum,
        "created_at": when,
        "status": "shadow_only",
        "registry_version": registry_version,
        "notes": req.notes,
    }
    return entry


def register(
    req: RegistrationRequest,
    *,
    registry_path: Path | None = None,
    dry_run: bool = True,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Append a registration entry. Refuses duplicate model_id. When
    dry_run=True the entry is built and returned but the file is NOT
    written."""
    p = registry_path or REGISTRY_PATH
    entries = load_entries(registry_path=p)
    entry = build_entry(req, now_utc=now_utc)
    for e in entries:
        if (
            e.get("model_id") == entry["model_id"]
            or (
                e.get("artifact_path") == entry["artifact_path"]
                and e.get("artifact_checksum_sha256")
                == entry["artifact_checksum_sha256"]
            )
        ):
            raise DuplicateModelIdError(
                f"model already registered: {entry['model_id']!r} "
                f"(artifact={entry['artifact_path']!r})"
            )
    if entry["status"] not in ALLOWED_STATUS:
        raise ModelRegistryError(
            f"status must be in {ALLOWED_STATUS}; got {entry['status']!r}"
        )
    if dry_run:
        return entry
    p.parent.mkdir(parents=True, exist_ok=True)
    out = entries + [entry]
    p.write_text(
        json.dumps(out, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return entry
