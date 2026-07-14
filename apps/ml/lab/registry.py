"""RegistryClient — ORM write path for the research_run ledger.

Implements the in-process entry point of the spec's "one write module, two
entry points" contract (RESEARCH_RUN_REGISTRY_SPEC.md §4): scripts on the
dev machine write through this client; a future admin API reuses the same
validation semantics.

Invariants enforced here (the ORM/migration 109 pins the storage shape;
the CHECK-level invariants are app-enforced through this client):
  * status machine: draft → running → completed | failed | aborted;
    terminal rows are frozen (RunFrozenError on any further mutation
    except the artifact `available` flag — spec §7).
  * metrics merge is append-only while running: an existing key is never
    overwritten (MetricOverwriteError), matching the reasoning_audit
    append-only contract.
  * failed runs must carry error_summary (capped at 2000 chars).
  * config_hash = sha256(canonical JSON of parameters); data_hash =
    sha256(canonical JSON of the caller-provided input-window manifest).
  * run_uid 'rr_<yyyymmdd>_<8hex>' — short, greppable; uuid PK stays
    internal.

Transactions: methods flush, never commit — the owning session/script
decides transaction boundaries.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import uuid

from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import ResearchRun

RUN_TYPES = frozenset({
    "walk_forward", "optuna_study", "optuna_trial", "calibration",
    "backtest", "feature_study", "drift_study", "other",
})
TERMINAL_STATUSES = frozenset({"completed", "failed", "aborted"})
ERROR_SUMMARY_MAX_CHARS = 2000
ARTIFACT_KINDS = frozenset({
    "fold_results", "reliability_curve", "feature_importance",
    "study_db", "plot", "report", "other",
})


class RegistryError(RuntimeError):
    """Base error for research-run registry violations."""


class MetricOverwriteError(RegistryError):
    """A metrics merge attempted to overwrite an existing key."""


class RunFrozenError(RegistryError):
    """Mutation attempted on a terminal (frozen) run."""


class InvalidTransitionError(RegistryError):
    """Status transition outside draft → running → terminal."""


# ---------------------------------------------------------------------------
# hashing / identity helpers
# ---------------------------------------------------------------------------


def canonical_json(obj: object) -> str:
    """Key-sorted, separator-stable JSON. allow_nan=False: NaN/Inf have no
    canonical form and would silently break hash determinism."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False, default=str,
    )


def config_hash(params: dict) -> str:
    """sha256 over canonicalized parameters — key order never matters."""
    return hashlib.sha256(canonical_json(params).encode("utf-8")).hexdigest()


def data_hash(manifest: dict) -> str:
    """sha256 over the caller-provided input-window manifest (universe,
    row counts, min/max timestamps per table — spec §2), not raw data."""
    return hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()


def new_run_uid(now: dt.datetime | None = None) -> str:
    stamp = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%d")
    return f"rr_{stamp}_{uuid.uuid4().hex[:8]}"


def resolve_git_sha() -> str:
    """GIT_SHA env first (Docker images bake it — build_provenance), then
    `git rev-parse HEAD`, else 'unknown' (which promotion gates reject)."""
    sha = os.environ.get("GIT_SHA", "").strip()
    if sha:
        return sha
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001 — no git binary / not a repo
        return "unknown"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def registry_table_exists(bind) -> bool:
    """True when the research_run table exists on the given engine or
    connection — scripts use this to make --registry a graceful no-op
    against databases that never ran migration 109."""
    return sa_inspect(bind).has_table(ResearchRun.__tablename__)


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------


class RegistryClient:
    """Session-injected writer for research_run rows."""

    def __init__(self, session: Session):
        self._session = session

    # -- lifecycle ----------------------------------------------------------

    def create_run(
        self,
        *,
        run_type: str,
        name: str,
        params: dict,
        git_sha: str | None = None,
        seed: int | None = None,
        data_window: tuple[dt.date | None, dt.date | None] | None = None,
        data_manifest: dict | None = None,
        description: str | None = None,
        model_version: str | None = None,
        feature_schema_version: str | None = None,
        split_method: str | None = None,
        parent_run_id: str | None = None,
        created_by: str = "owner",
        now: dt.datetime | None = None,
    ) -> ResearchRun:
        """Register a run in status 'draft'. config_hash is derived here —
        callers supply parameters, never hashes."""
        if run_type not in RUN_TYPES:
            raise RegistryError(f"run_type {run_type!r} not in {sorted(RUN_TYPES)}")
        if not isinstance(params, dict):
            raise RegistryError("params must be a dict")
        if parent_run_id is not None and self._session.get(ResearchRun, parent_run_id) is None:
            raise RegistryError(f"parent_run_id {parent_run_id!r} does not exist")

        start, end = data_window if data_window else (None, None)
        run = ResearchRun(
            run_uid=new_run_uid(now),
            run_type=run_type,
            name=name,
            description=description,
            status="draft",
            git_sha=git_sha or resolve_git_sha(),
            model_version=model_version,
            feature_schema_version=feature_schema_version,
            data_start=start,
            data_end=end,
            data_hash=data_hash(data_manifest) if data_manifest is not None else None,
            config_hash=config_hash(params),
            random_seed=seed,
            split_method=split_method,
            parameters=params,
            metrics={},
            artifact_manifest=[],
            parent_run_id=parent_run_id,
            created_by=created_by,
        )
        self._session.add(run)
        self._session.flush()
        return run

    def get_run(self, run_uid: str) -> ResearchRun | None:
        return self._session.execute(
            select(ResearchRun).where(ResearchRun.run_uid == run_uid)
        ).scalar_one_or_none()

    def start(self, run: ResearchRun) -> ResearchRun:
        if run.status != "draft":
            raise InvalidTransitionError(
                f"{run.run_uid}: start requires status 'draft', got {run.status!r}"
            )
        run.status = "running"
        run.started_at = dt.datetime.now(dt.timezone.utc)
        self._session.flush()
        return run

    def finish(self, run: ResearchRun, metrics: dict | None = None) -> ResearchRun:
        if run.status != "running":
            raise InvalidTransitionError(
                f"{run.run_uid}: finish requires status 'running', got {run.status!r}"
            )
        if metrics:
            self.append_metrics(run, metrics)
        run.status = "completed"
        run.completed_at = dt.datetime.now(dt.timezone.utc)
        self._session.flush()
        return run

    def fail(self, run: ResearchRun, error_summary: str) -> ResearchRun:
        if run.status in TERMINAL_STATUSES:
            raise RunFrozenError(f"{run.run_uid} is terminal ({run.status})")
        if not error_summary:
            raise RegistryError("failed runs must explain themselves (error_summary)")
        run.status = "failed"
        run.error_summary = error_summary[:ERROR_SUMMARY_MAX_CHARS]
        run.completed_at = dt.datetime.now(dt.timezone.utc)
        self._session.flush()
        return run

    # -- append-only metrics / artifacts -------------------------------------

    def append_metrics(self, run: ResearchRun, metrics: dict) -> ResearchRun:
        """Merge new metric keys. Existing keys are never overwritten —
        corrections are new keys or a retry run (spec §7.3)."""
        if run.status in TERMINAL_STATUSES:
            raise RunFrozenError(
                f"{run.run_uid} is terminal ({run.status}); metrics are frozen"
            )
        existing = dict(run.metrics or {})
        clash = sorted(set(existing) & set(metrics))
        if clash:
            raise MetricOverwriteError(
                f"{run.run_uid}: metric keys already recorded: {clash}"
            )
        # JSON round-trip guard: reject NaN/Inf before they hit JSONB.
        canonical_json(metrics)
        existing.update(metrics)
        run.metrics = existing  # reassign — JSON column mutation isn't tracked
        self._session.flush()
        return run

    def add_artifact(
        self,
        run: ResearchRun,
        path: str,
        *,
        kind: str = "other",
        sha256: str | None = None,
        n_bytes: int | None = None,
    ) -> dict:
        """Append a manifest entry {path, sha256, bytes, kind, available}.
        Hash/size are computed from disk when not supplied; a missing file
        records available=False (a fact about the disk, not the run)."""
        if run.status in TERMINAL_STATUSES:
            raise RunFrozenError(
                f"{run.run_uid} is terminal ({run.status}); manifest is frozen"
            )
        if kind not in ARTIFACT_KINDS:
            raise RegistryError(f"artifact kind {kind!r} not in {sorted(ARTIFACT_KINDS)}")
        manifest = list(run.artifact_manifest or [])
        if any(e.get("path") == path for e in manifest):
            raise RegistryError(f"{run.run_uid}: artifact path already recorded: {path}")

        if sha256 is None and os.path.isfile(path):
            sha256 = sha256_file(path)
            n_bytes = os.path.getsize(path)
        entry = {
            "path": path,
            "sha256": sha256,
            "bytes": n_bytes,
            "kind": kind,
            "available": sha256 is not None,
        }
        manifest.append(entry)
        run.artifact_manifest = manifest
        self._session.flush()
        return entry

    def set_artifact_available(
        self, run: ResearchRun, path: str, available: bool,
    ) -> ResearchRun:
        """The ONLY mutation legal on a terminal run (spec §7.1):
        availability is a statement about the dev disk, not the experiment."""
        manifest = list(run.artifact_manifest or [])
        for entry in manifest:
            if entry.get("path") == path:
                entry["available"] = bool(available)
                entry["verified_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                run.artifact_manifest = manifest
                self._session.flush()
                return run
        raise RegistryError(f"{run.run_uid}: no manifest entry for {path}")
