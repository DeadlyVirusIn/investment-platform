"""Research Inbox service — the ONLY mutation path for tasks + reports.

Spec: docs/architecture/RESEARCH_INBOX_SPEC.md (trust posture §1, version
semantics §4). Invariants enforced here:

* **Delivered reports are immutable.** There is deliberately NO update or
  delete path for a delivered ``research_report`` anywhere in this module
  (pinned by test introspection, thesis-revision precedent). Corrections
  go through :func:`correct_report`, which inserts a NEW ``version+1`` row
  with ``supersedes_report_id`` set and touches nothing on the old row —
  its "superseded" state is derived at read time, never stamped.
* **Citations carry provenance or they don't exist.** Every citation must
  be ``{source, url, observed_at}`` with a non-empty ``url`` and a parseable
  ``observed_at`` timestamp; reports with unverifiable evidence are
  rejected before insert.
* **Generated content is FORCED to review_status='pending'** server-side
  regardless of caller input — the human review gate is the containment
  boundary (thesis-evidence precedent). Human (owner-written) reports are
  approved on insert with the author as reviewer.
* **Review decisions are one-shot** (pending → approved|rejected) and only
  the three review fields change — never body/citations/version.
* **Staleness is computed, never stored** — :func:`report_state` derives
  ``fresh | stale | superseded`` from ``expires_at``, citation
  ``observed_at`` age, and the existence of a superseding row.
* ``schedule_expr`` is stored as a DEFINITION only. Nothing in this module
  (or this slice) parses, schedules, or executes it.
"""

from __future__ import annotations

import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import ResearchReport, ResearchTask

# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------

TASK_STATUSES: frozenset[str] = frozenset({"open", "paused", "closed"})
PROVENANCES: frozenset[str] = frozenset({"generated", "human"})
REVIEW_STATUSES: frozenset[str] = frozenset({"pending", "approved", "rejected"})

#: default staleness window: newest citation older than this ⇒ stale
DEFAULT_MAX_CITATION_AGE_DAYS = 7

#: derived report states (spec: staleness is computed, never hidden)
REPORT_STATES: frozenset[str] = frozenset({"fresh", "stale", "superseded"})


# ---------------------------------------------------------------------------
# errors (mapped to HTTP codes when the router lands — not in this slice)
# ---------------------------------------------------------------------------

class ResearchInboxError(Exception):
    """Base for research-inbox domain errors."""


class InvalidInput(ResearchInboxError):
    """Bad vocabulary / missing required field (422 at a future API)."""


class CitationInvalid(InvalidInput):
    """A citation is missing url or observed_at — unverifiable evidence."""


class TaskNotFound(ResearchInboxError):
    pass


class ReportNotFound(ResearchInboxError):
    pass


class ReviewStateError(ResearchInboxError):
    """Report is not pending — review decisions are one-shot."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    """Normalize naive timestamps to UTC (DB timestamptz convention)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


def _parse_observed_at(raw: object, *, ordinal: int) -> datetime.datetime:
    """Accept a datetime or an ISO-8601 string; anything else is rejected."""
    if isinstance(raw, datetime.datetime):
        return _as_utc(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            return _as_utc(
                datetime.datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            )
        except ValueError:
            pass
    raise CitationInvalid(
        f"citation [{ordinal}] observed_at {raw!r} is not a valid "
        "ISO-8601 timestamp"
    )


def _validate_citations(citations: object) -> list[dict]:
    """Validate + normalize the citations payload.

    Every citation MUST carry a non-empty ``url`` and a parseable
    ``observed_at`` — evidence without provenance is rejected (spec §2:
    cited, timestamped evidence). ``source`` is carried through as given.
    Returns JSON-serializable rows with observed_at as ISO strings.
    """
    if citations is None:
        return []
    if not isinstance(citations, list):
        raise CitationInvalid("citations must be a list of citation objects")
    normalized: list[dict] = []
    for i, item in enumerate(citations, start=1):
        if not isinstance(item, dict):
            raise CitationInvalid(f"citation [{i}] must be an object")
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            raise CitationInvalid(f"citation [{i}] is missing a url")
        if "observed_at" not in item or item.get("observed_at") in (None, ""):
            raise CitationInvalid(f"citation [{i}] is missing observed_at")
        observed = _parse_observed_at(item["observed_at"], ordinal=i)
        normalized.append(
            {
                "source": item.get("source"),
                "url": url.strip(),
                "observed_at": observed.isoformat(),
            }
        )
    return normalized


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------

def create_task(
    db: Session,
    *,
    title: str,
    question: str,
    scope: str | None = None,
    schedule_expr: str | None = None,
    created_by: str = "owner",
    follow_up_of_task_id: str | None = None,
) -> ResearchTask:
    """Create a standing research question (status='open').

    ``scope`` is a symbols CSV ("NVDA,TSM") or free theme text.
    ``schedule_expr`` is stored verbatim as a DEFINITION — this slice
    never parses or executes it. Follow-up tasks must point at an
    existing task (provenance chain, RESTRICT at the DB layer)."""
    title = _clean(title)
    question = _clean(question)
    if not title or not question:
        raise InvalidInput("title and question are required")
    if len(title) > 200:
        raise InvalidInput("title exceeds 200 chars")
    if follow_up_of_task_id:
        parent = db.get(ResearchTask, follow_up_of_task_id)
        if parent is None:
            raise TaskNotFound(
                f"follow_up_of_task_id {follow_up_of_task_id!r} does not exist"
            )

    task = ResearchTask(
        title=title,
        question=question,
        scope=_clean(scope) or None,
        schedule_expr=_clean(schedule_expr) or None,
        status="open",
        created_by=created_by,
        follow_up_of_task_id=follow_up_of_task_id,
    )
    db.add(task)
    db.commit()
    return task


# ---------------------------------------------------------------------------
# reports — insert-only; delivered rows are frozen
# ---------------------------------------------------------------------------

def _next_version(db: Session, task_id: str) -> int:
    return (
        db.execute(
            select(func.coalesce(func.max(ResearchReport.version), 0)).where(
                ResearchReport.task_id == task_id
            )
        ).scalar_one()
        + 1
    )


def _insert_report(
    db: Session,
    task: ResearchTask,
    *,
    body: str,
    citations: object,
    provenance: str,
    created_by: str,
    expires_at: datetime.datetime | None,
    supersedes_report_id: str | None,
) -> ResearchReport:
    """The single report write path (create + correct both land here).

    Inserts a frozen row: delivered_at is stamped now, version is
    server-assigned (max+1 per task, UNIQUE(task_id, version) is the race
    backstop). No function in this module ever updates body/citations/
    version/delivered_at after this insert."""
    body = _clean(body)
    if not body:
        raise InvalidInput("body is required")
    if provenance not in PROVENANCES:
        raise InvalidInput(f"invalid provenance {provenance!r}")
    normalized = _validate_citations(citations)

    if provenance == "generated":
        # Containment boundary: generated content always starts pending;
        # only approve_report/reject_report move it.
        review_status = "pending"
        reviewed_by = None
        reviewed_at = None
    else:  # human — the owner wrote it; author is the reviewer
        review_status = "approved"
        reviewed_by = created_by
        reviewed_at = _now()

    row = ResearchReport(
        task_id=task.id,
        version=_next_version(db, task.id),
        body=body,
        citations=normalized,
        provenance=provenance,
        review_status=review_status,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        delivered_at=_now(),
        expires_at=_as_utc(expires_at) if expires_at else None,
        supersedes_report_id=supersedes_report_id,
    )
    db.add(row)
    db.commit()
    return row


def create_report(
    db: Session,
    task_id: str,
    *,
    body: str,
    citations: object = None,
    provenance: str = "generated",
    created_by: str = "owner",
    expires_at: datetime.datetime | None = None,
    review_status: str | None = None,  # noqa: ARG001 — deliberately ignored
) -> ResearchReport:
    """Deliver a new report version for a task.

    ``review_status`` from the caller is DELIBERATELY IGNORED: generated
    reports are forced to 'pending' server-side; human reports are
    approved with the author as reviewer. Citation shape is validated
    (every citation needs url + observed_at) before anything is written."""
    task = db.get(ResearchTask, task_id)
    if task is None:
        raise TaskNotFound(f"task {task_id!r} does not exist")
    return _insert_report(
        db,
        task,
        body=body,
        citations=citations,
        provenance=provenance,
        created_by=created_by,
        expires_at=expires_at,
        supersedes_report_id=None,
    )


def correct_report(
    db: Session,
    old_report_id: str,
    *,
    new_body: str,
    citations: object = None,
    provenance: str = "human",
    created_by: str = "owner",
    expires_at: datetime.datetime | None = None,
) -> ResearchReport:
    """Correct a delivered report by INSERTING version+1 that supersedes it.

    The old row is never touched — not a flag, not a timestamp, nothing
    (byte-identical after this call; pinned in tests). Its 'superseded'
    state is derived by :func:`report_state` from the existence of this
    new row. ``citations=None`` carries the old report's citations forward
    (a text correction keeps its evidence); pass a list to replace them."""
    old = db.get(ResearchReport, old_report_id)
    if old is None:
        raise ReportNotFound(f"report {old_report_id!r} does not exist")
    task = db.get(ResearchTask, old.task_id)
    return _insert_report(
        db,
        task,
        body=new_body,
        citations=old.citations if citations is None else citations,
        provenance=provenance,
        created_by=created_by,
        expires_at=expires_at,
        supersedes_report_id=old.id,
    )


# ---------------------------------------------------------------------------
# review — the ONLY post-delivery writes, and only the three review fields
# ---------------------------------------------------------------------------

def _review_report(
    db: Session, report_id: str, *, reviewer: str, decision: str
) -> ResearchReport:
    reviewer = _clean(reviewer)
    if not reviewer:
        raise InvalidInput("reviewer identity is required")
    row = db.get(ResearchReport, report_id)
    if row is None:
        raise ReportNotFound(f"report {report_id!r} does not exist")
    if row.review_status != "pending":
        raise ReviewStateError(
            f"report {report_id!r} is already {row.review_status!r}; "
            "review decisions are one-shot (corrections are new versions "
            "via correct_report)"
        )
    # Review never edits content — only the three review fields change.
    row.review_status = decision
    row.reviewed_by = reviewer
    row.reviewed_at = _now()
    db.commit()
    return row


def approve_report(db: Session, report_id: str, *, reviewer: str) -> ResearchReport:
    """Approve a pending report — a human has read it (the action gate)."""
    return _review_report(db, report_id, reviewer=reviewer, decision="approved")


def reject_report(db: Session, report_id: str, *, reviewer: str) -> ResearchReport:
    """Reject a pending report — retained forever, never deleted."""
    return _review_report(db, report_id, reviewer=reviewer, decision="rejected")


# ---------------------------------------------------------------------------
# staleness — derived at read time, never stored
# ---------------------------------------------------------------------------

def report_state(
    db: Session,
    report: ResearchReport,
    now: datetime.datetime | None = None,
    *,
    max_citation_age_days: int = DEFAULT_MAX_CITATION_AGE_DAYS,
) -> str:
    """Derive ``fresh | stale | superseded`` for a report at ``now``.

    Precedence: superseded (a newer version points at this row via
    supersedes_report_id) > stale (``expires_at`` passed OR the NEWEST
    citation ``observed_at`` is older than ``max_citation_age_days``)
    > fresh. Reports with no citations are judged on ``expires_at`` alone
    — there is no evidence age to measure."""
    now = _as_utc(now) if now else _now()

    superseded = db.execute(
        select(ResearchReport.id)
        .where(ResearchReport.supersedes_report_id == report.id)
        .limit(1)
    ).scalar()
    if superseded:
        return "superseded"

    if report.expires_at is not None and now > _as_utc(report.expires_at):
        return "stale"

    citations = report.citations or []
    if citations:
        newest = max(
            _parse_observed_at(c.get("observed_at"), ordinal=i)
            for i, c in enumerate(citations, start=1)
        )
        if now - newest > datetime.timedelta(days=max_citation_age_days):
            return "stale"

    return "fresh"
