"""Phase 11Z incident-response — execution-chain replay safety tests.

Pins the contract for `scripts.replay_paper_execution_chain`:

  1. Default mode = dry-run (no DB writes, no engine invocation).
  2. --commit refused unless
     PAPER_EXEC_REPLAY_CONFIRM=I_UNDERSTAND_THIS_REGENERATES_EXECUTION_HISTORY
     is set.
  3. Account / paper_portfolio creation happens only in --commit.
  4. Existing-rows date refused without --replace-date.
  5. --replace-date deletes ONLY the target date's rows; every DELETE
     statement is bound to {'d': target}.
  6. Source must NOT INSERT/UPDATE/DELETE any forbidden table
     (research_*, options_paper_*, decision_log, paper_trade_log,
     paper_run_log, paper_shadow_log, auth/subscription, read-only
     inputs).
  7. Source must NOT contain `INSERT INTO paper_trade` — the only
     allowed write path is via existing `submit_trade`.
  8. Script must NOT be in worker registry / scheduler / cron.
  9. Allowed and forbidden write-table sets are disjoint.

Tests grep source + exercise the orchestrator with stubbed
SessionLocal / subprocess so no real DB is touched.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

import pytest

import scripts.replay_paper_execution_chain as mod


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def test_defaults_to_dry_run_when_neither_flag_set():
    args = mod._parse([
        "--start-date", "2026-04-24", "--end-date", "2026-04-24",
        "--account-name", "Test Replay", "--initial-cash", "100000",
    ])
    assert args.dry_run is True
    assert args.commit is False
    assert args.account_name == "Test Replay"
    assert args.initial_cash == Decimal("100000")


def test_inverted_range_rejected():
    with pytest.raises(SystemExit):
        mod._parse([
            "--start-date", "2026-04-25", "--end-date", "2026-04-24",
            "--account-name", "X", "--initial-cash", "1000",
        ])


def test_commit_and_dry_run_mutually_exclusive():
    with pytest.raises(SystemExit):
        mod._parse([
            "--start-date", "2026-04-24", "--end-date", "2026-04-24",
            "--account-name", "X", "--initial-cash", "1000",
            "--commit", "--dry-run",
        ])


def test_zero_cash_rejected():
    with pytest.raises(SystemExit):
        mod._parse([
            "--start-date", "2026-04-24", "--end-date", "2026-04-24",
            "--account-name", "X", "--initial-cash", "0",
        ])


def test_negative_cash_rejected():
    with pytest.raises(SystemExit):
        mod._parse([
            "--start-date", "2026-04-24", "--end-date", "2026-04-24",
            "--account-name", "X", "--initial-cash", "-5",
        ])


def test_trading_days_skips_weekends():
    days = mod._trading_days(dt.date(2026, 4, 24), dt.date(2026, 5, 1))
    assert days == [
        dt.date(2026, 4, 24), dt.date(2026, 4, 27),
        dt.date(2026, 4, 28), dt.date(2026, 4, 29),
        dt.date(2026, 4, 30), dt.date(2026, 5, 1),
    ]


# ---------------------------------------------------------------------------
# Confirmation env
# ---------------------------------------------------------------------------
def test_commit_refused_without_confirmation_env(monkeypatch):
    monkeypatch.delenv(mod.CONFIRM_ENV, raising=False)
    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24), end_date=dt.date(2026, 4, 24),
        account_name="X", initial_cash=Decimal("100"),
        dry_run=False, commit=True, replace_date=False,
    )
    with pytest.raises(SystemExit) as exc:
        mod.replay_chain(args)
    assert exc.value.code == 2


def test_commit_refused_with_wrong_confirmation(monkeypatch):
    monkeypatch.setenv(mod.CONFIRM_ENV, "yes")
    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24), end_date=dt.date(2026, 4, 24),
        account_name="X", initial_cash=Decimal("100"),
        dry_run=False, commit=True, replace_date=False,
    )
    with pytest.raises(SystemExit) as exc:
        mod.replay_chain(args)
    assert exc.value.code == 2


def test_dry_run_does_not_require_confirmation(monkeypatch):
    monkeypatch.delenv(mod.CONFIRM_ENV, raising=False)
    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24), end_date=dt.date(2026, 4, 24),
        account_name="X", initial_cash=Decimal("100"),
        dry_run=True, commit=False, replace_date=False,
    )
    mod._enforce_commit_confirmation(args)  # must not raise


# ---------------------------------------------------------------------------
# Account-create only in commit mode
# ---------------------------------------------------------------------------
def test_account_creation_skipped_in_dry_run(monkeypatch):
    """_ensure_account_and_portfolio in dry-run path must NOT add to
    session and must NOT commit, even when neither row exists."""
    added: list[object] = []

    class _Q:
        def first(self): return None
    class _Sess:
        def scalars(self, *a, **k): return _Q()
        def add(self, x): added.append(x)
        def flush(self): pytest.fail("flush called in dry-run")
        def commit(self): pytest.fail("commit called in dry-run")
        def rollback(self): pass

    acct, port = mod._ensure_account_and_portfolio(
        _Sess(), name="X", initial_cash=Decimal("1000"), commit=False,
    )
    assert acct is None
    assert port is None
    assert added == []


def test_account_creation_only_when_both_missing_in_commit(monkeypatch):
    """Commit mode creates Account + PaperPortfolio (one of each)
    when missing; idempotent if both already exist."""
    from apps.api.src.db.models import Account, PaperPortfolio

    flushed: list[str] = []
    committed: list[bool] = []
    added: list[object] = []

    class _Q:
        def first(self): return None
    class _Sess:
        def scalars(self, *a, **k): return _Q()
        def add(self, x):
            added.append(x)
            # Simulate ID assignment on flush
            x.id = f"stub-{type(x).__name__.lower()}"
        def flush(self):
            flushed.append("flush")
        def commit(self):
            committed.append(True)
        def rollback(self): pass

    acct, port = mod._ensure_account_and_portfolio(
        _Sess(), name="X", initial_cash=Decimal("1000"), commit=True,
    )
    # Both created; both flushed; one final commit.
    assert any(isinstance(o, Account) for o in added)
    assert any(isinstance(o, PaperPortfolio) for o in added)
    assert flushed.count("flush") == 2
    assert committed == [True]
    assert acct == "stub-account"
    assert port == "stub-paperportfolio"


# ---------------------------------------------------------------------------
# Existing-rows refusal
# ---------------------------------------------------------------------------
def test_existing_date_refused_without_replace(monkeypatch):
    invoked: list[dt.date] = []

    async def _fake_run(as_of):
        invoked.append(as_of)

    monkeypatch.setattr(mod, "_run_paper_trading_for_date", _fake_run)
    monkeypatch.setattr(
        mod, "_count_per_date",
        lambda s, d: {tbl: 5 for tbl, _w in mod.COUNT_TABLES_PER_DATE},
    )
    monkeypatch.setattr(mod, "SessionLocal",
                         lambda: _StubCtxSession())
    monkeypatch.setenv(mod.CONFIRM_ENV, mod.CONFIRM_VALUE)

    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24), end_date=dt.date(2026, 4, 24),
        account_name="X", initial_cash=Decimal("100"),
        dry_run=False, commit=True, replace_date=False,
    )
    # Skip the recs + bootstrap branches by stubbing.
    monkeypatch.setattr(mod, "_ensure_account_and_portfolio",
                         lambda *a, **k: ("acct", "port"))
    monkeypatch.setattr(mod, "_run_recommendations_once",
                         _noop_async)
    monkeypatch.setattr(mod, "_count_global", lambda s: {})
    monkeypatch.setattr(mod, "_candidate_idea_coverage",
                         lambda s, d: {})

    out = mod.replay_chain(args)
    assert out["days"][0]["status"] == "refused_existing"
    assert invoked == []


def test_replace_date_deletes_only_target_date(monkeypatch):
    """Every DELETE statement issued in --replace-date mode is bound
    to {'d': target} — it cannot affect any other date."""
    delete_calls: list[tuple[str, dict]] = []
    invoked: list[dt.date] = []

    async def _fake_run(as_of):
        invoked.append(as_of)

    class _StubResult:
        rowcount = 1
        def scalar(self): return 0
    class _StubSess:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def commit(self): pass
        def rollback(self): pass
        def execute(self, stmt, params=None):
            txt = str(getattr(stmt, "text", stmt)).upper()
            if "DELETE" in txt:
                delete_calls.append((str(getattr(stmt, "text", stmt)),
                                       params or {}))
            return _StubResult()

    monkeypatch.setattr(mod, "_run_paper_trading_for_date", _fake_run)
    monkeypatch.setattr(mod, "SessionLocal", lambda: _StubSess())
    monkeypatch.setattr(
        mod, "_count_per_date",
        lambda s, d: {tbl: 5 for tbl, _w in mod.COUNT_TABLES_PER_DATE},
    )
    monkeypatch.setattr(mod, "_count_global", lambda s: {})
    monkeypatch.setattr(mod, "_candidate_idea_coverage",
                         lambda s, d: {})
    monkeypatch.setattr(mod, "_ensure_account_and_portfolio",
                         lambda *a, **k: ("acct", "port"))
    monkeypatch.setattr(mod, "_run_recommendations_once", _noop_async)
    monkeypatch.setenv(mod.CONFIRM_ENV, mod.CONFIRM_VALUE)

    target = dt.date(2026, 4, 24)
    args = mod.ReplayArgs(
        start_date=target, end_date=target,
        account_name="X", initial_cash=Decimal("100"),
        dry_run=False, commit=True, replace_date=True,
    )
    out = mod.replay_chain(args)

    # paper_trading invoked once for the target date.
    assert invoked == [target]
    # All DELETE statements bound to target — no leakage to other dates.
    assert len(delete_calls) > 0
    for stmt_text, params in delete_calls:
        assert params.get("d") == target, (
            f"DELETE bound to wrong date: {params}")


def test_dry_run_with_existing_rows_does_not_delete(monkeypatch):
    delete_calls: list[str] = []
    invoked: list[dt.date] = []

    async def _fake_run(as_of):
        invoked.append(as_of)

    class _StubResult:
        rowcount = 0
        def scalar(self): return 0
    class _StubSess:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def commit(self): pass
        def rollback(self): pass
        def execute(self, stmt, params=None):
            txt = str(getattr(stmt, "text", stmt)).upper()
            if "DELETE" in txt:
                delete_calls.append(txt)
            return _StubResult()

    monkeypatch.setattr(mod, "_run_paper_trading_for_date", _fake_run)
    monkeypatch.setattr(mod, "SessionLocal", lambda: _StubSess())
    monkeypatch.setattr(
        mod, "_count_per_date",
        lambda s, d: {tbl: 5 for tbl, _w in mod.COUNT_TABLES_PER_DATE},
    )
    monkeypatch.setattr(mod, "_count_global", lambda s: {})
    monkeypatch.setattr(mod, "_candidate_idea_coverage",
                         lambda s, d: {})
    monkeypatch.setattr(mod, "_ensure_account_and_portfolio",
                         lambda *a, **k: ("acct", "port"))
    monkeypatch.setattr(mod, "_run_recommendations_once", _noop_async)

    args = mod.ReplayArgs(
        start_date=dt.date(2026, 4, 24), end_date=dt.date(2026, 4, 24),
        account_name="X", initial_cash=Decimal("100"),
        dry_run=True, commit=False, replace_date=True,
    )
    out = mod.replay_chain(args)
    assert delete_calls == []
    assert invoked == []
    assert out["days"][0]["status"] == "skipped_dry"


# ---------------------------------------------------------------------------
# Source-grep guards
# ---------------------------------------------------------------------------
def test_no_forbidden_table_writes_in_source():
    src = Path(
        "scripts/replay_paper_execution_chain.py"
    ).read_text(encoding="utf-8")
    write_patterns = (
        re.compile(r"INSERT\s+INTO\s+(\w+)", re.IGNORECASE),
        re.compile(r"UPDATE\s+(\w+)", re.IGNORECASE),
        re.compile(r"DELETE\s+FROM\s+(\w+)", re.IGNORECASE),
    )
    bad: list[str] = []
    for line in src.splitlines():
        stripped = line.strip()
        if (stripped.startswith('"') or stripped.startswith("#")
                or stripped.startswith("'") or stripped.startswith("*")):
            continue
        for pat in write_patterns:
            for m in pat.finditer(line):
                tbl = m.group(1).lower()
                if tbl in mod.FORBIDDEN_WRITE_TABLES:
                    bad.append(f"{tbl} in: {line.strip()}")
    assert not bad, f"forbidden table writes: {bad}"


def test_no_direct_paper_trade_insert_in_source():
    """Only allowed write to paper_trade is via existing
    submit_trade (called transitively by run_paper_trading)."""
    src = Path(
        "scripts/replay_paper_execution_chain.py"
    ).read_text(encoding="utf-8")
    bad: list[str] = []
    for line in src.splitlines():
        # Skip docstring + comment lines.
        stripped = line.strip()
        if stripped.startswith('"') or stripped.startswith("#"):
            continue
        if re.search(r"INSERT\s+INTO\s+paper_trade\b", line, re.IGNORECASE):
            bad.append(line.strip())
        # Also forbid direct ORM PaperTrade(...) construction.
        if re.search(r"\bPaperTrade\s*\(", line):
            bad.append(line.strip())
    assert not bad, (
        f"direct paper_trade insert / PaperTrade() construction "
        f"forbidden: {bad}"
    )


def test_uses_existing_engine_paths():
    """Source must reference the existing run_paper_trading +
    recommendation engine entrypoints — not reimplement them."""
    src = Path(
        "scripts/replay_paper_execution_chain.py"
    ).read_text(encoding="utf-8")
    must_have = (
        "from apps.worker.src.jobs.run_paper_trading import run_paper_trading",
        "run_recommendations_for_all_accounts",
    )
    for needle in must_have:
        assert needle in src, f"missing required import/call: {needle}"


def test_allowed_and_forbidden_disjoint():
    overlap = mod.ALLOWED_WRITE_TABLES & mod.FORBIDDEN_WRITE_TABLES
    assert not overlap, f"overlap: {overlap}"


def test_delete_statements_only_target_allowed_tables():
    for stmt, tbl in mod.DELETE_STATEMENTS_FOR_DATE:
        assert tbl in mod.ALLOWED_WRITE_TABLES, tbl
        assert tbl in stmt
        assert ":d" in stmt, (
            f"DELETE for {tbl} not date-scoped: {stmt}")


# ---------------------------------------------------------------------------
# Worker / scheduler isolation
# ---------------------------------------------------------------------------
def test_replay_chain_not_in_worker_registry():
    from apps.worker.src.jobs.registry import REGISTRY
    for name, fn in REGISTRY.items():
        assert "replay_paper_execution_chain" not in name
        mod_name = getattr(fn, "__module__", "") or ""
        assert "replay_paper_execution_chain" not in mod_name


def test_replay_chain_not_in_scheduler_or_cron():
    candidates = [
        Path("apps/worker/src/scheduler/tick_loop.py"),
        Path("apps/worker/src/jobs/registry.py"),
        Path("apps/worker/src/main.py"),
        Path("infra/compose/docker-compose.yml"),
        Path("scripts/run_daily_loop.sh"),
    ]
    for f in Path("apps/worker").rglob("*cron*"):
        candidates.append(f)
    bad: list[str] = []
    for f in candidates:
        if not f.exists():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "replay_paper_execution_chain" in text:
            bad.append(str(f))
    assert not bad, (
        f"replay_paper_execution_chain leaked into scheduler/cron: {bad}"
    )


def test_module_docstring_calls_out_operator_only():
    src = Path(
        "scripts/replay_paper_execution_chain.py"
    ).read_text(encoding="utf-8")
    head = src.split('"""')[1] if '"""' in src else ""
    assert "operator-only" in head.lower() or "OPERATOR-ONLY" in head
    assert "scheduled" in head.lower()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _noop_async(*a, **k):
    return None


class _StubCtxSession:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def commit(self): pass
    def rollback(self): pass
    def execute(self, *a, **k):
        class R:
            rowcount = 0
            def scalar(self): return 0
        return R()
