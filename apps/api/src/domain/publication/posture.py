"""Research Safe Mode — signal-derived system posture (Wave 1B).

Implements the frozen interface Wave 1A already consumes:

    current_posture(db)        -> "NORMAL" | "RESTRICTED" | "SAFE"
    current_posture_event(db)  -> (posture, posture_event_id | None)

Semantics (unchanged from the Wave-1A contract):
* NORMAL     — publication unrestricted (per-idea preflight still applies).
* RESTRICTED — publish only as READY_WITH_LIMITATIONS.
* SAFE       — no NEW ideas publish (preflight verdict: HOLD). Existing
  recommendations, portfolios, paper exits, outcome processing, account
  access, and history remain fully readable — posture gates PUBLICATION
  only, nothing else.

Flag: ``SYSTEM_POSTURE_ENABLED`` (default False).
* OFF → exact Wave-1A behavior: ``SYSTEM_POSTURE_OVERRIDE`` (dev/test
  lever) else NORMAL; no signals read, no events written, no routes, no
  banner.
* ON  → posture derives from the deterministic signal registry below; the
  env override is IGNORED (no lever may manufacture a posture the signals
  don't support).

Design rules:
* Signals are pure reads of stored facts; classification (ok | warning |
  critical) is explicit per signal and documented.
* Posture proposal: any critical → SAFE · any warning → RESTRICTED ·
  else clean.
* Hysteresis (deterministic, no timers): a clean proposal recovers one
  step per evaluation cycle, and SAFE additionally requires owner
  acknowledgment first — SAFE →(clean+ack)→ RESTRICTED(recovering)
  →(clean)→ NORMAL. RESTRICTED caused by warnings recovers through the
  same one-clean-cycle cooldown. Downgrades are always immediate.
* Events are append-only. Acknowledgment and incidents are their own
  events; nothing updates a prior row's posture/reasons (the two
  acknowledged_* columns exist for future annotation and are written only
  at insert time by the ack event itself).
* Fail closed: evaluator/db failure yields RESTRICTED (never NORMAL);
  ``_FAILURE_SAFE_THRESHOLD`` consecutive failures escalate to SAFE.
* No LLM anywhere; owner routes run the SAME evaluator and cannot
  override its result.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.build_provenance import get_build_provenance
from apps.api.src.config import settings

Posture = Literal["NORMAL", "RESTRICTED", "SAFE"]
Level = Literal["ok", "warning", "critical"]

_VALID: tuple[Posture, ...] = ("NORMAL", "RESTRICTED", "SAFE")

EVALUATOR_VERSION = "posture-1"

# ---- policy constants (documented in RESEARCH_SAFE_MODE.md) ---------------
INGEST_WARN_HOURS = 30          # matches preflight provider policy
INGEST_CRITICAL_HOURS = 72
PRICE_WARN_DAYS = 5             # matches preflight bar policy
PRICE_CRITICAL_DAYS = 10
OUTCOME_GRACE_DAYS = 4          # weekend + holiday tolerant
SCHEDULER_CRITICAL_JOBS = {     # jobs whose failure starves publication inputs
    "ingest_prices_daily", "run_daily_pipeline", "generate_stock_candidates",
}
#: consecutive evaluator failures before fail-closed escalates
#: RESTRICTED → SAFE (bounded rule; resets on any success).
_FAILURE_SAFE_THRESHOLD = 3
#: lazy-read cache TTL — bounded safety fallback, not the primary path.
_CACHE_TTL_SECONDS = 60

_REASON_LIMIT = 4000
_SNAPSHOT_LIMIT = 16000


# ---------------------------------------------------------------------------
# Signals — deterministic registry (pure reads, explicit classification)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Signal:
    signal_id: str
    level: Level
    detail: str
    snapshot: dict[str, Any]


def _sig(sid: str, level: Level, detail: str, **snap: Any) -> Signal:
    return Signal(sid, level, detail, dict(snap))


def _hours_since(db: Session, sql: str, params: dict[str, Any] | None = None):
    row = db.execute(text(sql), params or {}).first()
    return row


def _s_ingest_health(db: Session) -> Signal:
    row = db.execute(text(
        "SELECT jr.id, jr.status, jr.finished_at, "
        "EXTRACT(EPOCH FROM (now() - jr.finished_at))/3600.0 AS age_h "
        "FROM job_run jr JOIN job_schedule js ON js.id = jr.job_schedule_id "
        "WHERE js.name = 'ingest_prices_daily' "
        "ORDER BY jr.started_at DESC LIMIT 1"
    )).first()
    if row is None:
        return _sig("ingest_health", "critical",
                    "no ingest run history", run_id=None)
    run_id, status, _fin, age_h = row[0], row[1], row[2], row[3]
    age_h = float(age_h) if age_h is not None else None
    if status != "success":
        return _sig("ingest_health", "critical",
                    f"last ingest run status={status}",
                    run_id=run_id, status=status)
    if age_h is None or age_h > INGEST_CRITICAL_HOURS:
        return _sig("ingest_health", "critical",
                    f"last successful ingest beyond critical window "
                    f"({INGEST_CRITICAL_HOURS}h)", run_id=run_id, age_h=age_h)
    if age_h > INGEST_WARN_HOURS:
        return _sig("ingest_health", "warning",
                    f"last successful ingest beyond warning window "
                    f"({INGEST_WARN_HOURS}h)", run_id=run_id, age_h=age_h)
    return _sig("ingest_health", "ok", "ingest healthy",
                run_id=run_id, age_h=age_h)


def _s_price_data(db: Session) -> Signal:
    row = db.execute(text(
        "SELECT max(ts) AS newest, "
        "EXTRACT(EPOCH FROM (now() - max(ts)))/86400.0 AS age_d "
        "FROM price_bar WHERE timeframe = '1d'"
    )).first()
    newest = row[0].isoformat() if row and row[0] else None
    age_d = float(row[1]) if row and row[1] is not None else None
    if newest is None:
        return _sig("price_data", "critical", "no daily price bars exist",
                    newest=None)
    if age_d is None or age_d > PRICE_CRITICAL_DAYS:
        return _sig("price_data", "critical",
                    f"newest bar beyond critical window ({PRICE_CRITICAL_DAYS}d)",
                    newest=newest, age_d=age_d)
    if age_d > PRICE_WARN_DAYS:
        return _sig("price_data", "warning",
                    f"newest bar beyond warning window ({PRICE_WARN_DAYS}d)",
                    newest=newest, age_d=age_d)
    return _sig("price_data", "ok", "price data fresh",
                newest=newest, age_d=age_d)


def _s_ingest_contracts(db: Session) -> Signal:  # noqa: ARG001
    # Contract reports are not persisted yet; ABORT-level detection wires in
    # when they are. Until then: flag off = warning (validation unenforced —
    # a RESTRICTED trigger per policy); flag on = ok (aborts stop rows
    # upstream and surface via ingest_health/price_data).
    if not settings.INGEST_CONTRACTS_ENABLED:
        return _sig("ingest_contracts", "warning",
                    "ingest contracts disabled — dataset validation "
                    "unenforced", enabled=False)
    return _sig("ingest_contracts", "ok", "ingest contracts enforced",
                enabled=True)


def _s_scheduler(db: Session) -> Signal:
    from apps.api.src.domain.ops.scheduling_health import overdue_jobs
    rows = overdue_jobs(db)
    if not rows:
        return _sig("scheduler", "ok", "no overdue/stuck schedules", count=0)
    crit = [r["name"] for r in rows
            if r.get("status") == "alert" and r["name"] in SCHEDULER_CRITICAL_JOBS]
    names = [r["name"] for r in rows]
    if crit:
        return _sig("scheduler", "critical",
                    f"publication-input schedules stuck/overdue: "
                    f"{', '.join(sorted(crit))}", jobs=names)
    return _sig("scheduler", "warning",
                f"{len(rows)} schedule(s) overdue/stuck (non-critical set)",
                jobs=names)


def _s_drift(db: Session) -> Signal:
    # Policy decision (documented): statistical drift alone NEVER reaches
    # SAFE — worst case is RESTRICTED. Insufficient data is honestly ok.
    from apps.api.src.domain.monitoring.drift import run_drift_report
    report = run_drift_report(
        db, now=dt.datetime.now(dt.timezone.utc)).to_dict()
    worst = report.get("overall", "ok")
    if worst in ("warn", "alert"):
        return _sig("drift", "warning",
                    f"drift status={worst} (never escalates past RESTRICTED "
                    "by policy)", overall=worst)
    return _sig("drift", "ok", f"drift status={worst}", overall=worst)


def _s_provenance(db: Session) -> Signal:  # noqa: ARG001
    sha = str(get_build_provenance().get("git_sha", "unknown"))
    if sha in ("", "unknown"):
        return _sig("provenance", "warning",
                    "runtime git sha unknown (systemic provenance "
                    "limitation)", git_sha=None)
    return _sig("provenance", "ok", "runtime provenance known",
                git_sha=sha[:12])


def _s_outcome_pipeline(db: Session) -> Signal:
    row = db.execute(text(
        "SELECT EXTRACT(EPOCH FROM (now() - max(jr.finished_at)))/86400.0 "
        "FROM job_run jr JOIN job_schedule js ON js.id = jr.job_schedule_id "
        "WHERE js.name LIKE '%outcome%' AND jr.status = 'success'"
    )).first()
    age_d = float(row[0]) if row and row[0] is not None else None
    if age_d is None:
        return _sig("outcome_pipeline", "warning",
                    "no successful outcome-labeling run recorded", age_d=None)
    if age_d > OUTCOME_GRACE_DAYS:
        return _sig("outcome_pipeline", "warning",
                    f"outcome labeling beyond grace window "
                    f"({OUTCOME_GRACE_DAYS}d — weekend/holiday tolerant)",
                    age_d=age_d)
    return _sig("outcome_pipeline", "ok", "outcome labeling active",
                age_d=age_d)


def _s_owner_incident(db: Session) -> Signal:
    row = db.execute(text(
        "SELECT id, reasons_json, created_at FROM system_posture_event "
        "WHERE reasons_json::text LIKE '%\"kind\": \"incident_open\"%' "
        "   OR reasons_json::text LIKE '%\"kind\":\"incident_open\"%' "
        "ORDER BY created_at DESC LIMIT 1"
    )).first()
    if row is None:
        return _sig("owner_incident", "ok", "no owner incident", open=False)
    closed = db.execute(text(
        "SELECT 1 FROM system_posture_event "
        "WHERE (reasons_json::text LIKE '%incident_close%') "
        "AND created_at > :t LIMIT 1"
    ), {"t": row[2]}).first()
    if closed:
        return _sig("owner_incident", "ok", "last incident closed", open=False)
    try:
        reasons = json.loads(row[1] or "[]")
        sev = next((r.get("severity") for r in reasons
                    if isinstance(r, dict) and r.get("kind") == "incident_open"),
                   "restricted")
    except (ValueError, TypeError):
        sev = "safe"  # malformed incident payload fails closed
    level: Level = "critical" if sev == "safe" else "warning"
    return _sig("owner_incident", level,
                f"owner-declared incident open (severity={sev})",
                open=True, severity=sev, event_id=row[0])


#: Ordered signal registry — order is part of the evaluator version.
SIGNALS = (
    _s_ingest_health,
    _s_price_data,
    _s_ingest_contracts,
    _s_scheduler,
    _s_drift,
    _s_provenance,
    _s_outcome_pipeline,
    _s_owner_incident,
)


def evaluate_signals(db: Session) -> list[Signal]:
    """Run every signal; an individual signal exception fails closed as a
    warning-level signal (never silently ok, never a whole-evaluator crash)."""
    out: list[Signal] = []
    for fn in SIGNALS:
        try:
            out.append(fn(db))
        except Exception as exc:  # noqa: BLE001 — per-signal fail-closed
            db.rollback()
            out.append(_sig(fn.__name__.lstrip("_s_"), "warning",
                            f"signal evaluation failed: "
                            f"{type(exc).__name__} (fail closed)"))
    return out


# ---------------------------------------------------------------------------
# Posture derivation + hysteresis
# ---------------------------------------------------------------------------

def propose(signals: list[Signal]) -> tuple[Posture, bool]:
    """(proposed posture, clean) from signal levels alone."""
    if any(s.level == "critical" for s in signals):
        return "SAFE", False
    if any(s.level == "warning" for s in signals):
        return "RESTRICTED", False
    return "NORMAL", True


def transition(
    prev: dict[str, Any] | None, proposed: Posture, clean: bool,
) -> tuple[Posture, list[dict[str, Any]]]:
    """Deterministic hysteresis. Downgrades are always immediate; ANY
    improvement out of SAFE is gated on owner acknowledgment; recovery moves
    one step per evaluation cycle (SAFE → RESTRICTED → NORMAL)."""
    extra: list[dict[str, Any]] = []
    order = {"NORMAL": 0, "RESTRICTED": 1, "SAFE": 2}

    # SAFE recovery gate — applies to ANY proposal better than SAFE
    # (RESTRICTED-after-partial-heal included), not only a clean NORMAL.
    if prev is not None and prev["posture"] == "SAFE" \
            and order[proposed] < order["SAFE"]:
        prev_acked = bool(prev.get("acknowledged_at")) or _reasons_have(
            prev, "acknowledged")
        if not prev_acked:
            extra.append({"kind": "awaiting_acknowledgment",
                          "text": "signals improved but SAFE requires owner "
                                  "acknowledgment before recovery"})
            return "SAFE", extra
        extra.append({"kind": "recovering",
                      "text": "owner acknowledged — recovering via "
                              "RESTRICTED before NORMAL"})
        return "RESTRICTED", extra

    if not clean:
        return proposed, extra           # downgrades + steady dirty states

    if prev is None or prev["posture"] == "NORMAL":
        return "NORMAL", extra

    # prev RESTRICTED, clean proposal: one full clean cycle before NORMAL.
    if bool(prev.get("signals_clean")):
        return "NORMAL", extra
    extra.append({"kind": "recovery_cooldown",
                  "text": "signals clean — one full clean cycle required "
                          "before NORMAL"})
    return "RESTRICTED", extra


def _reasons_have(event: dict[str, Any], kind: str) -> bool:
    try:
        reasons = json.loads(event.get("reasons_json") or "[]")
    except (ValueError, TypeError):
        return False
    return any(isinstance(r, dict) and r.get("kind") == kind for r in reasons)


# ---------------------------------------------------------------------------
# Persistence (append-only, idempotent, race-safe)
# ---------------------------------------------------------------------------

_EVENT_COLS = (
    "id, posture, reasons_json, signal_snapshot_json, triggered_by, "
    "previous_event_id, evaluator_version, evaluator_git_sha, input_hash, "
    "acknowledged_at, acknowledged_by, created_at"
)


def latest_event(db: Session) -> dict[str, Any] | None:
    row = db.execute(text(
        f"SELECT {_EVENT_COLS} FROM system_posture_event "
        "ORDER BY created_at DESC, id DESC LIMIT 1"
    )).mappings().first()
    if row is None:
        return None
    d = dict(row)
    try:
        snap = json.loads(d.get("signal_snapshot_json") or "{}")
        d["signals_clean"] = bool(snap.get("clean"))
    except (ValueError, TypeError):
        d["signals_clean"] = False
    return d


#: Continuous measurements that legitimately drift between evaluations
#: without any policy state change. They are STORED in the snapshot for
#: humans but excluded from the idempotency hash — same fix class as the
#: pf-2 preflight hash: identity = fact ids + levels, never raw ages.
_VOLATILE_FACT_KEYS = frozenset({"age_h", "age_d"})


def _hash_basis(signals: list[Signal], clean: bool) -> str:
    payload = {
        "clean": clean,
        "signals": [
            {"id": s.signal_id, "level": s.level,
             "facts": {k: v for k, v in sorted(s.snapshot.items())
                       if k not in _VOLATILE_FACT_KEYS}}
            for s in signals
        ],
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _snapshot_json(signals: list[Signal], clean: bool) -> str:
    payload = {
        "clean": clean,
        "signals": [
            {"id": s.signal_id, "level": s.level, "detail": s.detail,
             "facts": s.snapshot}
            for s in signals
        ],
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    if len(raw) > _SNAPSHOT_LIMIT:
        payload["signals"] = [
            {"id": s.signal_id, "level": s.level, "detail": s.detail[:200]}
            for s in signals
        ]
        payload["truncated"] = True
        raw = json.dumps(payload, sort_keys=True, default=str)
    return raw[:_SNAPSHOT_LIMIT]


def _input_hash(posture: Posture, hash_basis: str) -> str:
    return hashlib.sha256(
        f"{EVALUATOR_VERSION}|{posture}|{hash_basis}".encode()
    ).hexdigest()


def _insert_event(
    db: Session, *, posture: Posture, reasons: list[dict[str, Any]],
    snapshot_json: str, hash_basis: str, triggered_by: str,
    previous_event_id: str | None,
    acknowledged_by: str | None = None,
) -> dict[str, Any]:
    reasons_json = json.dumps(reasons, sort_keys=True, default=str)[:_REASON_LIMIT]
    ih = _input_hash(posture, hash_basis)
    sha = str(get_build_provenance().get("git_sha", "unknown"))
    db.execute(text(
        "INSERT INTO system_posture_event "
        "(id, posture, reasons_json, signal_snapshot_json, triggered_by, "
        " previous_event_id, evaluator_version, evaluator_git_sha, "
        " input_hash, acknowledged_at, acknowledged_by, created_at) "
        "VALUES (:id, :p, :r, :s, :t, :prev, :ev, :sha, :ih, "
        "        CASE WHEN CAST(:ackby AS text) IS NULL THEN NULL "
        "             ELSE now() END, "
        "        CAST(:ackby AS text), now()) "
        "ON CONFLICT (previous_event_id, input_hash, posture, triggered_by) "
        "DO NOTHING"
    ), {"id": str(uuid.uuid4()), "p": posture, "r": reasons_json,
        "s": snapshot_json, "t": triggered_by[:120], "prev": previous_event_id,
        "ev": EVALUATOR_VERSION, "sha": sha[:64], "ih": ih,
        "ackby": acknowledged_by})
    db.commit()
    row = db.execute(text(
        f"SELECT {_EVENT_COLS} FROM system_posture_event "
        "WHERE input_hash = :ih AND posture = :p AND triggered_by = :t "
        "AND previous_event_id IS NOT DISTINCT FROM :prev "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"ih": ih, "p": posture, "t": triggered_by[:120],
        "prev": previous_event_id}).mappings().first()
    return dict(row) if row else {}


def evaluate_and_record(
    db: Session, triggered_by: str = "auto",
) -> dict[str, Any]:
    """The single evaluation path (scheduled, lazy, and owner-manual all call
    this). Idempotent: identical posture + signal snapshot with the same
    predecessor collapses to one row; concurrent evaluators race safely on
    the unique key. Returns the current authoritative event row."""
    prev = latest_event(db)
    signals = evaluate_signals(db)
    proposed, clean = propose(signals)
    posture, extra = transition(prev, proposed, clean)

    reasons: list[dict[str, Any]] = [
        {"kind": "signal", "id": s.signal_id, "level": s.level,
         "text": s.detail}
        for s in signals if s.level != "ok"
    ] + extra
    if not reasons:
        reasons = [{"kind": "clean", "text": "all signals healthy"}]

    snapshot_json = _snapshot_json(signals, clean)
    hash_basis = _hash_basis(signals, clean)

    # Idempotency vs the latest event: same posture + same STABLE signal
    # state (volatile ages excluded) → return it instead of appending noise.
    if prev is not None and prev["posture"] == posture and \
            prev["input_hash"] == _input_hash(posture, hash_basis):
        return prev

    row = _insert_event(
        db, posture=posture, reasons=reasons, snapshot_json=snapshot_json,
        hash_basis=hash_basis, triggered_by=triggered_by,
        previous_event_id=prev["id"] if prev else None,
    )
    return row or (prev or {})


# ---------------------------------------------------------------------------
# Owner actions — same evaluator, no override of derived results
# ---------------------------------------------------------------------------

class PostureActionError(RuntimeError):
    pass


def acknowledge_recovery(db: Session, owner_email: str) -> dict[str, Any]:
    """Owner acknowledges a SAFE state so recovery may proceed. Refused while
    any critical signal is still active — acknowledgment cannot manufacture
    recovery, it only unlocks the hysteresis path once signals are clean."""
    prev = latest_event(db)
    if prev is None or prev["posture"] != "SAFE":
        raise PostureActionError("nothing to acknowledge — posture is not SAFE")
    signals = evaluate_signals(db)
    if any(s.level == "critical" for s in signals):
        raise PostureActionError(
            "cannot acknowledge while critical signals remain active")
    proposed, clean = propose(signals)
    reasons = [{"kind": "acknowledged",
                "text": "owner acknowledged SAFE state; recovery unlocked"}]
    return _insert_event(
        db, posture="SAFE", reasons=reasons,
        snapshot_json=_snapshot_json(signals, clean),
        hash_basis=_hash_basis(signals, clean) + "|ack",
        triggered_by=f"owner:{owner_email}"[:120],
        previous_event_id=prev["id"], acknowledged_by=owner_email[:120],
    )


def declare_incident(
    db: Session, owner_email: str, severity: str, reason: str,
) -> dict[str, Any]:
    if severity not in ("restricted", "safe"):
        raise PostureActionError("severity must be 'restricted' or 'safe'")
    prev = latest_event(db)
    posture: Posture = "SAFE" if severity == "safe" else "RESTRICTED"
    # Downgrade-only: an incident can never RAISE the posture.
    if prev is not None:
        order = {"NORMAL": 0, "RESTRICTED": 1, "SAFE": 2}
        if order[posture] < order[prev["posture"]]:
            posture = prev["posture"]
    signals = evaluate_signals(db)
    _, clean = propose(signals)
    reasons = [{"kind": "incident_open", "severity": severity,
                "text": (reason or "")[:500]}]
    return _insert_event(
        db, posture=posture, reasons=reasons,
        snapshot_json=_snapshot_json(signals, clean),
        hash_basis=_hash_basis(signals, clean) + f"|incident:{severity}",
        triggered_by=f"owner:{owner_email}"[:120],
        previous_event_id=prev["id"] if prev else None,
    )


def close_incident(db: Session, owner_email: str) -> dict[str, Any]:
    """Close the open owner incident, then RE-EVALUATE: closing an incident
    never manufactures NORMAL — the evaluator decides from live signals."""
    open_sig = _s_owner_incident(db)
    if not open_sig.snapshot.get("open"):
        raise PostureActionError("no open incident to close")
    prev = latest_event(db)
    signals = evaluate_signals(db)
    _, clean = propose(signals)
    _insert_event(
        db, posture=prev["posture"] if prev else "RESTRICTED",
        reasons=[{"kind": "incident_close",
                  "text": "owner closed the incident"}],
        snapshot_json=_snapshot_json(signals, clean),
        hash_basis=_hash_basis(signals, clean) + "|incident_close",
        triggered_by=f"owner:{owner_email}"[:120],
        previous_event_id=prev["id"] if prev else None,
    )
    return evaluate_and_record(db, triggered_by=f"owner:{owner_email}"[:120])


# ---------------------------------------------------------------------------
# The frozen interface (+ bounded lazy cache, fail-closed)
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"at": 0.0, "value": ("NORMAL", None)}
_consecutive_failures = 0


def _flag_off_posture() -> tuple[Posture, None]:
    raw = (settings.SYSTEM_POSTURE_OVERRIDE or "").strip().upper()
    if raw in _VALID:
        return raw, None  # type: ignore[return-value]
    return "NORMAL", None


def current_posture_event(db: Session | None = None) -> tuple[Posture, str | None]:
    """(posture, posture_event_id). Flag off → override/NORMAL with no event.
    Flag on → latest event via bounded cache; missing/stale → lazy
    evaluate-and-record; any failure → RESTRICTED (SAFE after
    _FAILURE_SAFE_THRESHOLD consecutive failures). Never a fake NORMAL."""
    global _consecutive_failures
    if not settings.SYSTEM_POSTURE_ENABLED:
        return _flag_off_posture()
    if db is None:
        return "RESTRICTED", None  # no session to read facts — fail closed

    now = dt.datetime.now(dt.timezone.utc).timestamp()
    with _cache_lock:
        if now - _cache["at"] < _CACHE_TTL_SECONDS:
            return _cache["value"]

    try:
        row = evaluate_and_record(db, triggered_by="auto")
        posture = row.get("posture", "RESTRICTED")
        event_id = row.get("id")
        _consecutive_failures = 0
        with _cache_lock:
            _cache["at"] = now
            _cache["value"] = (posture, event_id)
        return posture, event_id
    except Exception:  # noqa: BLE001 — deliberate fail-closed boundary
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        _consecutive_failures += 1
        posture = "SAFE" if _consecutive_failures >= _FAILURE_SAFE_THRESHOLD \
            else "RESTRICTED"
        return posture, None


def current_posture(db: Session | None = None) -> Posture:
    """Frozen Wave-1A signature. Pure read; never raises."""
    return current_posture_event(db)[0]


def reset_cache_for_tests() -> None:
    global _consecutive_failures
    with _cache_lock:
        _cache["at"] = 0.0
        _cache["value"] = ("NORMAL", None)
    _consecutive_failures = 0
