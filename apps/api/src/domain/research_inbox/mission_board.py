"""Research Mission Board — Wave 2B. Pure READ aggregation over existing
Research Inbox + Agent Gateway state. Spec: docs/architecture/
RESEARCH_MISSION_BOARD.md.

Hard properties (pinned by tests):
  * ZERO writes, zero job launches, zero state mutation, no LLM. The whole
    board is at most FOUR bounded SELECTs (tasks, reports, follow-up
    parents, gateway jobs) — no N+1, no unbounded history scans.
  * The board stores NOTHING. Every column is derived at read time from
    the same source facts the Inbox uses (`research_task`,
    `research_report` version chains, `agent_job` status). It can never
    disagree with the Inbox about a report's state because it reuses
    the same derivations (7-day citation-age boundary =
    service.DEFAULT_MAX_CITATION_AGE_DAYS).
  * One card per task. Column assignment is a single total function with
    pinned precedence (task cards):
        review_needed > stale > corrected > delivered > queued
    Running/Failed NEVER hold task cards: `agent_job` has no task linkage
    (no task_id column exists — verified against migration 115), so a
    task-level "running/failed execution" fact has NO producer. Gateway
    jobs appear as their own clearly-labelled job cards instead.
  * No report bodies, no raw citation payloads, no token secrets/hashes,
    no stack traces, no emails (stable labels: 'owner' / 'agent:<name>').
    All text fields are bounded server-side.
  * Staleness is ADVISORY (fresh | aging | stale | unknown), never a
    failure, and never claims market freshness without a stored as-of
    fact (citation observed_at or expires_at). Reports with neither are
    'unknown', not 'fresh'.
"""

from __future__ import annotations

import datetime
import json
import re

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db.models import ResearchReport, ResearchTask
from apps.api.src.domain.research_inbox.service import (
    DEFAULT_MAX_CITATION_AGE_DAYS,
)

# ---------------------------------------------------------------------------
# Versioned board policy — thresholds documented in
# docs/architecture/RESEARCH_MISSION_BOARD.md. Bump the version string when
# any threshold or precedence rule changes.
# ---------------------------------------------------------------------------
#: mission-board-2 (Wave 2C): jobs carrying research_task_id (migration
#: 121) contribute to their TASK's card — an active linked job moves the
#: task to Running; the latest unsuperseded failed linked job moves it to
#: Failed (superseded = a newer linked job in queued/running/succeeded OR
#: a report delivered after the failure). Linked jobs never emit separate
#: job cards. Historical NULL-linked jobs keep the mission-board-1
#: behavior exactly (labelled job cards, parameter-based retry
#: suppression) — a task association is never guessed.
MISSION_BOARD_RULE_SET_VERSION = "mission-board-2"

#: evidence age (newest citation observed_at): <=3d fresh, <=7d aging,
#: >7d stale. The 7-day boundary is the Inbox's own staleness boundary
#: (service.DEFAULT_MAX_CITATION_AGE_DAYS) — board and Inbox always agree
#: on 'stale'.
EVIDENCE_FRESH_DAYS = 3
EVIDENCE_STALE_DAYS = DEFAULT_MAX_CITATION_AGE_DAYS  # 7

#: a task with a schedule_expr (DEFINITION only — nothing executes it) whose
#: newest approved report is older than this is advisory-stale: the owner
#: asked for recurrence and has no recent answer. >= 2 weekends wide, so
#: weekends alone can never trip it.
SCHEDULED_OVERDUE_DAYS = 14

#: gateway job handlers are bounded read-only analytics that finish in
#: seconds; a 'running' row older than this means the dev-lane runner died
#: mid-job. The card STAYS in Running (no failure fact exists) with an
#: advisory 'stale' freshness.
RUNNING_STUCK_MINUTES = 60

# Bounded scans (deterministic ORDER BY + LIMIT; truncation is reported in
# board_health, never silent).
TASK_SCAN_CAP = 500
REPORT_SCAN_CAP = 2000
JOB_SCAN_CAP = 200

PER_COLUMN_DEFAULT = 30
PER_COLUMN_MAX = 100
PREVIEW_CHARS = 160
STATUS_TEXT_CHARS = 160
FOLLOW_UP_MAX_DEPTH = 5

#: display order (product spec §columns); NOT the precedence order.
COLUMN_ORDER = (
    "queued", "running", "review_needed", "delivered",
    "corrected", "stale", "failed",
)

COLUMN_HELP = {
    "queued": "Research tasks that have not delivered a usable report yet. "
              "Nothing here runs automatically — schedules are definitions "
              "only.",
    "running": "Research being worked on: tasks with an active linked job, "
               "plus older standalone gateway jobs that carry no task link.",
    "review_needed": "Generated reports waiting for your decision.",
    "delivered": "Current approved research with no corrections.",
    "corrected": "Research with retained earlier versions.",
    "stale": "Research that may no longer reflect current information.",
    "failed": "Research runs that ended without a usable result "
              "(hidden when a newer retry or report exists).",
}

FRESHNESS_VALUES = frozenset({"fresh", "aging", "stale", "unknown"})


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _as_utc(v: datetime.datetime | None) -> datetime.datetime | None:
    if v is None:
        return None
    if v.tzinfo is None:
        return v.replace(tzinfo=datetime.timezone.utc)
    return v


def _iso(v: datetime.datetime | None) -> str | None:
    v = _as_utc(v)
    return v.isoformat() if v is not None else None


def _clip(s: str | None, n: int) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _actor_label(raw: str | None, provenance: str | None) -> str:
    """Stable owner-safe display label — never an email address."""
    if raw and raw.startswith("agent:"):
        return raw[:64]
    if provenance == "human":
        return "owner"
    return "generated" if provenance == "generated" else "owner"


def _newest_observed_at(citations: object) -> datetime.datetime | None:
    """Newest citation observed_at, or None. Malformed timestamps are
    treated as absent (freshness degrades to 'unknown', never crashes)."""
    if not isinstance(citations, list):
        return None
    newest: datetime.datetime | None = None
    for c in citations:
        if not isinstance(c, dict):
            continue
        raw = c.get("observed_at")
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            ts = datetime.datetime.fromisoformat(
                raw.strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        ts = _as_utc(ts)
        if newest is None or ts > newest:
            newest = ts
    return newest


# ---------------------------------------------------------------------------
# pure classification (unit-testable without a DB)
# ---------------------------------------------------------------------------

def report_freshness(report: dict, now: datetime.datetime) -> tuple[str, str]:
    """(freshness, reason) for one report dict — mission-board-1 policy.

    Evidence first: newest citation observed_at age <=3d fresh, <=7d aging,
    >7d stale. Without citations: expires_at in the future = fresh (owner-
    declared validity window), past = stale. With NEITHER stored as-of fact
    the answer is 'unknown' — delivery time alone never claims freshness."""
    expires = _as_utc(report.get("expires_at"))
    if expires is not None and now > expires:
        return "stale", "past its declared validity window"
    newest = _newest_observed_at(report.get("citations"))
    if newest is not None:
        age = (now - newest).days
        if age <= EVIDENCE_FRESH_DAYS:
            return "fresh", f"evidence observed {age}d ago"
        if age <= EVIDENCE_STALE_DAYS:
            return "aging", f"evidence observed {age}d ago"
        return "stale", f"evidence observed {age}d ago"
    if expires is not None:
        return "fresh", "within its declared validity window"
    return "unknown", "no evidence timestamps stored"


def _execution_facts(jobs: list[dict], chain: list[dict],
                     now: datetime.datetime) -> dict:
    """Derive task-level execution facts from the task's LINKED jobs
    (mission-board-2). `jobs` ascending by created_at.

    failed_relevant = the newest failed job NOT superseded by (a) a newer
    linked job in queued/running/succeeded — task-linkage retry rule,
    never parameter matching — or (b) any report delivered after the
    failure (the work eventually landed)."""
    jobs = sorted(
        jobs or [],
        key=lambda j: ((_iso(j.get("created_at")) or ""),
                       j.get("job_uid") or ""),
    )
    active = [j for j in jobs if j.get("status") in ("queued", "running")]
    failed_relevant = None
    for idx, j in enumerate(jobs):
        if j.get("status") != "failed":
            continue
        newer_attempt = any(
            o.get("status") in ("queued", "running", "succeeded")
            for o in jobs[idx + 1:]
        )
        f_at = _as_utc(j.get("created_at"))
        newer_report = any(
            _as_utc(r.get("delivered_at")) is not None and f_at is not None
            and _as_utc(r["delivered_at"]) > f_at
            for r in chain
        )
        if not newer_attempt and not newer_report:
            failed_relevant = j
    last = jobs[-1] if jobs else None
    stuck = any(
        j.get("status") == "running" and _as_utc(j.get("started_at"))
        and (now - _as_utc(j["started_at"]))
        > datetime.timedelta(minutes=RUNNING_STUCK_MINUTES)
        for j in active
    )
    return {
        "jobs": jobs,
        "active": active,
        "failed_relevant": failed_relevant,
        "last": last,
        "stuck": stuck,
    }


def classify_task(task: dict, chain: list[dict],
                  now: datetime.datetime,
                  jobs: list[dict] | None = None) -> dict | None:
    """One task + its full version chain + its LINKED gateway jobs -> ONE
    board card (or None when the task is off-board: closed with nothing
    delivered and no execution activity).

    mission-board-2 precedence (pinned):
        running (active linked job) > review_needed (pending latest report)
        > failed (latest unsuperseded failed linked job) > stale >
        corrected > delivered > queued.
    Rationale: an in-flight run is the truthful "being worked on" state
    even when a pending report exists (the card still surfaces the pending
    review context); a pending report delivered AFTER a failure outranks
    the failure (the failure is history once work landed); an approved
    report delivered after a failed job suppresses Failed the same way.
    `chain` must be sorted ascending by version; latest version is current
    (two versions of one task NEVER become two cards; linked jobs never
    become separate job cards)."""
    chain = sorted(chain, key=lambda r: r["version"])
    latest = chain[-1] if chain else None
    corrections = sum(
        1 for r in chain if r.get("supersedes_report_id") is not None)
    corrected_chain = corrections > 0
    ex = _execution_facts(jobs or [], chain, now)

    has_usable = any(r["review_status"] == "approved" for r in chain)

    # -- column ------------------------------------------------------------
    if ex["active"]:
        column = "running"
        status = ex["active"][-1].get("status")
        if ex["stuck"]:
            freshness = "stale"
            why = (f"linked job running for over {RUNNING_STUCK_MINUTES} "
                   "minutes — the offline runner may have stopped")
        else:
            freshness, why = "fresh", f"linked job is {status}"
    elif latest is not None and latest["review_status"] == "pending":
        column = "review_needed"
        freshness, why = report_freshness(latest, now)
    elif ex["failed_relevant"] is not None:
        column = "failed"
        freshness = "unknown"
        why = _clip(ex["failed_relevant"].get("error_summary"),
                    STATUS_TEXT_CHARS) or "linked job failed"
    elif latest is None:
        if task.get("status") == "closed":
            return None  # closed and never delivered: owner retired it
        column = "queued"
        freshness, why = "unknown", "no report delivered yet"
    elif not has_usable:
        # every version rejected — the task is still waiting for a usable
        # answer; that is Queued (with context), not Delivered/Failed.
        if task.get("status") == "closed":
            return None
        column = "queued"
        freshness, why = "unknown", (
            f"v{latest['version']} was rejected; no approved report")
    else:
        freshness, why = report_freshness(latest, now)
        if latest["review_status"] == "approved":
            # scheduled-overdue is advisory staleness on top of evidence
            if (freshness != "stale" and task.get("schedule_expr")
                    and _as_utc(latest.get("delivered_at")) is not None
                    and (now - _as_utc(latest["delivered_at"])).days
                    > SCHEDULED_OVERDUE_DAYS):
                freshness = "stale"
                why = (f"scheduled task with no report in "
                       f"{(now - _as_utc(latest['delivered_at'])).days}d")
        if freshness == "stale":
            column = "stale"
        elif corrected_chain:
            column = "corrected"   # product policy: correction history is
            # the primary story once a chain has retained prior versions
        elif latest["review_status"] == "approved":
            column = "delivered"
        else:
            # latest rejected but an older approved version exists — the
            # chain has been corrected-then-rejected; correction history
            # is the honest column.
            column = "corrected"

    delivered_at = _as_utc(latest.get("delivered_at")) if latest else None
    review_age_days = None
    if latest and latest["review_status"] == "pending" and delivered_at:
        review_age_days = max(0, (now - delivered_at).days)

    citations = latest.get("citations") if latest else None
    card = {
        "kind": "task",
        "card_id": f"task:{task['id']}",
        "task_id": task["id"],
        "column": column,
        "title": _clip(task.get("title"), 200),
        "question_preview": _clip(task.get("question"), PREVIEW_CHARS),
        "scope": _clip(task.get("scope"), 64),
        "task_status": task.get("status"),
        "schedule": (
            {"defined": True,
             "note": "schedule is a definition only — nothing runs "
                     "automatically"}
            if task.get("schedule_expr") else {"defined": False}
        ),
        "is_follow_up": bool(task.get("follow_up_of_task_id")),
        "follow_up": None,  # filled by the service (needs parent lookups)
        "latest_report": (
            {
                "report_id": latest["id"],
                "version": latest["version"],
                "review_status": latest["review_status"],
                "provenance": latest.get("provenance"),
                "generated_by_label": _actor_label(
                    latest.get("generated_by"), latest.get("provenance")),
                "reviewed_by_label": (
                    "owner" if latest.get("reviewed_by") else None),
                "delivered_at": _iso(latest.get("delivered_at")),
                "citation_count": (
                    len(citations) if isinstance(citations, list) else 0),
                "review_age_days": review_age_days,
            }
            if latest else None
        ),
        "chain": {
            "versions": len(chain),
            "prior_retained": max(0, len(chain) - 1),
            "corrections": corrections,
            "current_version": latest["version"] if latest else None,
            "current_status": latest["review_status"] if latest else None,
            "last_corrected_by_label": next(
                (_actor_label(r.get("generated_by"), r.get("provenance"))
                 for r in reversed(chain)
                 if r.get("supersedes_report_id") is not None),
                None,
            ),
        },
        "execution": (
            {
                "attempts": len(ex["jobs"]),
                "retries": max(0, len(ex["jobs"]) - 1),
                "active_status": (ex["active"][-1].get("status")
                                  if ex["active"] else None),
                "last_attempt_at": _iso(ex["last"].get("created_at"))
                if ex["last"] else None,
                "last_error": (
                    _clip(ex["failed_relevant"].get("error_summary"),
                          STATUS_TEXT_CHARS)
                    if ex["failed_relevant"] is not None else None),
                "history_available": True,
            }
            if ex["jobs"] else None
        ),
        "freshness": freshness,
        "freshness_reason": _clip(why, STATUS_TEXT_CHARS),
        "sort_ts": _iso(
            (ex["last"].get("created_at") if column in ("running", "failed")
             and ex["last"] else None)
            or delivered_at or task.get("created_at")),
        "created_at": _iso(task.get("created_at")),
    }
    return card


def classify_jobs(jobs: list[dict], now: datetime.datetime) -> list[dict]:
    """HISTORICAL UNLINKED gateway jobs (research_task_id IS NULL) ->
    standalone job cards for Running / Failed. This is the preserved
    mission-board-1 behavior — a task association is NEVER guessed for
    old jobs. Linked jobs must not reach this function (they contribute
    to their task's card via classify_task).

    * Running: status queued|running (real rows only — the enum has no
      'claimed'/'cancellation requested'; verified against jobs.py).
    * Failed: status failed, UNLESS a newer job with the same job_type and
      byte-identical params exists in queued/running/succeeded — that newer
      attempt supersedes the failure (parameter-matching retry rule stays
      ONLY for these unlinked historical jobs).
    * Cancelled is owner-initiated before start — not a failure; excluded.
    * Cards say the job is not linked to a task."""
    def _pkey(j: dict) -> str:
        try:
            return json.dumps(j.get("params") or {}, sort_keys=True)
        except (TypeError, ValueError):
            return str(j.get("params"))

    cards: list[dict] = []
    for j in jobs:
        status = j.get("status")
        if status in ("queued", "running"):
            column = "running"
            started = _as_utc(j.get("started_at"))
            stuck = (
                status == "running" and started is not None
                and (now - started)
                > datetime.timedelta(minutes=RUNNING_STUCK_MINUTES)
            )
            freshness = "stale" if stuck else "fresh"
            why = (f"running for over {RUNNING_STUCK_MINUTES} minutes — "
                   "the offline runner may have stopped" if stuck
                   else f"job is {status}")
        elif status == "failed":
            superseded = any(
                o is not j
                and o.get("job_type") == j.get("job_type")
                and _pkey(o) == _pkey(j)
                and o.get("status") in ("queued", "running", "succeeded")
                and (_as_utc(o.get("created_at")) or now)
                > (_as_utc(j.get("created_at")) or now)
                for o in jobs
            )
            if superseded:
                continue  # a newer retry owns the story
            column = "failed"
            freshness = "unknown"
            why = _clip(j.get("error_summary"),
                        STATUS_TEXT_CHARS) or "job failed"
        else:
            continue  # succeeded/cancelled are not board columns

        cards.append({
            "kind": "gateway_job",
            "card_id": f"job:{j['job_uid']}",
            "column": column,
            "title": f"Gateway job — {j.get('job_type')}",
            "job_uid": j["job_uid"],
            "job_type": j.get("job_type"),
            "job_status": status,
            "token_prefix": j.get("token_prefix"),  # public prefix, no hash
            "task_link": None,  # no producer: agent_job has no task column
            "queued_at": _iso(j.get("created_at")),
            "started_at": _iso(j.get("started_at")),
            "finished_at": _iso(j.get("finished_at")),
            "freshness": freshness,
            "freshness_reason": _clip(why, STATUS_TEXT_CHARS),
            "sort_ts": _iso(j.get("finished_at") or j.get("created_at")),
        })
    return cards


# ---------------------------------------------------------------------------
# follow-up chains — bounded, cycle-safe
# ---------------------------------------------------------------------------

def follow_up_summary(task_id: str, parents: dict[str, dict]) -> dict | None:
    """Bounded parent walk (<= FOLLOW_UP_MAX_DEPTH). `parents` maps
    task_id -> {id, title, follow_up_of_task_id}. Cycles or broken links
    -> a safe 'relationship unavailable' shape, never a crash/loop."""
    me = parents.get(task_id)
    if me is None or not me.get("follow_up_of_task_id"):
        return None
    seen = {task_id}
    depth = 0
    cur = me.get("follow_up_of_task_id")
    parent_title = None
    parent_id = None
    while cur and depth < FOLLOW_UP_MAX_DEPTH:
        if cur in seen:
            return {"available": False,
                    "note": "relationship unavailable (cycle detected)"}
        seen.add(cur)
        depth += 1
        node = parents.get(cur)
        if depth == 1:
            parent_id = cur
            parent_title = _clip(node.get("title"), 120) if node else None
        if node is None:
            break
        cur = node.get("follow_up_of_task_id")
    return {
        "available": True,
        "parent_task_id": parent_id,
        "parent_title": parent_title,
        "depth": depth,
        "depth_capped": bool(cur) and depth >= FOLLOW_UP_MAX_DEPTH,
    }


# ---------------------------------------------------------------------------
# deterministic ordering
# ---------------------------------------------------------------------------

def _sort_cards(column: str, cards: list[dict]) -> list[dict]:
    """review_needed: oldest waiting first (action order); everything else:
    newest first. card_id is the total tiebreak — ordering is deterministic
    for identical inputs."""
    reverse = column != "review_needed"
    return sorted(
        cards,
        key=lambda c: ((c.get("sort_ts") or ""), c["card_id"]),
        reverse=reverse,
    )


# ---------------------------------------------------------------------------
# the aggregation entrypoint — bounded reads only
# ---------------------------------------------------------------------------

def _fetch_jobs(db: Session, notes: list[str]) -> list[dict]:
    """Bounded gateway-job read. Gateway OFF -> zero queries and an explicit
    health note (tasks are NEVER marked failed because the gateway is off).
    A missing table (envs without migration 115) degrades the same way."""
    if not settings.AGENT_GATEWAY_ENABLED:
        notes.append(
            "Agent Gateway is off — Running/Failed job activity is not "
            "shown (tasks are unaffected).")
        return []
    try:
        rows = db.execute(
            text(
                "SELECT job_uid, job_type, params, status, token_prefix, "
                "created_at, started_at, finished_at, error_summary, "
                "research_task_id "
                "FROM agent_job "
                "WHERE status IN ('queued','running','failed','succeeded') "
                "ORDER BY created_at DESC, job_uid LIMIT :cap"
            ),
            {"cap": JOB_SCAN_CAP},
        ).mappings().all()
    except Exception:  # noqa: BLE001 — table absent / store unavailable
        db.rollback()
        notes.append(
            "Gateway job store unavailable — Running/Failed job activity "
            "is not shown.")
        return []
    return [dict(r) for r in rows]


def build_mission_board(
    db: Session,
    *,
    now: datetime.datetime | None = None,
    column: str | None = None,
    q: str | None = None,
    provenance: str | None = None,
    freshness: str | None = None,
    per_column: int = PER_COLUMN_DEFAULT,
) -> dict:
    """Compose the board. Read-only: four bounded SELECTs, then pure
    in-memory derivation. Filters are owner-safe (validated at the route);
    `q` matches task titles / job types case-insensitively in memory —
    no SQL is built from it."""
    now = _as_utc(now) or _now()
    per_column = max(1, min(PER_COLUMN_MAX, per_column))
    notes: list[str] = []

    # 1) tasks (bounded, deterministic)
    task_rows = list(db.execute(
        select(ResearchTask)
        .order_by(ResearchTask.created_at.desc(), ResearchTask.id)
        .limit(TASK_SCAN_CAP)
    ).scalars())
    if len(task_rows) >= TASK_SCAN_CAP:
        notes.append(
            f"task scan capped at {TASK_SCAN_CAP} newest tasks — older "
            "tasks are not on the board.")

    tasks = [
        {
            "id": t.id, "title": t.title, "question": t.question,
            "scope": t.scope, "schedule_expr": t.schedule_expr,
            "status": t.status,
            "follow_up_of_task_id": t.follow_up_of_task_id,
            "source_report_id": getattr(t, "source_report_id", None),
            "created_at": t.created_at,
        }
        for t in task_rows
    ]
    task_ids = [t["id"] for t in tasks]

    # 2) reports for those tasks (one query, bounded)
    reports_by_task: dict[str, list[dict]] = {}
    newest_report_at: datetime.datetime | None = None
    if task_ids:
        report_rows = list(db.execute(
            select(ResearchReport)
            .where(ResearchReport.task_id.in_(task_ids))
            .order_by(ResearchReport.task_id, ResearchReport.version)
            .limit(REPORT_SCAN_CAP)
        ).scalars())
        if len(report_rows) >= REPORT_SCAN_CAP:
            notes.append(
                f"report scan capped at {REPORT_SCAN_CAP} rows — some "
                "version chains may be incomplete.")
        for r in report_rows:
            reports_by_task.setdefault(r.task_id, []).append({
                "id": r.id, "version": r.version,
                "citations": r.citations,
                "provenance": r.provenance,
                "generated_by": r.generated_by,
                "review_status": r.review_status,
                "reviewed_by": r.reviewed_by,
                "delivered_at": r.delivered_at,
                "expires_at": r.expires_at,
                "supersedes_report_id": r.supersedes_report_id,
            })
            ca = _as_utc(r.created_at)
            if ca and (newest_report_at is None or ca > newest_report_at):
                newest_report_at = ca

    # 3) follow-up parents that fell outside the task scan (one query)
    parents: dict[str, dict] = {t["id"]: t for t in tasks}
    missing = {
        t["follow_up_of_task_id"] for t in tasks
        if t["follow_up_of_task_id"]
        and t["follow_up_of_task_id"] not in parents
    }
    if missing:
        for t in db.execute(
            select(ResearchTask).where(ResearchTask.id.in_(missing))
            .limit(TASK_SCAN_CAP)
        ).scalars():
            parents[t.id] = {
                "id": t.id, "title": t.title,
                "follow_up_of_task_id": t.follow_up_of_task_id,
            }

    # 4) gateway jobs (bounded; zero queries when the gateway is off)
    jobs = _fetch_jobs(db, notes)
    # mission-board-2 split: linked jobs feed their TASK's card; NULL-linked
    # historical jobs keep the mission-board-1 standalone-card behavior.
    scanned_ids = set(task_ids)
    linked_by_task: dict[str, list[dict]] = {}
    unlinked_jobs: list[dict] = []
    dropped_linked = 0
    for j in jobs:
        tid = j.get("research_task_id")
        if tid is None:
            unlinked_jobs.append(j)
        elif tid in scanned_ids:
            linked_by_task.setdefault(tid, []).append(j)
        else:
            dropped_linked += 1  # task fell outside the (capped) scan
    if dropped_linked:
        notes.append(
            f"{dropped_linked} linked job(s) reference tasks outside the "
            f"task scan cap and are not shown.")

    # 5) exact source-report versions for follow-up cards (one bounded
    # query; historical follow-ups without a stored source stay null —
    # never guessed).
    source_meta: dict[str, dict] = {}
    src_ids = {t["source_report_id"] for t in tasks if t["source_report_id"]}
    if src_ids:
        src_rows = db.execute(
            select(ResearchReport.id, ResearchReport.version,
                   ResearchReport.task_id)
            .where(ResearchReport.id.in_(src_ids))
        ).all()
        max_by_task: dict[str, int] = {}
        for tid2, chain_rows in reports_by_task.items():
            max_by_task[tid2] = max(r["version"] for r in chain_rows)
        for rid, ver, rtask in src_rows:
            maxv = max_by_task.get(rtask)
            source_meta[rid] = {
                "version": ver,
                "superseded": (ver < maxv) if maxv is not None else None,
            }

    # -- derive cards (pure) -------------------------------------------------
    cards: list[dict] = []
    for t in tasks:
        card = classify_task(t, reports_by_task.get(t["id"], []), now,
                             jobs=linked_by_task.get(t["id"]))
        if card is None:
            continue
        if card["is_follow_up"]:
            card["follow_up"] = follow_up_summary(t["id"], parents)
            meta = source_meta.get(t["source_report_id"] or "")
            if card["follow_up"] is not None:
                card["follow_up"]["source_version"] = (
                    meta["version"] if meta else None)
                card["follow_up"]["source_superseded"] = (
                    meta["superseded"] if meta else None)
        cards.append(card)
    cards.extend(classify_jobs(unlinked_jobs, now))

    # -- owner-safe filters (in memory; q never reaches SQL) ------------------
    if q:
        needle = q.strip().lower()[:64]
        cards = [
            c for c in cards
            if needle in (c.get("title") or "").lower()
            or needle in (c.get("job_type") or "").lower()
        ]
    if provenance:
        cards = [
            c for c in cards
            if c["kind"] == "task" and c.get("latest_report")
            and c["latest_report"]["provenance"] == provenance
        ]
    if freshness:
        cards = [c for c in cards if c.get("freshness") == freshness]

    # -- columns, counts, caps -------------------------------------------------
    by_column: dict[str, list[dict]] = {k: [] for k in COLUMN_ORDER}
    for c in cards:
        by_column[c["column"]].append(c)

    wanted = [column] if column else list(COLUMN_ORDER)
    columns = []
    counts: dict[str, int] = {}
    for key in COLUMN_ORDER:
        total = len(by_column[key])
        counts[key] = total
        if key not in wanted:
            continue
        shown = _sort_cards(key, by_column[key])[:per_column]
        columns.append({
            "key": key,
            "title": key.replace("_", " ").title(),
            "help": COLUMN_HELP[key],
            "total": total,
            "shown": len(shown),
            "overflow": max(0, total - len(shown)),
            "cards": shown,
        })

    newest_task_at = max(
        (ts for ts in (_as_utc(t["created_at"]) for t in tasks) if ts),
        default=None,
    )
    newest_job_at = max(
        (ts for ts in (_as_utc(j.get("created_at")) for j in jobs) if ts),
        default=None,
    )

    return {
        "rule_set_version": MISSION_BOARD_RULE_SET_VERSION,
        "generated_at": _iso(now),
        "gateway_enabled": bool(settings.AGENT_GATEWAY_ENABLED),
        "counts": counts,
        "columns": columns,
        "board_health": {
            "complete": not notes,
            "notes": notes,
        },
        "source_freshness": {
            "newest_task_at": _iso(newest_task_at),
            "newest_report_at": _iso(newest_report_at),
            "newest_job_at": _iso(newest_job_at),
        },
    }
