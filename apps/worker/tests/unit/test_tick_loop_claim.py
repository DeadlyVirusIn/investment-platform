"""P0-5A — atomic scheduler job-claim tests.

Both worker containers run the same tick-loop. _claim_due_job must let
exactly one scheduler win each due job via a guarded UPDATE ... RETURNING.

These tests monkeypatch SessionLocal + croniter so they need no DB and no
real cron parser (the module still imports croniter/loguru/sqlalchemy —
runs in container/CI like test_tick_loop_status.py). They pin the claim
CONTRACT; full two-process race behavior rides the integration env.
"""

from __future__ import annotations

import datetime
import inspect

import apps.worker.src.scheduler.tick_loop as tl


NOW = datetime.datetime(2026, 6, 13, 14, 45, tzinfo=datetime.timezone.utc)
NEXT = datetime.datetime(2026, 6, 14, 14, 45, tzinfo=datetime.timezone.utc)


class _Sched:
    def __init__(self, name="job", cron="45 14 * * *", id="sched-1"):
        self.name = name
        self.cron_expr = cron
        self.id = id


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    """Records the UPDATE + params; returns the configured RETURNING row."""

    last = None  # class-level capture of the most recent instance

    def __init__(self, row):
        self._row = row
        self.executed: list = []
        self.committed = False
        _FakeSession.last = self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt, params):
        self.executed.append((str(stmt), params))
        return _Result(self._row)

    def commit(self):
        self.committed = True


def _patch(monkeypatch, *, returning_row, cron_ok=True):
    monkeypatch.setattr(tl, "SessionLocal", lambda: _FakeSession(returning_row))
    if cron_ok:
        class _Cron:
            def __init__(self, *a):
                pass

            def get_next(self, _t):
                return NEXT
        monkeypatch.setattr(tl, "croniter", lambda expr, base: _Cron())
    else:
        def _boom(expr, base):
            raise ValueError("bad cron")
        monkeypatch.setattr(tl, "croniter", _boom)


def test_winner_claims_and_executes(monkeypatch):
    _patch(monkeypatch, returning_row=("sched-1",))
    assert tl._claim_due_job(_Sched(), NOW) is True
    assert _FakeSession.last.committed


def test_loser_gets_no_row_and_skips(monkeypatch):
    _patch(monkeypatch, returning_row=None)
    assert tl._claim_due_job(_Sched(), NOW) is False


def test_claim_advances_next_run_at_to_cron_next(monkeypatch):
    _patch(monkeypatch, returning_row=("sched-1",))
    tl._claim_due_job(_Sched(), NOW)
    _sql, params = _FakeSession.last.executed[0]
    assert params["next"] == NEXT          # advanced at claim time
    assert params["now"] == NOW
    assert params["id"] == "sched-1"


def test_claim_sql_guards_enabled_and_due_window(monkeypatch):
    _patch(monkeypatch, returning_row=("sched-1",))
    tl._claim_due_job(_Sched(), NOW)
    sql, _ = _FakeSession.last.executed[0]
    assert "UPDATE job_schedule" in sql
    assert "enabled = true" in sql
    assert "next_run_at <= :now" in sql
    assert "RETURNING id" in sql


def test_malformed_cron_does_not_claim(monkeypatch):
    _patch(monkeypatch, returning_row=("sched-1",), cron_ok=False)
    _FakeSession.last = None
    assert tl._claim_due_job(_Sched(), NOW) is False
    # no UPDATE attempted when cron can't be computed
    assert _FakeSession.last is None


def test_execute_job_no_longer_advances_next_run_at():
    """The post-execution next_run_at recompute is removed; advancement
    happens only at claim time (the non-atomic step that double-ran jobs)."""
    src = inspect.getsource(tl._execute_job)
    # no cron recompute and no assignment to next_run_at remain (a passing
    # mention in the explanatory comment is fine — assert on real tokens)
    assert "get_next" not in src
    assert "next_run_at =" not in src
    # last_run_at recording is preserved
    assert "last_run_at" in src


def test_failure_status_recording_preserved():
    """P0-2A.4 contract intact: raises and returned error dicts both record
    status=error in _execute_job."""
    src = inspect.getsource(tl._execute_job)
    assert '"error"' in src or "'error'" in src
    assert "_result_reports_failure" in src
    assert 'status = "error"' in src
