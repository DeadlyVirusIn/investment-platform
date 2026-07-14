"""Agent Gateway B-scope — bounded offline research jobs (spec §3/§4/§7).

The contract, structurally enforced:
  * job_type is an EXACT string match against a frozen set of four offline
    handlers — no casing/Unicode normalization, no paths, no modules, no
    shell, no URLs, no SQL. Anything else is rejected before any write.
  * every job type maps to a HARDCODED read-only handler in _HANDLERS and a
    hardcoded parameter validator in _PARAM_VALIDATORS. There is no dynamic
    dispatch, no import from request data, no eval of any field.
  * handlers run on the dev/offline lane ONLY: `run_next_queued` is called
    by tests or a manual operator script — NEVER from a request handler and
    NEVER from the scheduler (no registry entry exists).
  * idempotency is atomic: INSERT .. ON CONFLICT on agent_idempotency
    (UNIQUE token_prefix+idem_key), then request_hash comparison — same
    key + same request replays the original job; same key + different
    request is a 409-shaped IdempotencyConflict. Races collapse to one row.
  * queue cap: ≤ 5 queued/running jobs per owner, counted under a pg
    advisory transaction lock so concurrent submissions cannot overshoot.
  * terminal statuses (succeeded/failed/cancelled) are immutable —
    transition attempts raise; failures store capped summaries, never raw
    stack traces or secrets.
  * every accepted job writes a research_run registry row (Sprint 5
    discipline): run_uid, config_hash, recorded seed, parameters.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import secrets
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Errors (service-level; the router maps them to HTTP)
# ---------------------------------------------------------------------------


class AgentJobError(Exception):
    """Base."""


class InvalidJob(AgentJobError):
    """Unknown type / bad params / bad seed — 422-shaped."""


class IdempotencyConflict(AgentJobError):
    """Same key, different request — 409-shaped."""


class QueueFull(AgentJobError):
    """Owner already has 5 queued/running jobs — 429-shaped."""


class JobNotFound(AgentJobError):
    """Unknown or unowned job — 404-shaped (indistinguishable)."""


class TerminalStateError(AgentJobError):
    """Terminal statuses are immutable."""


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------
MAX_QUEUED_PER_OWNER = 5
MAX_SYMBOLS = 20
MAX_WINDOW_DAYS = 3660
MAX_SEED = 2**31 - 1
_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")
_DATE_MIN = dt.date(2000, 1, 1)
_DATE_MAX = dt.date(2100, 1, 1)
_RESULT_CAP = 2000
_ERROR_CAP = 500
_EVENT_PAYLOAD_CAP = 500

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


# ---------------------------------------------------------------------------
# Parameter validation — allowlisted keys, bounded values, unknown = reject
# ---------------------------------------------------------------------------
def _parse_date(raw: object, field: str) -> dt.date:
    if not isinstance(raw, str):
        raise InvalidJob(f"{field} must be an ISO date string")
    try:
        d = dt.date.fromisoformat(raw)
    except ValueError:
        raise InvalidJob(f"{field} is not a valid ISO date")
    if not (_DATE_MIN <= d <= _DATE_MAX):
        raise InvalidJob(f"{field} out of range 2000-01-01..2100-01-01")
    return d


def _validate_window(params: dict, out: dict) -> None:
    start = _parse_date(params.get("start"), "start")
    end = _parse_date(params.get("end"), "end")
    if start >= end:
        raise InvalidJob("start must be before end")
    if (end - start).days > MAX_WINDOW_DAYS:
        raise InvalidJob(f"window exceeds {MAX_WINDOW_DAYS} days")
    out["start"], out["end"] = start.isoformat(), end.isoformat()


def _validate_symbols(params: dict, out: dict, *, required: bool) -> None:
    raw = params.get("symbols")
    if raw is None:
        if required:
            raise InvalidJob("symbols required")
        return
    if not isinstance(raw, list) or not raw:
        raise InvalidJob("symbols must be a non-empty list")
    if len(raw) > MAX_SYMBOLS:
        raise InvalidJob(f"at most {MAX_SYMBOLS} symbols")
    cleaned = []
    for s in raw:
        if not isinstance(s, str) or not _SYMBOL_RE.match(s):
            raise InvalidJob(f"invalid symbol: {s!r}")
        cleaned.append(s)
    out["symbols"] = cleaned


def _validate_int(params: dict, out: dict, key: str, lo: int, hi: int,
                  default: int | None = None) -> None:
    raw = params.get(key, default)
    if raw is None:
        raise InvalidJob(f"{key} required")
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise InvalidJob(f"{key} must be an integer")
    if not (lo <= raw <= hi):
        raise InvalidJob(f"{key} must be in [{lo},{hi}]")
    out[key] = raw


def _reject_unknown(params: dict, allowed: frozenset[str]) -> None:
    if not isinstance(params, dict):
        raise InvalidJob("params must be an object")
    unknown = set(params) - allowed
    if unknown:
        raise InvalidJob(f"unknown params: {sorted(unknown)}")


def _v_calibration_study(params: dict) -> dict:
    _reject_unknown(params, frozenset({"start", "end", "bins"}))
    out: dict = {}
    _validate_window(params, out)
    _validate_int(params, out, "bins", 2, 50, default=10)
    return out


def _v_walk_forward_baseline(params: dict) -> dict:
    _reject_unknown(params, frozenset({"start", "end", "folds", "symbols"}))
    out: dict = {}
    _validate_window(params, out)
    _validate_int(params, out, "folds", 1, 20, default=5)
    _validate_symbols(params, out, required=False)
    return out


def _v_drift_report(params: dict) -> dict:
    _reject_unknown(params, frozenset({"reference_days", "current_days"}))
    out: dict = {}
    _validate_int(params, out, "reference_days", 7, 730, default=90)
    _validate_int(params, out, "current_days", 1, 90, default=14)
    return out


def _v_attribution_fixture(params: dict) -> dict:
    _reject_unknown(params, frozenset({"symbols"}))
    out: dict = {}
    _validate_symbols(params, out, required=False)
    return out


_PARAM_VALIDATORS = {
    "calibration_study": _v_calibration_study,
    "walk_forward_baseline": _v_walk_forward_baseline,
    "drift_report": _v_drift_report,
    "attribution_fixture": _v_attribution_fixture,
}

JOB_TYPES = frozenset(_PARAM_VALIDATORS)


def validate_job(job_type: object, params: object) -> dict:
    """Exact-match dispatch. `job_type` must be the literal str — casing,
    Unicode confusables, whitespace, traversal, or non-str types all miss
    the frozenset and are rejected."""
    if not isinstance(job_type, str) or job_type not in JOB_TYPES:
        raise InvalidJob("unknown job_type")
    return _PARAM_VALIDATORS[job_type](params if isinstance(params, dict) else {})


def normalize_seed(seed: object) -> int:
    """Deterministic seed: caller-provided int in range, or
    server-generated — either way it is RECORDED on the job + registry."""
    if seed is None:
        return secrets.randbelow(MAX_SEED)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise InvalidJob("seed must be an integer")
    if not (0 <= seed <= MAX_SEED):
        raise InvalidJob(f"seed must be in [0,{MAX_SEED}]")
    return seed


def request_fingerprint(job_type: str, params: dict, seed: int | None,
                        research_task_id: str | None = None) -> str:
    """Canonical hash for idempotency conflict detection.

    Wave 2C: the task link is part of the request identity — reusing an
    idempotency key with a DIFFERENT research_task_id is a 409 conflict,
    never a silent replay or a link mutation. The key is added to the
    blob ONLY when present, so every pre-121 fingerprint (and every
    task-less submission) hashes exactly as before."""
    payload: dict = {"t": job_type, "p": params, "s": seed}
    if research_task_id is not None:
        payload["rt"] = research_task_id
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Idempotency — atomic via INSERT .. ON CONFLICT (shared with D-scope drafts)
# ---------------------------------------------------------------------------
def claim_idempotency(
    db: Session, *, token_prefix: str, idem_key: str, kind: str,
    request_hash: str, ref_id: str,
) -> tuple[bool, str]:
    """Try to claim (token_prefix, idem_key). Returns (claimed, ref_id):
    claimed=True → this request owns the key (ref_id = ours);
    claimed=False → key exists: same request_hash → (False, original ref)
    for replay; different hash → IdempotencyConflict. Race-safe: the unique
    index collapses concurrent inserts to exactly one winner."""
    row = db.execute(
        text(
            """
            INSERT INTO agent_idempotency
              (id, token_prefix, idem_key, kind, request_hash, ref_id)
            VALUES (:id, :tp, :k, :kind, :rh, :ref)
            ON CONFLICT (token_prefix, idem_key) DO NOTHING
            RETURNING id
            """
        ),
        {"id": str(uuid.uuid4()), "tp": token_prefix, "k": idem_key[:64],
         "kind": kind, "rh": request_hash, "ref": ref_id},
    ).first()
    if row is not None:
        return True, ref_id
    existing = db.execute(
        text(
            "SELECT request_hash, ref_id, kind FROM agent_idempotency "
            "WHERE token_prefix = :tp AND idem_key = :k"
        ),
        {"tp": token_prefix, "k": idem_key[:64]},
    ).mappings().first()
    if existing is None:  # pragma: no cover — conflict row vanished
        raise IdempotencyConflict("idempotency state unavailable")
    if existing["request_hash"] != request_hash or existing["kind"] != kind:
        raise IdempotencyConflict(
            "idempotency key already used for a different request"
        )
    return False, existing["ref_id"]


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------
def _validate_research_task(db: Session, research_task_id: object) -> str | None:
    """Wave 2C task↔job provenance: validate the OPTIONAL task link at
    submit time. The task must exist and be executable (open|paused —
    paused pauses scheduling INTENT, manual/agent execution stays
    meaningful; closed tasks are retired and refuse new work). Bounded
    422-shaped errors; single-tenant deployment so task-id probing by
    owner-created tokens is owner-probing-owner (documented residual).
    The link is immutable after insert (DB trigger + no update path)."""
    if research_task_id is None:
        return None
    if not isinstance(research_task_id, str) or not research_task_id.strip():
        raise InvalidJob("research_task_id must be a non-empty string")
    tid = research_task_id.strip()[:36]
    row = db.execute(
        text("SELECT status FROM research_task WHERE id = :t"), {"t": tid}
    ).mappings().first()
    if row is None:
        raise InvalidJob("unknown research_task_id")
    if row["status"] not in ("open", "paused"):
        raise InvalidJob("research task is closed")
    return tid


def submit_job(
    db: Session, *, ident: dict, job_type: str, params: object,
    idempotency_key: str, seed: object = None, git_sha: str = "dev",
    research_task_id: object = None,
) -> tuple[dict, bool]:
    """Validate → idempotency claim → queue-cap check under advisory lock →
    insert agent_job + research_run registry row. Returns (job_dict,
    replayed). All side effects in the caller's transaction; caller commits.
    """
    key = (idempotency_key or "").strip()
    if not key or len(key) > 64:
        raise InvalidJob("idempotency_key required (1-64 chars)")
    clean = validate_job(job_type, params)
    seed_val = normalize_seed(seed)
    task_id = _validate_research_task(db, research_task_id)
    rhash = request_fingerprint(job_type, clean, seed_val
                                if seed is not None else None,
                                research_task_id=task_id)

    job_id = str(uuid.uuid4())
    claimed, ref = claim_idempotency(
        db, token_prefix=ident["token_prefix"], idem_key=key, kind="job",
        request_hash=rhash, ref_id=job_id,
    )
    if not claimed:
        job = get_job(db, ident, job_id_or_uid=ref, by_id=True)
        return job, True

    # queue cap — advisory xact lock serializes concurrent submitters for
    # the same owner, so count+insert is atomic (lock released on commit)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
               {"k": f"agent_jobs:{ident['created_by']}"})
    n = db.execute(
        text("SELECT count(*) FROM agent_job WHERE created_by = :o "
             "AND status IN ('queued','running')"),
        {"o": ident["created_by"]},
    ).scalar() or 0
    if n >= MAX_QUEUED_PER_OWNER:
        raise QueueFull(f"queue full ({n}/{MAX_QUEUED_PER_OWNER})")

    job_uid = "agj_" + secrets.token_hex(8)
    run_id = str(uuid.uuid4())
    # research_run registry row (Sprint 5 discipline) — parameters recorded,
    # seed recorded, config_hash = request fingerprint
    db.execute(
        text(
            """
            INSERT INTO research_run
              (id, run_uid, run_type, name, description, status, git_sha,
               config_hash, random_seed, parameters, metrics,
               artifact_manifest, promotion_status, created_by, created_at)
            VALUES
              (:id, :uid, 'agent_job', :name, :descr, 'draft', :sha,
               :ch, :seed, CAST(:params AS jsonb), CAST('{}' AS jsonb),
               CAST('[]' AS jsonb), 'none', :cb, now())
            """
        ),
        {"id": run_id, "uid": ("agr" + secrets.token_hex(8))[:32],
         "name": f"agent job {job_type}"[:256],
         "descr": f"Agent Gateway B-scope job {job_uid}",
         "sha": git_sha[:64], "ch": rhash, "seed": seed_val,
         "params": json.dumps(clean), "cb": ident["created_by"][:64]},
    )
    db.execute(
        text(
            """
            INSERT INTO agent_job
              (id, job_uid, job_type, params, seed, status, token_prefix,
               created_by, request_hash, research_run_id, research_task_id)
            VALUES
              (:id, :uid, :jt, CAST(:params AS jsonb), :seed, 'queued', :tp,
               :cb, :rh, :rr, :rt)
            """
        ),
        {"id": job_id, "uid": job_uid, "jt": job_type,
         "params": json.dumps(clean), "seed": seed_val,
         "tp": ident["token_prefix"], "cb": ident["created_by"][:64],
         "rh": rhash, "rr": run_id, "rt": task_id},
    )
    # Bounded provenance identity in the event stream — never task body/scope.
    _append_event(db, job_id, "queued",
                  f"job {job_type} accepted"
                  + (f" (task {task_id[:8]}…)" if task_id else ""))
    return get_job(db, ident, job_id_or_uid=job_id, by_id=True), False


def get_job(db: Session, ident: dict, *, job_id_or_uid: str,
            by_id: bool = False) -> dict:
    """Owner-scoped fetch. Unknown and unowned are indistinguishable (404
    posture — spec §7.4)."""
    col = "id" if by_id else "job_uid"
    row = db.execute(
        text(
            f"SELECT id, job_uid, job_type, params, seed, status, "
            f"result_summary, error_summary, created_at, started_at, "
            f"finished_at, created_by, research_task_id "
            f"FROM agent_job WHERE {col} = :v"
        ),
        {"v": job_id_or_uid[:36]},
    ).mappings().first()
    if row is None or row["created_by"] != ident["created_by"]:
        raise JobNotFound("no such job")
    return {
        "job_uid": row["job_uid"],
        "job_type": row["job_type"],
        "params": row["params"],
        "seed": row["seed"],
        "status": row["status"],
        "result_summary": row["result_summary"],
        "error_summary": row["error_summary"],
        "created_at": row["created_at"].isoformat(),
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        # the caller's own claim, echoed back (immutable after insert)
        "research_task_id": row["research_task_id"],
        "_id": row["id"],  # internal — routers must strip before serializing
    }


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
def _append_event(db: Session, job_id: str, event_type: str,
                  payload: str) -> None:
    db.execute(
        text(
            """
            INSERT INTO agent_job_event (id, job_id, seq, event_type, payload)
            VALUES (:id, CAST(:j AS varchar),
                    COALESCE((SELECT max(seq) FROM agent_job_event
                              WHERE job_id = CAST(:j2 AS varchar)), 0) + 1,
                    :et, :pl)
            """
        ),
        {"id": str(uuid.uuid4()), "j": job_id, "j2": job_id,
         "et": event_type[:24], "pl": (payload or "")[:_EVENT_PAYLOAD_CAP]},
    )


def fetch_events(db: Session, job_id: str, *, after_seq: int = 0,
                 limit: int = 100) -> list[dict]:
    """Bounded, indexed page ((job_id, seq) index; never a full scan)."""
    rows = db.execute(
        text(
            "SELECT seq, event_type, payload, created_at FROM agent_job_event "
            "WHERE job_id = :j AND seq > :a ORDER BY seq ASC LIMIT :l"
        ),
        {"j": job_id, "a": max(0, int(after_seq)), "l": min(500, max(1, int(limit)))},
    ).mappings().all()
    return [{"seq": r["seq"], "event": r["event_type"],
             "payload": r["payload"], "at": r["created_at"].isoformat()}
            for r in rows]


# ---------------------------------------------------------------------------
# Status transitions — terminal is immutable
# ---------------------------------------------------------------------------
def _transition(db: Session, job_id: str, new_status: str, *,
                result_summary: str | None = None,
                error_summary: str | None = None) -> None:
    row = db.execute(
        text("SELECT status FROM agent_job WHERE id = :i FOR UPDATE"),
        {"i": job_id},
    ).mappings().first()
    if row is None:
        raise JobNotFound("no such job")
    if row["status"] in TERMINAL_STATUSES:
        raise TerminalStateError(
            f"job already terminal ({row['status']}); statuses are immutable"
        )
    stamps = {
        "running": "started_at = now()",
        "succeeded": "finished_at = now()",
        "failed": "finished_at = now()",
        "cancelled": "finished_at = now()",
    }
    db.execute(
        text(
            f"UPDATE agent_job SET status = :s, {stamps[new_status]}, "
            f"result_summary = COALESCE(:rs, result_summary), "
            f"error_summary = COALESCE(:es, error_summary) WHERE id = :i"
        ),
        {"s": new_status, "i": job_id,
         "rs": (result_summary or None) and result_summary[:_RESULT_CAP],
         "es": (error_summary or None) and error_summary[:_ERROR_CAP]},
    )


def cancel_job(db: Session, ident: dict, job_uid: str) -> dict:
    """Cancellation is safe ONLY for queued jobs (nothing has run). A
    running/terminal job cannot be cancelled — no kill path exists."""
    job = get_job(db, ident, job_id_or_uid=job_uid)
    if job["status"] != "queued":
        raise TerminalStateError("only queued jobs can be cancelled")
    _transition(db, job["_id"], "cancelled", result_summary="cancelled by owner")
    _append_event(db, job["_id"], "cancelled", "cancelled before start")
    return get_job(db, ident, job_id_or_uid=job_uid)


# ---------------------------------------------------------------------------
# Offline dev-lane runner — NEVER called from a request handler and NEVER
# registered with the scheduler. Tests and a manual operator invocation are
# the only callers. Handlers are read-only over dev data and bounded.
# ---------------------------------------------------------------------------
def _h_calibration_study(db: Session, params: dict, seed: int) -> str:
    row = db.execute(
        text(
            "SELECT count(*) AS n, count(DISTINCT action) AS actions "
            "FROM recommendation WHERE generated_at >= :s AND generated_at < :e"
        ),
        {"s": params["start"], "e": params["end"]},
    ).mappings().one()
    return (f"calibration_study seed={seed} bins={params['bins']} "
            f"recommendations={row['n']} actions={row['actions']}")


def _h_walk_forward_baseline(db: Session, params: dict, seed: int) -> str:
    n = db.execute(
        text("SELECT count(*) FROM historical_label "
             "WHERE as_of_date >= :s AND as_of_date < :e"),
        {"s": params["start"], "e": params["end"]},
    ).scalar() or 0
    return (f"walk_forward_baseline seed={seed} folds={params['folds']} "
            f"labels={n} symbols={len(params.get('symbols', []) or [])}")


def _h_drift_report(db: Session, params: dict, seed: int) -> str:
    from apps.api.src.domain.monitoring.drift import run_drift_report

    report = run_drift_report(
        db, now=dt.datetime.now(dt.timezone.utc),
        reference_days=params["reference_days"],
        current_days=params["current_days"],
    )
    d = report.to_dict()
    return (f"drift_report seed={seed} overall={d['overall']} "
            f"checks={len(d['checks'])} truncated={d['checks_truncated']}")


def _h_attribution_fixture(db: Session, params: dict, seed: int) -> str:
    syms = params.get("symbols") or []
    return f"attribution_fixture seed={seed} symbols={','.join(syms) or 'none'}"


_HANDLERS = {
    "calibration_study": _h_calibration_study,
    "walk_forward_baseline": _h_walk_forward_baseline,
    "drift_report": _h_drift_report,
    "attribution_fixture": _h_attribution_fixture,
}
assert set(_HANDLERS) == JOB_TYPES  # dispatch table stays in lockstep


def run_next_queued(db: Session) -> str | None:
    """Run the oldest queued job to completion. Returns its job_uid, or
    None when the queue is empty. Dev/offline lane only."""
    row = db.execute(
        text("SELECT id, job_uid, job_type, params, seed FROM agent_job "
             "WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1 "
             "FOR UPDATE SKIP LOCKED"),
    ).mappings().first()
    if row is None:
        return None
    _transition(db, row["id"], "running")
    _append_event(db, row["id"], "started", f"running {row['job_type']}")
    try:
        summary = _HANDLERS[row["job_type"]](db, row["params"], row["seed"])
        _transition(db, row["id"], "succeeded", result_summary=summary)
        _append_event(db, row["id"], "completed", summary)
        db.execute(
            text("UPDATE research_run SET status='completed', "
                 "completed_at=now(), metrics = CAST(:m AS jsonb) "
                 "WHERE id = (SELECT research_run_id FROM agent_job "
                 "WHERE id = :i)"),
            {"i": row["id"], "m": json.dumps({"summary": summary[:500]})},
        )
    except Exception as exc:  # noqa: BLE001 — capped summary, never a stack
        msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        _transition(db, row["id"], "failed", error_summary=msg)
        _append_event(db, row["id"], "failed", msg)
        db.execute(
            text("UPDATE research_run SET status='failed', "
                 "completed_at=now(), error_summary=:e "
                 "WHERE id = (SELECT research_run_id FROM agent_job "
                 "WHERE id = :i)"),
            {"i": row["id"], "e": msg},
        )
    return row["job_uid"]
