"""Phase 11Z incident-response — replay_paper_history safety tests.

After the 2026-05-02 `compose_pgdata` wipe, `scripts.replay_paper_history`
was created to rebuild paper-trading rows from already-recovered
upstream data. This test module pins the safety contract:

  1. The script MUST refuse `--commit` unless the literal env
     PAPER_REPLAY_CONFIRM=I_UNDERSTAND_THIS_REGENERATES_PAPER_HISTORY
     is set.
  2. The script MUST default to dry-run (no DB writes) when neither
     `--dry-run` nor `--commit` is passed.
  3. The script MUST refuse to overwrite a date that already has
     rows unless `--replace-date` is also passed.
  4. When `--replace-date` IS passed, every DELETE statement in the
     module MUST be scoped to a single date column (so it is
     impossible to drop rows from a different date).
  5. The script MUST never write to research_*, options_paper_*,
     or auth/subscription tables.
  6. The script MUST NOT be in the worker job registry, the
     scheduler, or any cron entry.

These are pinned to source code (grep) and to the parser/orchestrator
behaviour (mocked subprocess). They never invoke the real DB.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

import scripts.replay_paper_history as mod


# ---------------------------------------------------------------------------
# Argument parsing & defaults
# ---------------------------------------------------------------------------
def test_defaults_to_dry_run_when_neither_flag_set():
    args = mod._parse([
        "--start-date", "2026-04-24", "--end-date", "2026-04-24",
    ])
    assert args.dry_run is True
    assert args.commit is False
    assert args.replace_date is False


def test_explicit_dry_run_flag():
    args = mod._parse([
        "--start-date", "2026-04-24", "--end-date", "2026-04-24",
        "--dry-run",
    ])
    assert args.dry_run is True
    assert args.commit is False


def test_commit_and_dry_run_mutually_exclusive():
    with pytest.raises(SystemExit):
        mod._parse([
            "--start-date", "2026-04-24", "--end-date", "2026-04-24",
            "--commit", "--dry-run",
        ])


def test_inverted_range_rejected():
    with pytest.raises(SystemExit):
        mod._parse([
            "--start-date", "2026-04-25", "--end-date", "2026-04-24",
        ])


def test_trading_days_skips_weekends():
    days = mod._trading_days(dt.date(2026, 4, 24), dt.date(2026, 5, 1))
    # Fri 4-24, Mon 4-27, Tue 4-28, Wed 4-29, Thu 4-30, Fri 5-1
    assert days == [
        dt.date(2026, 4, 24),
        dt.date(2026, 4, 27),
        dt.date(2026, 4, 28),
        dt.date(2026, 4, 29),
        dt.date(2026, 4, 30),
        dt.date(2026, 5, 1),
    ]


# ---------------------------------------------------------------------------
# Test 1 — dry-run writes zero rows
# ---------------------------------------------------------------------------
def test_dry_run_invokes_paper_daily_with_dry_run_flag(monkeypatch):
    """Dry-run path must propagate --dry-run into the subprocess so
    run_paper_daily writes nothing."""
    captured: list[list[str]] = []

    def _fake_run(cmd, capture_output=False):
        captured.append(list(cmd))
        class P:
            returncode = 0
        return P()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    # Avoid any real DB session — replace SessionLocal with a stub that
    # behaves like a context manager and yields a session whose execute
    # returns 0 counts.
    class _StubResult:
        def __init__(self, val=0): self._val = val
        def scalar(self): return self._val
    class _StubSession:
        def execute(self, *a, **kw): return _StubResult(0)
        def commit(self): pass
        def rollback(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(mod, "SessionLocal", lambda: _StubSession())

    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24),
        end_date=dt.date(2026, 4, 24),
        dry_run=True, commit=False, replace_date=False,
    )
    out = mod.replay_range(args)
    assert out["ok"] is True
    assert len(captured) == 1
    cmd = captured[0]
    assert "--dry-run" in cmd
    assert "--date" in cmd
    assert "2026-04-24" in cmd
    # Critical: dry-run path NEVER calls the delete helper.
    assert all(d["deleted"] == {} for d in out["days"])


# ---------------------------------------------------------------------------
# Test 2 — --commit refused without confirmation env
# ---------------------------------------------------------------------------
def test_commit_refused_without_confirmation_env(monkeypatch):
    monkeypatch.delenv(mod.CONFIRM_ENV, raising=False)
    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24),
        end_date=dt.date(2026, 4, 24),
        dry_run=False, commit=True, replace_date=False,
    )
    with pytest.raises(SystemExit) as exc:
        mod.replay_range(args)
    assert exc.value.code == 2


def test_commit_refused_with_wrong_confirmation_value(monkeypatch):
    monkeypatch.setenv(mod.CONFIRM_ENV, "yes")
    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24),
        end_date=dt.date(2026, 4, 24),
        dry_run=False, commit=True, replace_date=False,
    )
    with pytest.raises(SystemExit) as exc:
        mod.replay_range(args)
    assert exc.value.code == 2


def test_commit_accepted_with_correct_confirmation_value(monkeypatch):
    monkeypatch.setenv(mod.CONFIRM_ENV, mod.CONFIRM_VALUE)
    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24),
        end_date=dt.date(2026, 4, 24),
        dry_run=False, commit=True, replace_date=False,
    )
    # Should NOT raise.
    mod._enforce_commit_confirmation(args)


def test_dry_run_bypasses_confirmation(monkeypatch):
    """Dry-run must NOT require the confirmation env."""
    monkeypatch.delenv(mod.CONFIRM_ENV, raising=False)
    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24),
        end_date=dt.date(2026, 4, 24),
        dry_run=True, commit=False, replace_date=False,
    )
    # Should NOT raise.
    mod._enforce_commit_confirmation(args)


# ---------------------------------------------------------------------------
# Test 3 — date rerun is idempotent or safely refused
# ---------------------------------------------------------------------------
def test_existing_date_refused_without_replace(monkeypatch):
    """If a date already has rows and --replace-date is NOT passed,
    that date returns status='refused_existing' and does not invoke
    paper_daily."""
    paper_daily_calls: list[dt.date] = []

    def _fake_run(cmd, capture_output=False):
        # Find date arg.
        idx = cmd.index("--date")
        paper_daily_calls.append(dt.date.fromisoformat(cmd[idx + 1]))
        class P:
            returncode = 0
        return P()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)

    # Simulate a session that reports rows already present.
    nonzero = {tbl: 5 for tbl, _ in mod.COUNT_TABLES}
    class _StubSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def commit(self): pass
        def rollback(self): pass
        # We monkeypatch _count_rows_for_date below instead.

    monkeypatch.setattr(mod, "SessionLocal", lambda: _StubSession())
    monkeypatch.setattr(
        mod, "_count_rows_for_date", lambda s, d: dict(nonzero),
    )
    monkeypatch.setenv(mod.CONFIRM_ENV, mod.CONFIRM_VALUE)

    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24),
        end_date=dt.date(2026, 4, 24),
        dry_run=False, commit=True, replace_date=False,
    )
    out = mod.replay_range(args)
    assert out["days"][0]["status"] == "refused_existing"
    # paper_daily must NOT have been invoked.
    assert paper_daily_calls == []


def test_replace_date_invokes_delete_only_for_target_date(monkeypatch):
    """When --replace-date is passed and rows exist, delete is invoked
    and ONLY for the requested date — every DELETE statement is bound
    to {'d': target_date}."""
    delete_calls: list[tuple[str, dict]] = []
    paper_daily_calls: list[dt.date] = []

    def _fake_run(cmd, capture_output=False):
        idx = cmd.index("--date")
        paper_daily_calls.append(dt.date.fromisoformat(cmd[idx + 1]))
        class P:
            returncode = 0
        return P()

    class _StubResult:
        rowcount = 1
        def scalar(self): return 0
    class _StubSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def commit(self): pass
        def rollback(self): pass
        def execute(self, stmt, params=None):
            try:
                stmt_text = str(getattr(stmt, "text", stmt))
            except Exception:
                stmt_text = ""
            if "DELETE" in stmt_text.upper():
                delete_calls.append((stmt_text, params or {}))
            return _StubResult()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    monkeypatch.setattr(mod, "SessionLocal", lambda: _StubSession())
    nonzero = {tbl: 5 for tbl, _ in mod.COUNT_TABLES}
    monkeypatch.setattr(
        mod, "_count_rows_for_date", lambda s, d: dict(nonzero),
    )
    monkeypatch.setenv(mod.CONFIRM_ENV, mod.CONFIRM_VALUE)

    target = dt.date(2026, 4, 24)
    args = mod.ReplayArgs(
        start_date=target, end_date=target,
        dry_run=False, commit=True, replace_date=True,
    )
    out = mod.replay_range(args)

    # paper_daily was invoked exactly once for the target date.
    assert paper_daily_calls == [target]

    # Every DELETE statement was bound to {'d': target} — no other
    # date could possibly be affected.
    assert len(delete_calls) > 0
    for _stmt, params in delete_calls:
        assert params.get("d") == target, (
            f"DELETE bound to wrong date: {params}"
        )

    # Every DELETE in the static statement table targets one of the
    # ALLOWED_WRITE_TABLES — pinned for safety.
    for stmt, table in mod.DELETE_STATEMENTS_FOR_DATE:
        assert table in mod.ALLOWED_WRITE_TABLES
        assert ":d" in stmt, (
            f"DELETE for {table} not bound to date param: {stmt}"
        )

    assert out["days"][0]["status"] == "ok"


def test_dry_run_with_existing_rows_does_not_delete(monkeypatch):
    """Even with --replace-date, a dry-run must NOT execute delete
    statements."""
    delete_calls: list[str] = []

    def _fake_run(cmd, capture_output=False):
        class P: returncode = 0
        return P()

    class _StubSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def commit(self): pass
        def rollback(self): pass
        def execute(self, stmt, params=None):
            stmt_text = str(getattr(stmt, "text", stmt))
            if "DELETE" in stmt_text.upper():
                delete_calls.append(stmt_text)
            class R:
                rowcount = 0
                def scalar(self): return 0
            return R()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    monkeypatch.setattr(mod, "SessionLocal", lambda: _StubSession())
    nonzero = {tbl: 5 for tbl, _ in mod.COUNT_TABLES}
    monkeypatch.setattr(
        mod, "_count_rows_for_date", lambda s, d: dict(nonzero),
    )

    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24),
        end_date=dt.date(2026, 4, 24),
        dry_run=True, commit=False, replace_date=True,
    )
    out = mod.replay_range(args)
    # No DELETE should have hit the session in dry-run.
    assert delete_calls == []
    assert out["days"][0]["status"] in ("skipped_dry", "ok")


# ---------------------------------------------------------------------------
# Test 4 — replay does not touch research / options / live tables
# ---------------------------------------------------------------------------
def test_no_forbidden_table_writes_in_source():
    """Pin the rule that this script never writes to research_*,
    options_paper_*, or auth/subscription tables. We grep the source
    for INSERT INTO / UPDATE / DELETE FROM statements that name any
    of those tables."""
    src = Path("scripts/replay_paper_history.py").read_text(encoding="utf-8")
    write_patterns = (
        re.compile(r"INSERT\s+INTO\s+(\w+)", re.IGNORECASE),
        re.compile(r"UPDATE\s+(\w+)", re.IGNORECASE),
        re.compile(r"DELETE\s+FROM\s+(\w+)", re.IGNORECASE),
    )
    bad: list[str] = []
    for line in src.splitlines():
        # Skip the FORBIDDEN_WRITE_TABLES literal definition itself —
        # those lines are documentation, not SQL.
        stripped = line.strip()
        if (
            stripped.startswith('"')
            or stripped.startswith("#")
            or stripped.startswith("'")
        ):
            continue
        for pat in write_patterns:
            for m in pat.finditer(line):
                tbl = m.group(1).lower()
                if tbl in mod.FORBIDDEN_WRITE_TABLES:
                    bad.append(f"{tbl} in: {line.strip()}")
    assert not bad, f"replay script writes to forbidden tables: {bad}"


def test_allowed_and_forbidden_tables_disjoint():
    overlap = mod.ALLOWED_WRITE_TABLES & mod.FORBIDDEN_WRITE_TABLES
    assert not overlap, (
        f"ALLOWED_WRITE_TABLES and FORBIDDEN_WRITE_TABLES overlap: {overlap}"
    )


def test_delete_statements_only_target_allowed_tables():
    for stmt, table in mod.DELETE_STATEMENTS_FOR_DATE:
        assert table in mod.ALLOWED_WRITE_TABLES, (
            f"DELETE table {table!r} is not in ALLOWED_WRITE_TABLES"
        )
        # Statement must reference the table name and a date param.
        assert table in stmt, f"DELETE statement does not name {table}: {stmt}"
        assert ":d" in stmt, (
            f"DELETE for {table} not date-scoped: {stmt}"
        )


# ---------------------------------------------------------------------------
# Test 5 — replay script must NEVER appear in worker registry
# ---------------------------------------------------------------------------
def test_replay_not_in_worker_registry():
    from apps.worker.src.jobs.registry import REGISTRY

    for name, fn in REGISTRY.items():
        assert "replay_paper_history" not in name, (
            f"replay_paper_history must not be a registered job: {name}"
        )
        assert "replay" not in name.lower() or "replay_paper" not in name, (
            f"replay_paper_history-style job name found: {name}"
        )
        # Also check the function's module — defensive.
        mod_name = getattr(fn, "__module__", "") or ""
        assert "replay_paper_history" not in mod_name, (
            f"job {name!r} resolves to replay module: {mod_name}"
        )


def test_replay_not_referenced_in_scheduler_or_cron():
    """Grep the worker scheduler + cron files for any reference to
    replay_paper_history. Must find none."""
    candidates = [
        Path("apps/worker/src/scheduler/tick_loop.py"),
        Path("apps/worker/src/jobs/registry.py"),
        Path("apps/worker/src/main.py"),
        Path("infra/compose/docker-compose.yml"),
    ]
    cron_glob = list(Path("apps/worker").rglob("*cron*"))
    scripts_run_daily = Path("scripts/run_daily_loop.sh")
    bad: list[str] = []
    for f in candidates + cron_glob + [scripts_run_daily]:
        if not f.exists():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "replay_paper_history" in text:
            bad.append(str(f))
    assert not bad, (
        f"replay_paper_history must not be referenced in scheduler/"
        f"cron files. Found in: {bad}"
    )


# ---------------------------------------------------------------------------
# Test 6 — script source contains no strategy / threshold / live tokens
# ---------------------------------------------------------------------------
def test_no_strategy_or_threshold_changes_in_replay_source():
    """Replay is pure orchestration — it must never reference
    threshold constants or live-trading helpers."""
    src = Path("scripts/replay_paper_history.py").read_text(encoding="utf-8")
    forbidden = (
        "RATE_THRESHOLD",
        "VRP_THRESHOLD",
        "DEFAULT_MAX_OPEN_POSITIONS",
        "submit_trade",
        "auto_trade_portfolio",
        "execute_order",
        "live_broker",
    )
    for tok in forbidden:
        assert tok not in src, (
            f"replay script must not reference {tok!r}"
        )


def test_script_has_module_docstring_calling_out_no_scheduler():
    """The module docstring must explicitly state this script is
    operator-only and never scheduled."""
    src = Path("scripts/replay_paper_history.py").read_text(encoding="utf-8")
    # First docstring chunk.
    head = src.split('"""')[1] if '"""' in src else ""
    assert "OPERATOR-ONLY" in head or "operator-only" in head.lower()
    assert "scheduled" in head.lower() or "scheduler" in head.lower()
