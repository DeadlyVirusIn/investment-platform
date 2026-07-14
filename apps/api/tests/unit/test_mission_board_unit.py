"""Wave 2B — Mission Board pure-classification unit tests.

Pins: every column mapping, precedence (review_needed > stale > corrected >
delivered > queued), one card per task, latest-version-is-current, job
retry supersession, cancelled exclusion, stuck-running advisory, follow-up
chains + cycle defence, malformed timestamps, freshness policy
(mission-board-1), deterministic ordering, and that no board state exists
without a producer (no 'blocked', tasks never in running/failed).
"""

from __future__ import annotations

import datetime

from apps.api.src.domain.research_inbox.mission_board import (
    FOLLOW_UP_MAX_DEPTH,
    MISSION_BOARD_RULE_SET_VERSION,
    classify_jobs,
    classify_task,
    follow_up_summary,
    report_freshness,
    _sort_cards,
)

NOW = datetime.datetime(2026, 7, 13, 12, 0, tzinfo=datetime.timezone.utc)


def _ts(days_ago: float) -> datetime.datetime:
    return NOW - datetime.timedelta(days=days_ago)


def _task(**kw) -> dict:
    base = {"id": "t1", "title": "NVDA supply chain", "question": "Q?",
            "scope": None, "schedule_expr": None, "status": "open",
            "follow_up_of_task_id": None, "created_at": _ts(10)}
    base.update(kw)
    return base


def _report(version=1, review="approved", *, cite_days=1.0, expires=None,
            supersedes=None, provenance="generated", delivered_days=1.0,
            **kw) -> dict:
    base = {
        "id": f"r{version}", "version": version,
        "citations": [{"source": "s", "url": "https://x",
                       "observed_at": _ts(cite_days).isoformat()}]
        if cite_days is not None else [],
        "provenance": provenance, "generated_by": None,
        "review_status": review, "reviewed_by": None,
        "delivered_at": _ts(delivered_days), "expires_at": expires,
        "supersedes_report_id": supersedes,
    }
    base.update(kw)
    return base


# ── column mapping ─────────────────────────────────────────────────────────

def test_no_reports_is_queued_unknown():
    c = classify_task(_task(), [], NOW)
    assert c["column"] == "queued"
    assert c["freshness"] == "unknown"
    assert c["latest_report"] is None


def test_pending_latest_is_review_needed():
    c = classify_task(_task(), [_report(1, "pending")], NOW)
    assert c["column"] == "review_needed"
    assert c["latest_report"]["review_age_days"] == 1


def test_approved_single_fresh_is_delivered():
    c = classify_task(_task(), [_report(1, "approved", cite_days=1)], NOW)
    assert c["column"] == "delivered"
    assert c["freshness"] == "fresh"


def test_approved_v1_plus_pending_v2_is_review_needed_with_chain():
    chain = [_report(1, "approved"),
             _report(2, "pending", supersedes="r1")]
    c = classify_task(_task(), chain, NOW)
    assert c["column"] == "review_needed"       # precedence over corrected
    assert c["chain"]["corrections"] == 1
    assert c["chain"]["current_version"] == 2


def test_corrected_approved_chain_is_corrected_not_delivered():
    chain = [_report(1, "approved"),
             _report(2, "approved", supersedes="r1"),
             _report(3, "approved", supersedes="r2")]
    c = classify_task(_task(), chain, NOW)
    assert c["column"] == "corrected"           # pinned product policy
    assert c["chain"]["prior_retained"] == 2
    assert c["chain"]["current_status"] == "approved"


def test_rejected_corrected_latest_with_prior_approved_is_corrected():
    chain = [_report(1, "approved"),
             _report(2, "rejected", supersedes="r1")]
    c = classify_task(_task(), chain, NOW)
    assert c["column"] == "corrected"
    assert c["chain"]["current_status"] == "rejected"


def test_single_rejected_v1_is_queued_with_context():
    c = classify_task(_task(), [_report(1, "rejected")], NOW)
    assert c["column"] == "queued"
    assert "rejected" in c["freshness_reason"]


def test_stale_delivered_is_stale_not_delivered():
    c = classify_task(_task(), [_report(1, "approved", cite_days=10)], NOW)
    assert c["column"] == "stale"
    assert c["freshness"] == "stale"


def test_stale_beats_corrected_in_precedence():
    chain = [_report(1, "approved"),
             _report(2, "approved", supersedes="r1", cite_days=10)]
    c = classify_task(_task(), chain, NOW)
    assert c["column"] == "stale"


def test_scheduled_overdue_approved_is_stale():
    # citation-less report + owner schedule + 20d silence → advisory stale
    c = classify_task(
        _task(schedule_expr="0 6 * * MON"),
        [_report(1, "approved", cite_days=None, delivered_days=20)], NOW)
    assert c["column"] == "stale"
    assert "scheduled" in c["freshness_reason"]


def test_closed_task_without_reports_is_off_board():
    assert classify_task(_task(status="closed"), [], NOW) is None


def test_closed_task_with_approved_report_stays_on_board():
    c = classify_task(_task(status="closed"),
                      [_report(1, "approved")], NOW)
    assert c is not None and c["column"] == "delivered"


def test_one_card_per_task_latest_version_is_current():
    chain = [_report(1, "approved"), _report(2, "approved",
                                             supersedes="r1")]
    c = classify_task(_task(), chain, NOW)
    assert c["latest_report"]["version"] == 2   # never two cards


def test_tasks_without_linked_jobs_never_reach_running_or_failed():
    # mission-board-2: only a LINKED job can move a task into Running or
    # Failed; without jobs the mission-board-1 truth holds, and no
    # 'blocked' state exists anywhere.
    for chain in ([], [_report(1, "pending")], [_report(1, "approved")],
                  [_report(1, "rejected")]):
        c = classify_task(_task(), chain, NOW)
        if c is not None:
            assert c["column"] not in ("running", "failed", "blocked")


# ── mission-board-2: linked-job task classification ────────────────────────

def _ljob(uid="lj1", status="running", *, created_days=0.2,
          started_days=0.1, err=None) -> dict:
    return {"job_uid": uid, "job_type": "drift_report", "params": {},
            "status": status, "token_prefix": "arthos_a",
            "research_task_id": "t1",
            "created_at": _ts(created_days),
            "started_at": _ts(started_days) if started_days else None,
            "finished_at": None, "error_summary": err}


def test_active_linked_job_moves_task_to_running():
    c = classify_task(_task(), [], NOW, jobs=[_ljob(status="queued",
                                                    started_days=None)])
    assert c["column"] == "running"
    assert c["execution"]["active_status"] == "queued"
    assert c["execution"]["attempts"] == 1


def test_running_beats_pending_report_with_context_kept():
    c = classify_task(_task(), [_report(1, "pending")], NOW,
                      jobs=[_ljob()])
    assert c["column"] == "running"               # pinned precedence
    assert c["latest_report"]["review_status"] == "pending"  # context kept


def test_failed_linked_job_moves_task_to_failed():
    c = classify_task(_task(), [], NOW,
                      jobs=[_ljob(status="failed", err="ValueError: x")])
    assert c["column"] == "failed"
    assert "ValueError" in c["freshness_reason"]
    assert c["execution"]["last_error"].startswith("ValueError")


def test_linked_retry_suppresses_old_failure_by_task_linkage():
    old = _ljob("lj1", "failed", created_days=2, err="boom")
    retry = _ljob("lj2", "running", created_days=0.1)
    c = classify_task(_task(), [], NOW, jobs=[old, retry])
    assert c["column"] == "running"
    assert c["execution"]["retries"] == 1


def test_completed_retry_clears_failure_and_reports_rule_applies():
    old = _ljob("lj1", "failed", created_days=2, err="boom")
    done = _ljob("lj2", "succeeded", created_days=0.5)
    c = classify_task(_task(), [_report(1, "approved")], NOW,
                      jobs=[old, done])
    assert c["column"] == "delivered"             # succeeded retry supersedes


def test_report_delivered_after_failure_suppresses_failed():
    # approved report newer than the failed attempt: the work landed.
    failed = _ljob("lj1", "failed", created_days=3, err="boom")
    c = classify_task(_task(), [_report(1, "approved", delivered_days=1)],
                      NOW, jobs=[failed])
    assert c["column"] == "delivered"


def test_pending_report_after_failed_job_is_review_needed():
    failed = _ljob("lj1", "failed", created_days=3, err="boom")
    c = classify_task(_task(), [_report(1, "pending", delivered_days=1)],
                      NOW, jobs=[failed])
    assert c["column"] == "review_needed"


def test_failure_after_approved_report_is_failed():
    # latest attempt failed AFTER the report was delivered → Failed.
    failed = _ljob("lj1", "failed", created_days=0.5, err="boom")
    c = classify_task(_task(), [_report(1, "approved", delivered_days=2)],
                      NOW, jobs=[failed])
    assert c["column"] == "failed"


def test_stale_report_with_running_job_is_running():
    c = classify_task(_task(), [_report(1, "approved", cite_days=20)], NOW,
                      jobs=[_ljob()])
    assert c["column"] == "running"               # refresh in flight


def test_closed_task_with_active_linked_job_still_boards():
    c = classify_task(_task(status="closed"), [], NOW, jobs=[_ljob()])
    assert c is not None and c["column"] == "running"


def test_stuck_linked_running_job_stays_running_with_stale_advisory():
    c = classify_task(_task(), [], NOW,
                      jobs=[_ljob(started_days=0.5)])   # 12h > 60min
    assert c["column"] == "running"
    assert c["freshness"] == "stale"


def test_linked_job_task_stays_one_card_with_execution_summary():
    c = classify_task(_task(), [_report(1, "approved")], NOW,
                      jobs=[_ljob("a", "succeeded"), _ljob("b", "running")])
    assert c["card_id"] == "task:t1"
    assert c["execution"] == {
        "attempts": 2, "retries": 1, "active_status": "running",
        "last_attempt_at": c["execution"]["last_attempt_at"],
        "last_error": None, "history_available": True,
    }


# ── freshness policy ───────────────────────────────────────────────────────

def test_freshness_boundaries():
    assert report_freshness(_report(cite_days=2), NOW)[0] == "fresh"
    assert report_freshness(_report(cite_days=5), NOW)[0] == "aging"
    assert report_freshness(_report(cite_days=8), NOW)[0] == "stale"


def test_no_asof_facts_is_unknown_never_fresh():
    r = _report(cite_days=None)
    assert report_freshness(r, NOW)[0] == "unknown"


def test_expires_at_alone_governs_citationless_reports():
    fut = _report(cite_days=None, expires=_ts(-5))   # 5d in the future
    past = _report(cite_days=None, expires=_ts(1))
    assert report_freshness(fut, NOW)[0] == "fresh"
    assert report_freshness(past, NOW)[0] == "stale"


def test_malformed_citation_timestamps_degrade_to_unknown():
    r = _report()
    r["citations"] = [{"url": "https://x", "observed_at": "not-a-date"},
                      "garbage", {"url": "https://y"}]
    assert report_freshness(r, NOW)[0] == "unknown"


# ── payload redaction (shape-level) ────────────────────────────────────────

def test_card_never_carries_body_raw_citations_or_emails():
    r = _report(1, "approved", generated_by="owner@example.com",
                reviewed_by="owner@example.com", provenance="human")
    r["body"] = "SECRET BODY"
    c = classify_task(_task(), [r], NOW)
    flat = repr(c)
    assert "SECRET BODY" not in flat
    assert "owner@example.com" not in flat
    assert c["latest_report"]["generated_by_label"] == "owner"
    assert c["latest_report"]["citation_count"] == 1
    assert "citations" not in c["latest_report"]


def test_agent_generated_by_label_passes_through():
    r = _report(1, "pending", generated_by="agent:researcher")
    c = classify_task(_task(), [r], NOW)
    assert c["latest_report"]["generated_by_label"] == "agent:researcher"


# ── gateway job cards ──────────────────────────────────────────────────────

def _job(uid="j1", status="running", jt="drift_report", params=None,
         created_days=0.5, started_days=0.4, err=None) -> dict:
    return {"job_uid": uid, "job_type": jt, "params": params or {},
            "status": status, "token_prefix": "arthos_a",
            "created_at": _ts(created_days),
            "started_at": _ts(started_days) if started_days else None,
            "finished_at": None, "error_summary": err}


def test_queued_and_running_jobs_land_in_running():
    cards = classify_jobs([_job("j1", "queued", started_days=None),
                           _job("j2", "running")], NOW)
    assert {c["column"] for c in cards} == {"running"}
    assert {c["job_status"] for c in cards} == {"queued", "running"}
    assert all(c["task_link"] is None for c in cards)


def test_failed_job_is_failed_with_bounded_reason():
    cards = classify_jobs([_job("j1", "failed", err="ValueError: " + "x" * 900)],
                          NOW)
    assert cards[0]["column"] == "failed"
    assert len(cards[0]["freshness_reason"]) <= 160


def test_failed_with_newer_identical_retry_is_suppressed():
    old = _job("j1", "failed", params={"reference_days": 90},
               created_days=2)
    retry = _job("j2", "running", params={"reference_days": 90},
                 created_days=0.1)
    cards = classify_jobs([old, retry], NOW)
    assert [c["card_id"] for c in cards] == ["job:j2"]   # Running only


def test_failed_with_different_params_retry_is_not_suppressed():
    old = _job("j1", "failed", params={"reference_days": 90}, created_days=2)
    other = _job("j2", "running", params={"reference_days": 30},
                 created_days=0.1)
    cards = classify_jobs([old, other], NOW)
    assert {c["card_id"] for c in cards} == {"job:j1", "job:j2"}


def test_cancelled_and_succeeded_jobs_are_not_carded():
    assert classify_jobs([_job("j1", "cancelled"),
                          _job("j2", "succeeded")], NOW) == []


def test_stuck_running_job_stays_running_with_stale_advisory():
    cards = classify_jobs([_job("j1", "running", started_days=0.5)], NOW)
    assert cards[0]["column"] == "running"      # not failed — no failure fact
    assert cards[0]["freshness"] == "stale"


def test_job_card_has_no_secret_fields():
    c = classify_jobs([_job()], NOW)[0]
    assert "created_by" not in c
    assert "request_hash" not in c
    assert c["token_prefix"] == "arthos_a"      # public prefix only


# ── follow-up chains ───────────────────────────────────────────────────────

def _parents(*pairs) -> dict:
    return {i: {"id": i, "title": f"T-{i}", "follow_up_of_task_id": p}
            for i, p in pairs}


def test_follow_up_parent_and_depth():
    parents = _parents(("a", None), ("b", "a"), ("c", "b"))
    s = follow_up_summary("c", parents)
    assert s["available"] and s["parent_task_id"] == "b"
    assert s["parent_title"] == "T-b"
    assert s["depth"] == 2


def test_follow_up_cycle_is_safe_label():
    parents = _parents(("a", "b"), ("b", "a"))
    s = follow_up_summary("a", parents)
    assert s == {"available": False,
                 "note": "relationship unavailable (cycle detected)"}


def test_follow_up_depth_is_capped():
    chain = [("t0", None)] + [(f"t{i}", f"t{i-1}") for i in range(1, 12)]
    s = follow_up_summary("t11", _parents(*chain))
    assert s["depth"] == FOLLOW_UP_MAX_DEPTH
    assert s["depth_capped"] is True


def test_non_follow_up_has_no_summary():
    assert follow_up_summary("a", _parents(("a", None))) is None


# ── ordering + policy version ──────────────────────────────────────────────

def test_review_needed_sorts_oldest_first_others_newest_first():
    a = {"card_id": "task:a", "sort_ts": _ts(3).isoformat()}
    b = {"card_id": "task:b", "sort_ts": _ts(1).isoformat()}
    assert _sort_cards("review_needed", [b, a])[0]["card_id"] == "task:a"
    assert _sort_cards("delivered", [a, b])[0]["card_id"] == "task:b"


def test_ordering_is_deterministic_on_ties():
    a = {"card_id": "task:a", "sort_ts": _ts(1).isoformat()}
    b = {"card_id": "task:b", "sort_ts": _ts(1).isoformat()}
    assert _sort_cards("delivered", [b, a]) == _sort_cards("delivered", [a, b])


def test_rule_set_version_pinned():
    assert MISSION_BOARD_RULE_SET_VERSION == "mission-board-2"
