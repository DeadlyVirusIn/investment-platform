"""P0-2A.4 — scheduler must honor job-reported failure status.

Regression: 2026-06-12 options_candidate_generation swallowed a
NoSuchColumnError and returned {"status": "error"}; tick_loop discarded
the return value and recorded job_run.status='success', masking a
production outage.

These tests pin the pure classification helper. The wiring (status flip
in _execute_job's else-branch, same recording path as a raise) is a
4-line diff reviewed alongside; full-loop behavior rides the container
environment like the rest of the worker suite.
"""

from __future__ import annotations

from apps.worker.src.scheduler.tick_loop import _result_reports_failure


def test_error_status_is_failure():
    assert _result_reports_failure({"status": "error"}) is True
    assert _result_reports_failure({"status": "ERROR"}) is True
    assert _result_reports_failure({"status": "failed"}) is True


def test_success_like_statuses_are_not_failure():
    for s in ("ok", "no_data", "skipped", "success", ""):
        assert _result_reports_failure({"status": s}) is False


def test_non_dict_results_are_not_failure():
    for r in (None, "error", 1, ["error"], object()):
        assert _result_reports_failure(r) is False


def test_dict_without_status_is_not_failure():
    assert _result_reports_failure({"inserted": 0}) is False
